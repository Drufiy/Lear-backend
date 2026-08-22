"""Grafana connector (Sprint 2 Tier 3, PRASH_V2.md §7b).

Read-only for this sprint. Unlike Datadog, Grafana has no fixed API host --
every install (self-hosted, or a Grafana Cloud org like myorg.grafana.net)
has its own URL, so GRAFANA_URL is a required credential, not a fallback
default. Auth is a Bearer token (a legacy API key or, on newer Grafana, a
service account token) -- the header is identical either way, so this
connector doesn't need to know which kind it was given.

Grafana's closest analog to a Datadog monitor or a GitHub Actions run's
conclusion is an alert rule: it has a name/uid and evaluates to a state.
`resource` is therefore an alert rule uid or title, resolved by listing
`/api/v1/provisioning/alert-rules` and matching either field (first match
wins -- same "good enough for v1" posture as every other connector's
locate()). Known limitation, not silently glossed over: that endpoint has
no server-side filter in the stable API, so locate() lists every rule in
the org on each call -- fine for a v1 read, worth revisiting if this is
ever used against an org with thousands of rules. Current firing state
comes from the unified-alerting Alertmanager-compatible endpoint
(`/api/alertmanager/grafana/api/v2/alerts`), matched by the `alertname`
label, which Grafana sets to the rule's title by default.

fetch_logs() deliberately does NOT do full-text log search -- that's Loki,
a separate product with its own query language and a per-install datasource
UID this connector has no generic way to discover. Instead it returns
Grafana's own annotation timeline (`/api/annotations`, filtered by tag),
which is a real, always-available signal (deploy markers, alert state
changes, manual notes) rather than a promise of log search this connector
can't actually keep.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping

from .base import Connector, ConnectorState, ResourceState

_ALERT_STATE_MAP = {
    "active": ConnectorState.FAILED,
    "suppressed": ConnectorState.DEGRADED,
    "unprocessed": ConnectorState.UNKNOWN,
}


class GrafanaError(RuntimeError):
    pass


class GrafanaConnector(Connector):
    name = "grafana"
    read_capabilities = ("alert_state", "annotations")
    write_capabilities = ("silence_alert",)

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        raw_url = credentials.get("GRAFANA_URL") or ""
        self.url = raw_url.rstrip("/")
        self.api_key = credentials.get("GRAFANA_API_KEY")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key or ''}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        req = urllib.request.Request(f"{self.url}{path}", data=json.dumps(body).encode("utf-8") if body is not None else None, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise GrafanaError(f"Grafana API {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}") from exc

    def authenticate(self) -> bool:
        if not self.url or not self.api_key:
            return False
        try:
            self._request("GET", "/api/org")
            return True
        except GrafanaError:
            return False

    def locate(self, resource: str) -> Dict[str, Any]:
        if not self.url or not self.api_key:
            return {}
        try:
            rules = self._request("GET", "/api/v1/provisioning/alert-rules")
        except GrafanaError:
            return {}
        if not isinstance(rules, list):
            return {}
        resource_lower = resource.lower()
        for rule in rules:
            if rule.get("uid") == resource or (rule.get("title") or "").lower() == resource_lower:
                return {"uid": rule.get("uid"), "title": rule.get("title", "")}
        return {}

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        handle = self.locate(resource)
        if not handle:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
        try:
            alerts = self._request("GET", "/api/alertmanager/grafana/api/v2/alerts")
        except GrafanaError:
            return ResourceState(
                resource, ConnectorState.UNKNOWN,
                {"uid": handle["uid"], "title": handle["title"], "error": "could not fetch alert state"},
            )
        matching = [
            a for a in (alerts if isinstance(alerts, list) else [])
            if (a.get("labels") or {}).get("alertname") == handle["title"]
        ]
        if not matching:
            return ResourceState(resource, ConnectorState.HEALTHY, {"uid": handle["uid"], "title": handle["title"], "alert_state": "none"})
        alert_state = (matching[0].get("status") or {}).get("state", "unknown")
        state = _ALERT_STATE_MAP.get(alert_state, ConnectorState.UNKNOWN)
        return ResourceState(
            resource, state,
            {"uid": handle["uid"], "title": handle["title"], "alert_state": alert_state, "active_alert_count": len(matching)},
        )

    def fetch_logs(self, resource: str, tags: list[str] | None = None, minutes: int = 60, limit: int = 50, **kwargs: Any) -> list[str]:
        if not self.url or not self.api_key:
            return []
        tag_list = tags if tags is not None else [resource]
        now_ms = int(time.time() * 1000)
        from_ms = now_ms - minutes * 60_000
        tag_query = "&".join(f"tags={urllib.parse.quote(t)}" for t in tag_list)
        path = f"/api/annotations?{tag_query}&from={from_ms}&to={now_ms}&limit={limit}"
        try:
            resp = self._request("GET", path)
        except GrafanaError:
            return []
        annotations = resp if isinstance(resp, list) else []
        lines = []
        for ann in annotations:
            ts = ann.get("time", "")
            text = ann.get("text", "")
            line = f"{ts} {text}".strip()
            if line:
                lines.append(line)
        return lines

    def silence_alert(self, resource: str, minutes: int = 60) -> Dict[str, Any]:
        """Create a time-bounded silence via Grafana's Alertmanager-compatible
        silences API. Write action added 2026-08-19 (PRASH_V2.md §7b): same
        role as Datadog's mute_monitor -- stop the paging noise, don't touch
        whatever's actually firing. Matched by the `alertname` label, same
        as poll_state()'s own matching logic, so a silence created here
        actually covers the alert instances poll_state() reads."""
        handle = self.locate(resource)
        if not handle:
            raise GrafanaError(f"alert rule not found: {resource}")
        now = datetime.now(timezone.utc)
        body = {
            "matchers": [{"name": "alertname", "value": handle["title"], "isRegex": False}],
            "startsAt": now.isoformat(),
            "endsAt": (now + timedelta(minutes=minutes)).isoformat(),
            "createdBy": "prash",
            "comment": "Silenced by Prash",
        }
        return self._request("POST", "/api/alertmanager/grafana/api/v2/silences", body=body)
