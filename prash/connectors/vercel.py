"""Vercel connector, ported from v1's vercel_client.py as the template for all
new connectors: authenticate -> locate resource -> fetch logs -> poll state.

Write actions added 2026-08-19 (PRASH_V2.md §7b) -- redeploy() and rollback(),
wired through prash/actions/vercel_deploy.py. redeploy() reuses the exact
same /v13/deployments create-deployment endpoint Vercel itself calls a
"redeploy": a new deployment is created that references an existing
deployment's id, cloning it. rollback() uses Vercel's dedicated Rollback API
(/v9/projects/{id}/rollback/{deploymentId}).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Mapping

from .base import Connector, ConnectorState, ResourceState

API_URL = "https://api.vercel.com"


class VercelError(RuntimeError):
    pass


class VercelConnector(Connector):
    name = "vercel"
    read_capabilities = ("build_logs", "deploy_state")
    write_capabilities = ("redeploy", "rollback")

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.token = credentials.get("VERCEL_TOKEN")
        self.headers = {"Authorization": f"Bearer {self.token or ''}"}

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        url = f"{API_URL}{path}"
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            self.headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise VercelError(f"Vercel API {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}") from exc

    def authenticate(self) -> bool:
        if not self.token:
            return False
        try:
            self._request("GET", "/v2/user")
            return True
        except VercelError:
            return False

    def locate(self, resource: str) -> Dict[str, Any]:
        return {"project": resource}

    def fetch_logs(self, resource: str, deployment: str = "latest", **kwargs: Any) -> list[str]:
        handle = self.locate(resource)
        resp = self._request("GET", f"/v1/deployments/{deployment}")
        logs = resp.get("logs", []) if isinstance(resp, dict) else []
        return [f"{log.get('createdAt', '')} {log.get('text', '')}".strip() for log in logs]

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        handle = self.locate(resource)
        try:
            deploys = self._request("GET", f"/v1/deployments?projectId={handle['project']}&limit=1")
        except VercelError:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
        items = deploys.get("deployments", []) if isinstance(deploys, dict) else []
        if not items:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
        ready_state = items[0].get("readyState", "ERROR")
        state = ConnectorState.HEALTHY if ready_state == "READY" else ConnectorState.FAILED
        if ready_state in ("BUILDING", "QUEUED", "INITIALIZING"):
            state = ConnectorState.DEPLOYING
        return ResourceState(resource, state, {"latest_deployment": items[0]})

    def _latest_deployment_id(self, project: str) -> str:
        deploys = self._request("GET", f"/v1/deployments?projectId={project}&limit=1")
        items = deploys.get("deployments", []) if isinstance(deploys, dict) else []
        if not items:
            raise VercelError(f"no deployments found for project {project}")
        return items[0]["uid"]

    def redeploy(self, resource: str, deployment_id: str | None = None) -> Dict[str, Any]:
        """Create a new deployment cloning an existing one -- Vercel's own
        "redeploy" action, done via the same create-deployment endpoint used
        to make any deployment. Defaults to redeploying the latest one."""
        handle = self.locate(resource)
        target_id = deployment_id or self._latest_deployment_id(handle["project"])
        return self._request("POST", "/v13/deployments", {"deploymentId": target_id, "name": handle["project"]})

    def production_deployment_id(self, resource: str) -> str | None:
        """The deployment currently aliased to production -- NOT the same as
        "most recent deployment" (poll_state's notion). A rollback re-points
        the production alias to an existing, older deployment without
        creating anything new, so the most-recently-created deployment never
        changes when a rollback succeeds. Verifying rollback against
        poll_state() was structurally guaranteed to report failure on every
        successful rollback -- found live, 2026-08-24, testing a real
        rollback that Vercel confirmed succeeded while verify() called it a
        failure. This reads /v9/projects/{id}'s targets.production.id, the
        field that actually reflects what's live."""
        handle = self.locate(resource)
        try:
            project = self._request("GET", f"/v9/projects/{handle['project']}")
        except VercelError:
            return None
        return (project.get("targets") or {}).get("production", {}).get("id")

    def rollback(self, resource: str, deployment_id: str) -> Dict[str, Any]:
        """Point production at a specific earlier deployment via Vercel's
        dedicated Rollback API. Unlike redeploy(), this requires an explicit
        deployment_id -- rolling back to "whatever's most recent" would just
        be a redeploy, not a rollback."""
        handle = self.locate(resource)
        return self._request("POST", f"/v9/projects/{handle['project']}/rollback/{deployment_id}")
