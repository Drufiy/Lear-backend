"""Azure VM read-only connector with execution capabilities.

Reads credentials from the injected CredentialStore per Lear philosophy.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any, Dict, Mapping

try:
    from azure.identity import ClientSecretCredential, DefaultAzureCredential
    from azure.mgmt.compute import ComputeManagementClient
    from azure.core.exceptions import AzureError
    _HAS_AZURE = True
except ImportError:
    _HAS_AZURE = False

from .base import Connector, ConnectorState, ResourceState

class AzureRunCommandFailedNeedsSSH(Exception):
    """Raised when Azure Run Command fails and requires SSH to proceed."""
    pass


class AzureConnector(Connector):
    name = "azure"
    read_capabilities = ("instance_status", "logs")
    write_capabilities = ("execute",)

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.subscription_id = self.credentials.get("AZURE_SUBSCRIPTION_ID")
        self.tenant_id = self.credentials.get("AZURE_TENANT_ID")
        self.client_id = self.credentials.get("AZURE_CLIENT_ID")
        self.client_secret = self.credentials.get("AZURE_CLIENT_SECRET")
        self._authenticated: bool | None = None
        self._credential = None
        self._rg_cache: Dict[str, str] = {}  # VM name -> Resource Group name cache

    def authenticate(self) -> bool:
        if self._authenticated is not None:
            return self._authenticated

        if not self.subscription_id:
            self._authenticated = False
            return False

        if _HAS_AZURE:
            try:
                if self.tenant_id and self.client_id and self.client_secret:
                    self._credential = ClientSecretCredential(
                        tenant_id=self.tenant_id,
                        client_id=self.client_id,
                        client_secret=self.client_secret
                    )
                else:
                    self._credential = DefaultAzureCredential()
                
                # Test auth
                client = ComputeManagementClient(self._credential, self.subscription_id)
                # Just list one VM to verify access
                next(client.virtual_machines.list_all(), None)
                self._authenticated = True
                return True
            except Exception:
                pass

        # Fallback to AZ CLI
        try:
            subprocess.run(
                ["az", "account", "show"],
                capture_output=True,
                check=True
            )
            self._authenticated = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self._authenticated = False

        return self._authenticated

    def _get_resource_group(self, vm_name: str) -> str | None:
        if vm_name in self._rg_cache:
            return self._rg_cache[vm_name]

        if _HAS_AZURE and self._credential:
            client = ComputeManagementClient(self._credential, self.subscription_id)
            for vm in client.virtual_machines.list_all():
                if vm.name == vm_name:
                    rg = vm.id.split("/")[4]
                    self._rg_cache[vm_name] = rg
                    return rg
        else:
            try:
                res = subprocess.run(
                    ["az", "vm", "list", "--query", f"[?name=='{vm_name}'].resourceGroup", "-o", "tsv"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                rg = res.stdout.strip()
                if rg:
                    self._rg_cache[vm_name] = rg
                    return rg
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        return None

    def locate(self, resource: str) -> Dict[str, Any]:
        """Locate Azure VM by Name."""
        if not self.authenticate():
            return {}

        rg = self._get_resource_group(resource)
        if not rg:
            return {}

        if _HAS_AZURE and self._credential:
            client = ComputeManagementClient(self._credential, self.subscription_id)
            try:
                vm = client.virtual_machines.get(rg, resource, expand="instanceView")
                state = "unknown"
                if vm.instance_view and vm.instance_view.statuses:
                    for status in vm.instance_view.statuses:
                        if status.code.startswith("PowerState/"):
                            state = status.code.split("/")[-1]
                return {
                    "vm_name": vm.name,
                    "resource_group": rg,
                    "location": vm.location,
                    "vm_size": vm.hardware_profile.vm_size if vm.hardware_profile else None,
                    "state": state
                }
            except AzureError:
                return {}
        else:
            try:
                res = subprocess.run(
                    ["az", "vm", "show", "-g", rg, "-n", resource, "-d", "--query", "{name:name, rg:resourceGroup, loc:location, size:hardwareProfile.vmSize, state:powerState}", "-o", "json"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                data = json.loads(res.stdout)
                state = data.get("state", "").replace("VM ", "")
                return {
                    "vm_name": data.get("name"),
                    "resource_group": data.get("rg"),
                    "location": data.get("loc"),
                    "vm_size": data.get("size"),
                    "state": state
                }
            except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
                return {}

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        if not self.authenticate():
            return ResourceState(resource, ConnectorState.UNKNOWN, {"error": "unauthenticated"})

        vm_info = self.locate(resource)
        if not vm_info:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
            
        state_name = vm_info["state"].lower()
        if "running" in state_name:
            state = ConnectorState.HEALTHY
        elif "deallocated" in state_name or "stopped" in state_name:
            state = ConnectorState.STABLE
        elif "starting" in state_name:
            state = ConnectorState.DEPLOYING
        elif "failed" in state_name:
            state = ConnectorState.FAILED
        else:
            state = ConnectorState.UNKNOWN

        return ResourceState(resource, state, vm_info)

    def fetch_logs(self, resource: str, **kwargs: Any) -> list[str]:
        if not self.authenticate():
            return []

        vm_info = self.locate(resource)
        if not vm_info:
            return []
            
        rg = vm_info["resource_group"]
        
        try:
            res = subprocess.run(
                ["az", "vm", "boot-diagnostics", "get-boot-log", "-g", rg, "-n", resource],
                capture_output=True,
                text=True,
                check=True
            )
            return res.stdout.splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    def execute_command(self, resource: str, command: str, **kwargs: Any) -> Dict[str, Any]:
        """Execute command via Azure VM Run Command, falling back to SSH."""
        if not self.authenticate():
            return {"error": "unauthenticated"}

        vm_info = self.locate(resource)
        if not vm_info:
            return {"error": f"VM {resource} not found"}

        rg = vm_info["resource_group"]
        script_id = "RunShellScript"
        
        try:
            if _HAS_AZURE and self._credential:
                client = ComputeManagementClient(self._credential, self.subscription_id)
                poller = client.virtual_machines.begin_run_command(
                    rg, resource,
                    {"command_id": script_id, "script": [command]}
                )
                result = poller.result()
                stdout = ""
                stderr = ""
                if result.value:
                    for msg in result.value:
                        if msg.code == "ComponentStatus/StdOut/succeeded":
                            stdout = msg.message or ""
                        elif msg.code == "ComponentStatus/StdErr/succeeded":
                            stderr = msg.message or ""
                return {
                    "source": "run-command",
                    "status": "Success",
                    "stdout": stdout,
                    "stderr": stderr
                }
            else:
                res = subprocess.run(
                    ["az", "vm", "run-command", "invoke", "-g", rg, "-n", resource, "--command-id", script_id, "--scripts", command, "-o", "json"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                data = json.loads(res.stdout)
                stdout = ""
                stderr = ""
                for msg in data.get("value", []):
                    if msg.get("code") == "ComponentStatus/StdOut/succeeded":
                        stdout = msg.get("message", "")
                    elif msg.get("code") == "ComponentStatus/StdErr/succeeded":
                        stderr = msg.get("message", "")
                return {
                    "source": "run-command",
                    "status": "Success",
                    "stdout": stdout,
                    "stderr": stderr
                }
        except Exception as e:
            pem_path = kwargs.get("pem_path")
            if not pem_path:
                raise AzureRunCommandFailedNeedsSSH(f"Run Command failed: {e}. A PEM file is required for SSH fallback.")

            if not os.path.exists(pem_path):
                return {"error": f"PEM file not found at {pem_path}"}
            
            try:
                res = subprocess.run(
                    ["az", "vm", "show-details", "-g", rg, "-n", resource, "--query", "publicIps", "-o", "tsv"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                public_ip = res.stdout.strip()
                if not public_ip:
                    return {"error": "VM does not have a Public IP."}
            except Exception:
                return {"error": "Failed to get Public IP for SSH."}
            
            ssh_cmd = [
                "ssh", "-i", pem_path, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
                f"azureuser@{public_ip}", command
            ]
            
            try:
                result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
                return {
                    "source": "ssh",
                    "status": "Success",
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
            except subprocess.CalledProcessError as err:
                return {
                    "source": "ssh",
                    "status": "Failed",
                    "stdout": err.stdout,
                    "stderr": err.stderr,
                    "exit_code": err.returncode
                }
