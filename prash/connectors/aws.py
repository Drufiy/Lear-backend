"""AWS EC2 read-only connector.

Reads credentials from the injected CredentialStore per Prash v2 philosophy.
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
    read_capabilities = ("pod_status", "logs")  # Mapping EC2 instances similar to pods for now
    write_capabilities = ("execute",)

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.access_key = self.credentials.get("AWS_ACCESS_KEY_ID")
        self.secret_key = self.credentials.get("AWS_SECRET_ACCESS_KEY")
        self.region = self.credentials.get("AWS_REGION")
        self.session_token = self.credentials.get("AWS_SESSION_TOKEN")

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
        if not self.access_key or not self.secret_key:
            return False
        
        try:
            session = self._get_boto_session()
            sts = session.client("sts")
            sts.get_caller_identity()
            return True
        except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
            return False

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
            return ResourceState(resource, state, detail)
            
        except botocore.exceptions.ClientError as e:
            return ResourceState(resource, ConnectorState.UNKNOWN, {"error": str(e)})

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
