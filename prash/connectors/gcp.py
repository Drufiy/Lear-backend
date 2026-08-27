"""GCP Compute Engine read-only connector with execution capabilities.

Reads credentials from the injected CredentialStore per Lear philosophy.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, Mapping

try:
    from google.oauth2 import service_account
    import google.auth
    from googleapiclient import discovery
    from googleapiclient.errors import HttpError
    _HAS_GCP = True
except ImportError:
    _HAS_GCP = False

from .base import Connector, ConnectorState, ResourceState

class GCPRunCommandFailedNeedsSSH(Exception):
    """Raised when GCP execution fails and requires an SSH PEM file to proceed."""
    pass


class GCPConnector(Connector):
    name = "gcp"
    read_capabilities = ("instance_status", "logs")
    write_capabilities = ("execute",)

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.project_id = self.credentials.get("GCP_PROJECT_ID")
        self.region = self.credentials.get("GCP_REGION", "us-central1")
        self.credentials_path = self.credentials.get("GOOGLE_APPLICATION_CREDENTIALS")
        self._authenticated: bool | None = None
        self._creds = None
        self._zone_cache: Dict[str, str] = {}

    def authenticate(self) -> bool:
        if self._authenticated is not None:
            return self._authenticated

        if not self.project_id:
            self._authenticated = False
            return False

        if _HAS_GCP:
            try:
                if self.credentials_path and os.path.exists(self.credentials_path):
                    self._creds = service_account.Credentials.from_service_account_file(self.credentials_path)
                else:
                    self._creds, _ = google.auth.default()
                self._authenticated = True
                return True
            except Exception:
                pass

        # Fallback to gcloud
        try:
            subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True,
                check=True
            )
            self._authenticated = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self._authenticated = False

        return self._authenticated

    def _get_zone(self, instance_name: str) -> str | None:
        if instance_name in self._zone_cache:
            return self._zone_cache[instance_name]

        if _HAS_GCP and self._creds:
            try:
                compute = discovery.build('compute', 'v1', credentials=self._creds, cache_discovery=False)
                request = compute.instances().aggregatedList(project=self.project_id)
                while request is not None:
                    response = request.execute()
                    for name, instances_scoped_list in response.get('items', {}).items():
                        for instance in instances_scoped_list.get('instances', []):
                            if instance['name'] == instance_name:
                                zone = instance['zone'].split('/')[-1]
                                self._zone_cache[instance_name] = zone
                                return zone
                    request = compute.instances().aggregatedList_next(previous_request=request, previous_response=response)
            except HttpError:
                pass
        else:
            try:
                res = subprocess.run(
                    ["gcloud", "compute", "instances", "list", "--filter", f"name={instance_name}", "--format", "value(zone)", "--project", self.project_id],
                    capture_output=True,
                    text=True,
                    check=True
                )
                zone = res.stdout.strip()
                if zone:
                    self._zone_cache[instance_name] = zone
                    return zone
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        return None

    def locate(self, resource: str) -> Dict[str, Any]:
        """Locate GCE instance."""
        if not self.authenticate():
            return {}

        zone = self._get_zone(resource)
        if not zone:
            return {}

        if _HAS_GCP and self._creds:
            try:
                compute = discovery.build('compute', 'v1', credentials=self._creds, cache_discovery=False)
                instance = compute.instances().get(project=self.project_id, zone=zone, instance=resource).execute()
                return {
                    "instance_name": instance['name'],
                    "zone": zone,
                    "machine_type": instance['machineType'].split('/')[-1],
                    "state": instance['status']
                }
            except HttpError:
                return {}
        else:
            try:
                res = subprocess.run(
                    ["gcloud", "compute", "instances", "describe", resource, "--zone", zone, "--project", self.project_id, "--format", "json"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                data = json.loads(res.stdout)
                return {
                    "instance_name": data.get('name'),
                    "zone": zone,
                    "machine_type": data.get('machineType', '').split('/')[-1],
                    "state": data.get('status')
                }
            except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
                return {}

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        if not self.authenticate():
            return ResourceState(resource, ConnectorState.UNKNOWN, {"error": "unauthenticated"})

        instance_info = self.locate(resource)
        if not instance_info:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
            
        state_name = instance_info["state"].upper()
        if state_name == "RUNNING":
            state = ConnectorState.HEALTHY
        elif state_name in ("STOPPED", "TERMINATED", "SUSPENDED"):
            state = ConnectorState.STABLE
        elif state_name in ("PROVISIONING", "STAGING"):
            state = ConnectorState.DEPLOYING
        else:
            state = ConnectorState.UNKNOWN

        return ResourceState(resource, state, instance_info)

    def fetch_logs(self, resource: str, **kwargs: Any) -> list[str]:
        if not self.authenticate():
            return []

        zone = self._get_zone(resource)
        if not zone:
            return []
            
        try:
            res = subprocess.run(
                ["gcloud", "compute", "instances", "get-serial-port-output", resource, "--zone", zone, "--project", self.project_id],
                capture_output=True,
                text=True,
                check=True
            )
            return res.stdout.splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    def execute_command(self, resource: str, command: str, **kwargs: Any) -> Dict[str, Any]:
        """Execute command via gcloud compute ssh."""
        if not self.authenticate():
            return {"error": "unauthenticated"}

        zone = self._get_zone(resource)
        if not zone:
            return {"error": f"Instance {resource} not found"}
            
        try:
            res = subprocess.run(
                ["gcloud", "compute", "ssh", resource, "--zone", zone, "--project", self.project_id, "--command", command, "--quiet"],
                capture_output=True,
                text=True,
                check=True
            )
            return {
                "source": "gcloud-ssh",
                "status": "Success",
                "stdout": res.stdout,
                "stderr": res.stderr
            }
        except Exception as e:
            pem_path = kwargs.get("pem_path")
            if not pem_path:
                raise GCPRunCommandFailedNeedsSSH(f"Execution failed: {e}. A PEM file is required for native SSH fallback.")

            if not os.path.exists(pem_path):
                return {"error": f"PEM file not found at {pem_path}"}
            
            try:
                ip_res = subprocess.run(
                    ["gcloud", "compute", "instances", "describe", resource, "--zone", zone, "--project", self.project_id, "--format", "get(networkInterfaces[0].accessConfigs[0].natIP)"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                public_ip = ip_res.stdout.strip()
                if not public_ip:
                    return {"error": "Instance does not have a Public IP."}
            except Exception:
                return {"error": "Failed to get Public IP for SSH."}
            
            ssh_cmd = [
                "ssh", "-i", pem_path, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
                f"{kwargs.get('ssh_user', 'ubuntu')}@{public_ip}", command
            ]
            
            try:
                result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
                return {
                    "source": "ssh",
                    "status": "Success",
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
            except subprocess.CalledProcessError as ssh_err:
                return {
                    "source": "ssh",
                    "status": "Failed",
                    "stdout": ssh_err.stdout,
                    "stderr": ssh_err.stderr,
                    "exit_code": ssh_err.returncode
                }
