"""AWS EC2 read-only connector.

Reads credentials from the injected CredentialStore per Lear philosophy.
Does not fall back to `~/.aws/credentials` implicitly unless the user added it to the env.
"""

from __future__ import annotations

import base64
import os
import subprocess
import time
from typing import Any, Dict, Mapping

try:
    import boto3
    import botocore.exceptions
    _HAS_BOTO3 = True
except ImportError:
    _HAS_BOTO3 = False

from .base import Connector, ConnectorState, ResourceState

class SSMFailedNeedsSSH(Exception):
    """Raised when SSM execution fails and requires an SSH PEM file to proceed."""
    pass


class AWSConnector(Connector):
    name = "aws"
    read_capabilities = ("instance_status", "logs")
    write_capabilities = ("execute",)

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.access_key = self.credentials.get("AWS_ACCESS_KEY_ID")
        self.secret_key = self.credentials.get("AWS_SECRET_ACCESS_KEY")
        self.region = self.credentials.get("AWS_REGION")
        self.session_token = self.credentials.get("AWS_SESSION_TOKEN")
        self._authenticated: bool | None = None

    def _get_boto_session(self) -> Any:
        if not _HAS_BOTO3:
            raise RuntimeError("boto3 is not installed")
        
        return boto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            aws_session_token=self.session_token,
        )

    def authenticate(self) -> bool:
        """Validate credentials against STS, once per connector instance.

        Every other method here calls authenticate() before touching AWS, so
        without caching a single `prash investigate` invocation fires several
        redundant STS calls (poll_state -> authenticate + locate ->
        authenticate). Cached per-instance, which matches how connectors are
        constructed: fresh per CLI invocation (see cli.py _make_connectors).
        """
        if self._authenticated is not None:
            return self._authenticated

        if not self.access_key or not self.secret_key:
            self._authenticated = False
            return False

        try:
            session = self._get_boto_session()
            sts = session.client("sts")
            sts.get_caller_identity()
            self._authenticated = True
        except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
            self._authenticated = False
        return self._authenticated

    def locate(self, resource: str) -> Dict[str, Any]:
        """Locate EC2 instance by ID or Name tag."""
        if not self.authenticate():
            return {}

        session = self._get_boto_session()
        ec2 = session.client("ec2")

        try:
            if resource.startswith("i-"):
                resp = ec2.describe_instances(InstanceIds=[resource])
            else:
                resp = ec2.describe_instances(Filters=[{"Name": "tag:Name", "Values": [resource]}])
            
            if not resp.get("Reservations") or not resp["Reservations"][0].get("Instances"):
                return {}
                
            instance = resp["Reservations"][0]["Instances"][0]
            return {
                "instance_id": instance["InstanceId"],
                "instance_type": instance["InstanceType"],
                "state": instance["State"]["Name"],
            }
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                return {}
            raise

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        """Poll the state of an EC2 instance and map it to ConnectorState."""
        if not self.authenticate():
            return ResourceState(resource, ConnectorState.UNKNOWN, {"error": "unauthenticated"})

        instance_info = self.locate(resource)
        if not instance_info:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
            
        instance_id = instance_info["instance_id"]
        session = self._get_boto_session()
        ec2 = session.client("ec2")

        try:
            # Check instance state
            state_name = instance_info["state"]
            
            # Map AWS states to ConnectorState
            if state_name == "running":
                state = ConnectorState.HEALTHY
            elif state_name in ("stopped", "stopping"):
                state = ConnectorState.STABLE
            elif state_name == "pending":
                state = ConnectorState.DEPLOYING
            elif state_name in ("shutting-down", "terminated"):
                state = ConnectorState.NOT_FOUND
            else:
                state = ConnectorState.UNKNOWN

            # Check Status Checks if it's running
            if state == ConnectorState.HEALTHY:
                status_resp = ec2.describe_instance_status(InstanceIds=[instance_id])
                if status_resp.get("InstanceStatuses"):
                    status = status_resp["InstanceStatuses"][0]
                    if status["InstanceStatus"]["Status"] == "impaired" or status["SystemStatus"]["Status"] == "impaired":
                        state = ConnectorState.FAILED

            detail = {
                "instance_id": instance_id,
                "instance_type": instance_info["instance_type"],
                "aws_state": state_name
            }

            # Service-level health, not just instance-level: when the instance
            # is up and its status checks pass, ask the box itself whether the
            # prash test fixture is wedged (marker file present). This is what
            # makes `prash investigate prash-test-fixture --provider aws`
            # report DEGRADED after scripts/testing/break_aws.py forces the
            # failure state -- the instance stays HEALTHY at the EC2 level
            # (a running instance with OK checks) while the app it simulates
            # is genuinely broken, exactly the split TESTING_SETUP.md promises.
            # Mirrors the Datadog connector's poll_state(), which actively
            # reads the monitor's real overall_state rather than mapping
            # metadata.
            if state == ConnectorState.HEALTHY:
                try:
                    marker_present = self._marker_present(instance_id, kwargs.get("pem_path"))
                    if marker_present:
                        state = ConnectorState.DEGRADED
                        detail["marker"] = "prash-test-fixture-break"
                except Exception:  # noqa: BLE001 — never fabricate a degraded state we couldn't verify
                    pass

            return ResourceState(resource, state, detail)
            
        except botocore.exceptions.ClientError as e:
            return ResourceState(resource, ConnectorState.UNKNOWN, {"error": str(e)})

    def _marker_present(self, instance_id: str, pem_path: str | None = None) -> bool:
        """Return True if the prash test fixture's break marker exists on the
        instance. Uses SSM first; falls back to SSH when pem_path is given
        (the exact fallback execute-aws exercises). Never raises.
        """
        session = self._get_boto_session()
        ssm = session.client("ssm")
        cmd = "test -f /tmp/prash-test-fixture-break && echo PRESENT || echo ABSENT"
        try:
            resp = ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={"commands": [cmd]},
                TimeoutSeconds=30,
            )
            command_id = resp["Command"]["CommandId"]
            # Poll until the invocation finishes -- a single immediate read can
            # catch it still Pending/InProgress and wrongly report ABSENT.
            for _ in range(15):
                time.sleep(2)
                inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
                if inv.get("Status") not in ("Pending", "InProgress"):
                    return "PRESENT" in inv.get("StandardOutputContent", "")
            return False
        except Exception:  # noqa: BLE001 — SSM unavailable; fall through to SSH if we have a pem
            pass

        if not pem_path or not os.path.exists(pem_path):
            return False

        try:
            ec2 = session.client("ec2")
            inst = ec2.describe_instances(InstanceIds=[instance_id])
            public_ip = inst["Reservations"][0]["Instances"][0]["PublicIpAddress"]
        except (KeyError, IndexError):
            return False

        try:
            result = subprocess.run(
                ["ssh", "-i", pem_path,
                 "-o", "StrictHostKeyChecking=no",
                 "-o", "ConnectTimeout=10",
                 f"ubuntu@{public_ip}", cmd],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return "PRESENT" in result.stdout
        except Exception:  # noqa: BLE001 — same honesty rule as the SSM path
            return False

    def fetch_logs(self, resource: str, **kwargs: Any) -> list[str]:
        """Fetch EC2 console output."""
        if not self.authenticate():
            return []

        instance_info = self.locate(resource)
        if not instance_info:
            return []
            
        session = self._get_boto_session()
        ec2 = session.client("ec2")

        try:
            resp = ec2.get_console_output(InstanceId=instance_info["instance_id"])
            output = resp.get("Output")
            if not output:
                return []
                
            try:
                import binascii
                # Some boto3 versions/mocks automatically decode the base64 string
                decoded = base64.b64decode(output).decode("utf-8", errors="replace")
            except (binascii.Error, ValueError):
                decoded = output
            return decoded.splitlines()
        except botocore.exceptions.ClientError:
            return []

    def execute_command(self, resource: str, command: str, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute a command on an EC2 instance.
        Attempts AWS Systems Manager (SSM) first.
        If SSM fails, it attempts native SSH if 'pem_path' is provided in kwargs.
        If SSM fails and 'pem_path' is absent, raises SSMFailedNeedsSSH.
        """
        if not self.authenticate():
            return {"error": "unauthenticated"}

        instance_info = self.locate(resource)
        if not instance_info:
            return {"error": f"Instance {resource} not found"}

        instance_id = instance_info["instance_id"]
        session = self._get_boto_session()
        ssm = session.client("ssm")

        try:
            ssm_resp = ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={'commands': [command]},
                TimeoutSeconds=30
            )
            command_id = ssm_resp['Command']['CommandId']
            # Wait a few seconds for command to start outputting
            time.sleep(2)
            out_resp = ssm.get_command_invocation(
                CommandId=command_id,
                InstanceId=instance_id,
            )
            return {
                "source": "ssm",
                "status": out_resp.get("Status"),
                "stdout": out_resp.get("StandardOutputContent", ""),
                "stderr": out_resp.get("StandardErrorContent", "")
            }
        except Exception as e:
            # SSM failed. Check if we should fallback to SSH
            pem_path = kwargs.get("pem_path")
            if not pem_path:
                raise SSMFailedNeedsSSH(f"SSM execution failed: {e}. A PEM file is required for SSH fallback.")

            if not os.path.exists(pem_path):
                return {"error": f"PEM file not found at {pem_path}"}

            ec2 = session.client("ec2")
            inst_info = ec2.describe_instances(InstanceIds=[instance_id])
            try:
                public_ip = inst_info["Reservations"][0]["Instances"][0]["PublicIpAddress"]
            except KeyError:
                return {"error": "Instance does not have a Public IP address assigned for SSH."}

            # Attempt native SSH
            ssh_cmd = [
                "ssh",
                "-i", pem_path,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                f"ubuntu@{public_ip}",
                command
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
