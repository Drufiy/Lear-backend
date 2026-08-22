"""Datadog connector (Sprint 2 Tier 3, PRASH_V2.md §7b).

Read-only for this sprint, same posture every connector shipped with before
write actions were added later. Stdlib-only urllib, same convention as
github.py/gitlab.py/vercel.py -- Datadog's REST API needs nothing a plain
HTTP client can't do.

Datadog's core "is something wrong" primitive is a monitor, not a raw
service/host: a monitor already tracks one alerting condition and exposes a
single rolled-up `overall_state`, which maps onto ConnectorState the same
way a GitHub Actions run's conclusion does. `resource` is therefore a
monitor id (numeric string) or a monitor name (resolved via search, first
match wins -- same "good enough for v1, tighten later" posture as every
other connector's locate()). Logs have no equivalent single-endpoint
lookup by monitor, so fetch_logs() takes an explicit `query` kwarg (a
Datadog log search query) and falls back to searching on the resource
string itself if none is given.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Mapping

from .base import Connector, ConnectorState, ResourceState

# Datadog's own overall_state vocabulary for monitors (v1 API). "Alert" is a
# firing monitor -- the direct analog of CrashLoopBackOff/FAILED elsewhere.
_STATE_MAP = {
    "OK": ConnectorState.HEALTHY,
    "Alert": ConnectorState.FAILED,
    "Warn": ConnectorState.DEGRADED,
    "No Data": ConnectorState.UNKNOWN,
    "Skipped": ConnectorState.UNKNOWN,
    "Ignored": ConnectorState.UNKNOWN,
    "Unknown": ConnectorState.UNKNOWN,
}


class DatadogError(RuntimeError):
    pass


class DatadogConnector(Connector):
    name = "datadog"
    read_capabilities = ("monitor_state", "logs")
    write_capabilities = ("mute_monitor",)

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.api_key = credentials.get("DATADOG_API_KEY")
        self.app_key = credentials.get("DATADOG_APP_KEY")
        # Datadog runs region-isolated sites (US1 = datadoghq.com, EU =
        # datadoghq.eu, US3/US5/AP1 have their own hosts too) -- a customer
        # on a non-default site would otherwise get silent 403s against the
        # wrong region with no clue why. Blank/absent = default US1, same
        # "blank is absent" contract every other optional key in this repo
        # follows (see the 2026-08-13 KUBECONFIG fix in log_fetcher.py).
        site = credentials.get("DATADOG_SITE") or "datadoghq.com"
        self.base_url = f"https://api.{site}"

    def _headers(self, need_app_key: bool) -> Dict[str, str]:
        headers = {"DD-API-KEY": self.api_key or "", "Content-Type": "application/json"}
        if need_app_key:
            headers["DD-APPLICATION-KEY"] = self.app_key or ""
        return headers

    def _request(self, method: str, path: str, body: Any = None, need_app_key: bool = True) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(need_app_key), method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise DatadogError(f"Datadog API {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}") from exc

    def authenticate(self) -> bool:
        # /v1/validate only checks the API key (no app key needed) -- the
        # cheapest possible real auth check, same role GitHub's /user and
        # GitLab's /user play here.
        if not self.api_key:
            return False
        try:
            resp = self._request("GET", "/api/v1/validate", need_app_key=False)
            return bool(resp.get("valid"))
        except DatadogError:
            return False

    def locate(self, resource: str) -> Dict[str, Any]:
        if not self.api_key or not self.app_key:
            return {}
        try:
            if resource.isdigit():
                monitor = self._request("GET", f"/api/v1/monitor/{resource}")
            else:
                query = urllib.parse.quote(resource)
                resp = self._request("GET", f"/api/v1/monitor/search?query={query}")
                monitors = resp.get("monitors", []) if isinstance(resp, dict) else []
                if not monitors:
                    return {}
                monitor = monitors[0]
        except DatadogError:
            return {}
        if not monitor.get("id"):
            return {}
        return {"monitor_id": monitor["id"], "name": monitor.get("name", ""), "monitor": monitor}

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        handle = self.locate(resource)
        if not handle:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
        monitor = handle.get("monitor") or {}
        overall_state = monitor.get("overall_state", "Unknown")
        state = _STATE_MAP.get(overall_state, ConnectorState.UNKNOWN)
        return ResourceState(
            resource,
            state,
            {"monitor_id": handle["monitor_id"], "name": handle["name"], "overall_state": overall_state},
        )

    def fetch_logs(self, resource: str, query: str | None = None, minutes: int = 15, limit: int = 50, **kwargs: Any) -> list[str]:
        if not self.api_key or not self.app_key:
            return []
        body = {
            "filter": {"query": query or resource, "from": f"now-{minutes}m", "to": "now"},
            "sort": "-timestamp",
            "page": {"limit": limit},
        }
        try:
            resp = self._request("POST", "/api/v2/logs/events/search", body=body)
        except DatadogError:
            return []
        events = resp.get("data", []) if isinstance(resp, dict) else []
        lines = []
        for event in events:
            attrs = event.get("attributes", {}) if isinstance(event, dict) else {}
            ts = attrs.get("timestamp", "")
            msg = attrs.get("message", "")
            line = f"{ts} {msg}".strip()
            if line:
                lines.append(line)
        return lines

    def mute_monitor(self, resource: str, minutes: int = 60) -> Dict[str, Any]:
        """Mute a monitor for the given duration -- Datadog's own /mute
        endpoint, which silences alert notifications without touching
        whatever's actually wrong. Write action added 2026-08-19 (PRASH_V2.md
        §7b): the point isn't to fix the underlying issue (Datadog has no
        concept of "fixing" a metric), it's to stop the paging noise while a
        human or another action handles the real cause -- same role
        pagerduty-acknowledge plays for incidents."""
        handle = self.locate(resource)
        if not handle:
            raise DatadogError(f"monitor not found: {resource}")
        end_ts = int(time.time()) + minutes * 60
        return self._request("POST", f"/api/v1/monitor/{handle['monitor_id']}/mute", body={"end": end_ts})
