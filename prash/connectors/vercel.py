"""Vercel connector, ported from v1's vercel_client.py as the template for all
new connectors: authenticate -> locate resource -> fetch logs -> poll state.

Read-only for this sprint (matching the v1 scope). Add write capabilities as
needed in later phases.
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
