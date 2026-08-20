"""PagerDuty connector (Sprint 2 Tier 3, PRASH_V2.md §7b).

Read + a scoped pair of write actions (acknowledge/resolve an incident) --
per Aradhya's explicit call, since PagerDuty's actual value is arguably the
write side, not just reading state (unlike Datadog/Grafana, which stayed
read-only for their first pass, matching every other connector's v1
posture).

`resource` is a PagerDuty *service* name or id -- the persistent thing you
check on, the same role a Datadog monitor or Grafana alert rule plays here.
poll_state() reports whatever triggered/acknowledged incidents currently
exist for that service; the write methods (acknowledge_incident /
resolve_incident, called from prash/actions/pagerduty_incident.py) then act
on one specific incident by its id, which poll_state()'s detail surfaces --
the same relationship this repo's other connectors already have between a
broad resource and a specific sub-target (a pod vs. its Deployment for
rollback; a monitor vs. the alert instance for Grafana).

Auth is a REST API key via `Authorization: Token token=...` (works for both
account-level API keys and user-scoped tokens) -- checked against
`/abilities`, which needs nothing beyond a valid token. Writes additionally
require identifying WHO is making the change: PagerDuty's API rejects a
status update with no `From: <email>` header naming a real user on the
account, so PAGERDUTY_FROM_EMAIL is a second, write-only-required
credential -- reads work with just the API key.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Mapping

from .base import Connector, ConnectorState, ResourceState

API_URL = "https://api.pagerduty.com"

# Incidents in either of these statuses are still open -- someone hasn't
# declared the problem over yet. "resolved" is excluded on purpose: a
# resolved incident isn't evidence the service is currently unhealthy.
_OPEN_STATUSES = ("triggered", "acknowledged")


class PagerDutyError(RuntimeError):
    pass


class PagerDutyConnector(Connector):
    name = "pagerduty"
    read_capabilities = ("incident_state",)
    write_capabilities = ("acknowledge_incident", "resolve_incident")

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.api_key = credentials.get("PAGERDUTY_API_KEY")
        self.from_email = credentials.get("PAGERDUTY_FROM_EMAIL")

    def _headers(self, need_from: bool = False) -> Dict[str, str]:
        headers = {
            "Authorization": f"Token token={self.api_key or ''}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }
        if need_from:
            headers["From"] = self.from_email or ""
        return headers

    def _request(self, method: str, path: str, body: Any = None, need_from: bool = False) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"{API_URL}{path}", data=data, headers=self._headers(need_from), method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise PagerDutyError(f"PagerDuty API {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}") from exc

    def authenticate(self) -> bool:
        if not self.api_key:
            return False
        try:
            self._request("GET", "/abilities")
            return True
        except PagerDutyError:
            return False

    def locate(self, resource: str) -> Dict[str, Any]:
        if not self.api_key:
            return {}
        try:
            resp = self._request("GET", f"/services?query={urllib.parse.quote(resource)}")
        except PagerDutyError:
            return {}
        services = resp.get("services", []) if isinstance(resp, dict) else []
        if not services:
            return {}
        first = services[0]
        if not first.get("id"):
            return {}
        return {"service_id": first["id"], "name": first.get("name", "")}

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        handle = self.locate(resource)
        if not handle:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
        status_query = "&".join(f"statuses[]={s}" for s in _OPEN_STATUSES)
        path = f"/incidents?service_ids[]={handle['service_id']}&{status_query}"
        try:
            resp = self._request("GET", path)
        except PagerDutyError:
            return ResourceState(
                resource, ConnectorState.UNKNOWN,
                {"service_id": handle["service_id"], "name": handle["name"], "error": "could not fetch incidents"},
            )
        incidents = resp.get("incidents", []) if isinstance(resp, dict) else []
        if not incidents:
            return ResourceState(
                resource, ConnectorState.HEALTHY,
                {"service_id": handle["service_id"], "name": handle["name"], "open_incidents": []},
            )
        open_incidents = [
            {"id": inc.get("id"), "title": inc.get("title", ""), "status": inc.get("status", "")}
            for inc in incidents
        ]
        # A still-triggered (unacknowledged) incident is worse than one
        # someone's already on -- surface the worst state actually present.
        state = ConnectorState.FAILED if any(i["status"] == "triggered" for i in open_incidents) else ConnectorState.DEGRADED
        return ResourceState(
            resource, state,
            {"service_id": handle["service_id"], "name": handle["name"], "open_incidents": open_incidents},
        )

    def acknowledge_incident(self, incident_id: str) -> Dict[str, Any]:
        return self._update_incident_status(incident_id, "acknowledged")

    def resolve_incident(self, incident_id: str) -> Dict[str, Any]:
        return self._update_incident_status(incident_id, "resolved")

    def _update_incident_status(self, incident_id: str, status: str) -> Dict[str, Any]:
        if not self.from_email:
            raise PagerDutyError("PAGERDUTY_FROM_EMAIL not configured -- required so PagerDuty can identify who made this change")
        body = {"incident": {"type": "incident_reference", "status": status}}
        resp = self._request("PUT", f"/incidents/{incident_id}", body=body, need_from=True)
        return resp.get("incident", resp) if isinstance(resp, dict) else resp
