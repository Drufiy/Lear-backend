import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Mapping

from prash.connectors.base import Connector, ConnectorState, ResourceState

logger = logging.getLogger(__name__)


class TerraformConnector(Connector):
    """Connector for Terraform, supporting local CLI and Terraform Cloud (HCP)."""

    name: str = "terraform"
    read_capabilities: tuple[str, ...] = ("state", "drift")
    write_capabilities: tuple[str, ...] = ("apply", "init")

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.use_cloud = str(self.credentials.get("TERRAFORM_USE_CLOUD", "false")).lower() == "true"
        self.cloud_token = self.credentials.get("TERRAFORM_API_TOKEN", "")

    def authenticate(self) -> bool:
        """Validate credentials or local binary."""
        if self.use_cloud:
            if not self.cloud_token:
                logger.warning("Terraform Cloud enabled but TERRAFORM_API_TOKEN is missing")
                return False
            # Here we would normally make a lightweight API call to TF Cloud to verify token.
            return True
        else:
            # Local execution check
            try:
                subprocess.run(["terraform", "version"], check=True, capture_output=True)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.warning("Terraform binary not found on PATH or failed to execute.")
                return False

    def locate(self, resource: str) -> Dict[str, Any]:
        """Resolve a human-readable resource id (directory or workspace) to a handle."""
        if self.use_cloud:
            return {"workspace": resource, "type": "cloud"}
        else:
            target_dir = Path(resource).resolve()
            if not target_dir.exists() or not target_dir.is_dir():
                logger.warning(f"Terraform directory not found: {target_dir}")
                return {"directory": None, "type": "local"}
            return {"directory": str(target_dir), "type": "local"}

    def fetch_logs(self, resource: str, **kwargs: Any) -> list[str]:
        """Return raw log lines for a resource (e.g. from a recent plan)."""
        handle = self.locate(resource)
        if handle.get("type") == "cloud":
            # Mock cloud fetch for now
            return ["Cloud logging not fully implemented. Please check Terraform Cloud UI."]
        
        target_dir = handle.get("directory")
        if not target_dir:
            return []

        # Run a plan to fetch logs as drift detection
        try:
            result = subprocess.run(
                ["terraform", "plan", "-no-color"],
                cwd=target_dir,
                capture_output=True,
                text=True,
            )
            return result.stdout.splitlines() + result.stderr.splitlines()
        except Exception as e:
            return [f"Failed to fetch terraform plan logs: {e}"]

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        """Return the current state of a resource (e.g., checking tfstate or drift)."""
        handle = self.locate(resource)
        if handle.get("type") == "cloud":
            # Mock cloud state for now
            return ResourceState(resource=resource, state=ConnectorState.STABLE, detail={"mode": "cloud"})

        target_dir = handle.get("directory")
        if not target_dir:
            return ResourceState(resource=resource, state=ConnectorState.NOT_FOUND, detail={"error": "Directory not found"})

        # To optimize, we can first check if terraform.tfstate exists and is valid
        tfstate_path = Path(target_dir) / "terraform.tfstate"
        if not tfstate_path.exists():
            return ResourceState(
                resource=resource,
                state=ConnectorState.DEGRADED,
                detail={"error": "No terraform.tfstate found. Run terraform init/apply."}
            )

        try:
            with open(tfstate_path, "r") as f:
                state_data = json.load(f)
                if not state_data.get("resources"):
                    return ResourceState(
                        resource=resource, 
                        state=ConnectorState.UNKNOWN, 
                        detail={"info": "State is empty."}
                    )
        except Exception as e:
            return ResourceState(
                resource=resource, 
                state=ConnectorState.FAILED, 
                detail={"error": f"Could not parse state: {e}"}
            )

        # For strict drift checking, we can run terraform plan -detailed-exitcode
        # But since the user wanted just parsing tfstate for watcher, we'll return STABLE if parseable.
        # If the user specifically asks for drift in kwargs, we can run plan.
        if kwargs.get("check_drift"):
            try:
                result = subprocess.run(
                    ["terraform", "plan", "-detailed-exitcode", "-no-color"],
                    cwd=target_dir,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return ResourceState(resource=resource, state=ConnectorState.STABLE, detail={"drift": False})
                elif result.returncode == 2:
                    return ResourceState(resource=resource, state=ConnectorState.DEGRADED, detail={"drift": True, "info": "Drift detected"})
                else:
                    return ResourceState(resource=resource, state=ConnectorState.FAILED, detail={"error": "Plan failed"})
            except Exception as e:
                return ResourceState(resource=resource, state=ConnectorState.FAILED, detail={"error": str(e)})

        return ResourceState(resource=resource, state=ConnectorState.STABLE, detail={"parsed_state": True})
