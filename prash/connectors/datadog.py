"""Datadog connector (Sprint 2 Tier 3, PRASH_V2.md §7b).

Stdlib-only urllib, same convention as github.py/gitlab.py/vercel.py --
Datadog's REST API needs nothing a plain HTTP client can't do.

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

Full autonomous loop (CONNECTOR_REWRITE_SPEC §4a/§4b/§4c, milestones
M2/M4): watch() returns a per-monitor WatchHandle that diffs per-group
monitor states on every poll() and emits ConnectorEvents for transitions;
get_stats() rebuilds a normalized timeline from Events API v2 plus an
optional metric-query context point. Writes: mute_monitor (SAFE, time-
bounded silence) and post_event (the primitive behind the APPROVAL-gated
datadog-alert action).

Request plumbing: transient failures (429/5xx, network, timeout) retry
with capped exponential backoff -- a 429's Retry-After wins when present;
permanent ones (403/404) raise immediately; a 401 gets one environment
re-read first (API key rotation) before it's treated as permanent.
Timeouts are per-endpoint: 10s for single-document monitor/validate
reads, 30s for search endpoints that legitimately take longer.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .base import Connector, ConnectorEvent, ConnectorState, ResourceState, WatchHandle

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

_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_CAP = 30.0
DEFAULT_TIMEOUT = 30
SHORT_TIMEOUT = 10  # single-document monitor/validate reads, not searches

# Events API v2 source_type_name -> our normalized event_type (§4c).
_EVENT_TYPE_MAP = {"alert": "monitor_alert", "monitor": "monitor_alert", "deploy": "deploy_event"}


class DatadogError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> Optional[datetime]:
    """Best-effort Datadog timestamp -> aware UTC datetime.

    Handles epoch seconds, epoch milliseconds (pointlist), and ISO-8601
    strings (with or without the Z suffix).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 1e11:  # milliseconds
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.replace(".", "", 1).isdigit():
        return _parse_ts(float(text))
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _metric_expr(monitor_query: str) -> Optional[str]:
    """Strip a monitor alert query down to its metric expression.

    `avg(last_5m):avg:system.cpu.user{*} by {host} > 90` ->
    `avg:system.cpu.user{*} by {host}` -- already valid /api/v1/query syntax.
    """
    match = re.match(r"^[a-zA-Z_]+(?:\.[a-zA-Z_]+)*\([^)]*\):(.+)$", monitor_query.strip())
    if not match:
        return None
    expr = re.split(r"\s*(?:>=|<=|!=|==|>|<)\s*-?[\d.]+", match.group(1), maxsplit=1)[0].strip()
    return expr or None


def _series_stats(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize a /api/v1/query response: max/mean across all series points."""
    points: List[Tuple[datetime, float]] = []
    for series in resp.get("series", []) or []:
        for point in series.get("pointlist", []) or []:
            if len(point) < 2 or point[1] is None:
                continue
            ts = _parse_ts(point[0])
            if ts is not None:
                points.append((ts, float(point[1])))
    if not points:
        return {}
    peak_ts, peak_val = max(points, key=lambda pair: pair[1])
    return {
        "max": round(peak_val, 4),
        "mean": round(sum(v for _, v in points) / len(points), 4),
        "peak_at": peak_ts.isoformat(),
        "points": len(points),
    }


class _DatadogWatchHandle(WatchHandle):
    """Per-monitor watch handle: one poll() = one monitor GET, diffed per group."""

    def __init__(
        self,
        connector: "DatadogConnector",
        target: str,
        monitor_id: Any,
        monitor_name: str,
        interval: int,
        last_state: Dict[str, str],
        monitor_query: Optional[str],
    ):
        self.connector = connector.name
        self.target = target
        self.interval = interval
        self.monitor_id = monitor_id
        self.monitor_name = monitor_name
        self._dd = connector
        self._last_state = last_state  # {group_key: overall_state string}
        self._monitor_query = monitor_query

    def poll(self) -> List[ConnectorEvent]:
        states, monitor_query = self._dd._monitor_groups(self.monitor_id)
        if monitor_query:
            self._monitor_query = monitor_query
        events: List[ConnectorEvent] = []
        for group, status in sorted(states.items()):
            previous = self._last_state.get(group)
            self._last_state[group] = status
            if previous is None or previous == status:
                # Brand-new group (or unchanged state): baseline, not a transition.
                continue
            events.append(
                self._dd._transition_event(self.monitor_id, self.monitor_name, group, previous, status, self._monitor_query)
            )
        return events


class DatadogConnector(Connector):
    name = "datadog"
    read_capabilities = ("monitor_state", "logs", "watch", "stats")
    write_capabilities = ("mute_monitor", "alert")

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

    def _refresh_credentials(self) -> bool:
        """Re-read the Datadog keys from the environment (API key rotation).

        Returns True when at least one key actually changed, i.e. a retry
        has a chance of succeeding. Absent env vars fall back to the
        current values so a partial rotation can't blank out credentials.
        """
        new_api = os.environ.get("DATADOG_API_KEY") or self.api_key
        new_app = os.environ.get("DATADOG_APP_KEY") or self.app_key
        changed = (bool(new_api) and new_api != self.api_key) or (bool(new_app) and new_app != self.app_key)
        self.api_key = new_api
        self.app_key = new_app
        return changed

    @staticmethod
    def _backoff_seconds(attempt: int, exc: urllib.error.HTTPError) -> float:
        """Capped exponential backoff; a 429's Retry-After header wins when present."""
        if exc.code == 429:
            headers = getattr(exc, "headers", None)
            retry_after = headers.get("Retry-After") if headers is not None else None
            if retry_after:
                try:
                    return float(retry_after)
                except (TypeError, ValueError):
                    pass
        return min(2 ** attempt, _BACKOFF_CAP)

    def _request(self, method: str, path: str, body: Any = None, need_app_key: bool = True,
                 timeout: int = DEFAULT_TIMEOUT) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        rotated = False
        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, headers=self._headers(need_app_key), method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                message = f"Datadog API {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}"
                if exc.code == 401 and not rotated:
                    # The key may have been rotated since startup; re-read the
                    # environment once before treating this as permanent.
                    rotated = True
                    if self._refresh_credentials():
                        continue
                    raise DatadogError(message) from exc
                if exc.code in _TRANSIENT_STATUS and attempt < _MAX_RETRIES:
                    time.sleep(self._backoff_seconds(attempt, exc))
                    attempt += 1
                    continue
                raise DatadogError(message) from exc
            except (socket.timeout, urllib.error.URLError) as exc:
                if attempt < _MAX_RETRIES:
                    time.sleep(min(2 ** attempt, _BACKOFF_CAP))
                    attempt += 1
                    continue
                raise DatadogError(f"Datadog API unreachable: {exc}") from exc

    def authenticate(self) -> bool:
        # /v1/validate only checks the API key (no app key needed) -- the
        # cheapest possible real auth check, same role GitHub's /user and
        # GitLab's /user play here.
        if not self.api_key:
            return False
        try:
            resp = self._request("GET", "/api/v1/validate", need_app_key=False, timeout=SHORT_TIMEOUT)
            return bool(resp.get("valid"))
        except DatadogError:
            return False

    def locate(self, resource: str) -> Dict[str, Any]:
        if not self.api_key or not self.app_key:
            return {}
        try:
            if resource.isdigit():
                monitor = self._request("GET", f"/api/v1/monitor/{resource}", timeout=SHORT_TIMEOUT)
            else:
                query = urllib.parse.quote(resource)
                resp = self._request("GET", f"/api/v1/monitor/search?query={query}", timeout=SHORT_TIMEOUT)
                monitors = resp.get("monitors", []) if isinstance(resp, dict) else []
                if not monitors:
                    return {}
                monitor = monitors[0]
        except DatadogError:
            return {}
        if not monitor.get("id"):
            return {}
        return {"monitor_id": monitor["id"], "name": monitor.get("name", ""), "monitor": monitor}

    def _monitor_groups(self, monitor_id: Any) -> Tuple[Dict[str, str], Optional[str]]:
        """Fetch a monitor with all group states.

        Returns ({group_key: overall_state}, monitor_query). Multi-alert
        monitors report one key per scope (e.g. "host:web-1"); single-state
        monitors report a single "" key. Group statuses reuse the same
        overall_state vocabulary ("OK"/"Alert"/"Warn"/...).
        """
        monitor = self._request("GET", f"/api/v1/monitor/{monitor_id}?group_states=all", timeout=SHORT_TIMEOUT)
        monitor = monitor if isinstance(monitor, dict) else {}
        states: Dict[str, str] = {}
        for group in (monitor.get("state") or {}).get("groups") or []:
            if not isinstance(group, dict):
                continue
            status = group.get("status")
            if isinstance(status, dict):
                status = status.get("status")
            states[str(group.get("name") or "")] = str(status or "Unknown")
        if not states:
            overall = monitor.get("overall_state") or monitor.get("status") or "Unknown"
            states = {"": str(overall)}
        return states, monitor.get("query") or None

    def _metric_context(self, monitor_query: Optional[str], minutes: int = 15) -> Optional[Dict[str, Any]]:
        """Best-effort underlying metric snapshot for a firing monitor.

        Correlation context for the diagnosis brain -- a failure here never
        blocks the transition event it decorates.
        """
        if not monitor_query:
            return None
        expr = _metric_expr(monitor_query)
        if not expr:
            return None
        to_ts = int(time.time())
        from_ts = to_ts - minutes * 60
        try:
            resp = self._request(
                "GET", f"/api/v1/query?from={from_ts}&to={to_ts}&query={urllib.parse.quote(expr)}",
                timeout=SHORT_TIMEOUT,
            )
        except DatadogError:
            return None
        stats = _series_stats(resp if isinstance(resp, dict) else {})
        if not stats:
            return None
        stats.update({"query": expr, "from": from_ts, "to": to_ts, "response": resp})
        return stats

    def _transition_event(self, monitor_id: Any, name: str, group: str,
                          previous: str, current: str,
                          monitor_query: Optional[str]) -> ConnectorEvent:
        if current == "OK":
            event_type = "monitor_recovered"
        elif _STATE_MAP.get(current, ConnectorState.UNKNOWN) in (ConnectorState.FAILED, ConnectorState.DEGRADED):
            event_type = "monitor_alert"
        else:
            event_type = "monitor_state_changed"
        scope = f" [{group}]" if group else ""
        if event_type == "monitor_recovered":
            summary = f"Monitor '{name}'{scope} recovered to OK"
        elif event_type == "monitor_alert":
            summary = f"Monitor '{name}'{scope} entered {current} state"
        else:
            summary = f"Monitor '{name}'{scope} state changed: {previous} -> {current}"
        raw: Dict[str, Any] = {
            "monitor_id": monitor_id,
            "monitor_name": name,
            "group": group or None,
            "previous_state": previous,
            "current_state": current,
        }
        if event_type == "monitor_alert":
            metric = self._metric_context(monitor_query)
            if metric:
                raw["metric"] = metric
        return ConnectorEvent(
            timestamp=_utcnow(),
            connector=self.name,
            event_type=event_type,
            summary=summary,
            raw=raw,
        )

    def watch(self, target: str, interval: int = 30) -> WatchHandle:
        """Begin monitoring a monitor (CONNECTOR_REWRITE_SPEC §4a).

        The returned handle polls the monitor endpoint (with all group
        states, so multi-alert monitors diff per scope) and emits
        ConnectorEvents only for state transitions. Multiple monitors =
        multiple handles; the shared watcher loop owns the cadence.
        """
        handle = self.locate(target)
        if not handle:
            raise DatadogError(f"monitor not found: {target}")
        monitor_id = handle["monitor_id"]
        try:
            states, monitor_query = self._monitor_groups(monitor_id)
        except DatadogError:
            # group_states fetch failed; fall back to the search/get payload.
            monitor = handle.get("monitor") or {}
            states = {"": str(monitor.get("overall_state") or monitor.get("status") or "Unknown")}
            monitor_query = monitor.get("query") or None
        return _DatadogWatchHandle(
            self,
            target=target,
            monitor_id=monitor_id,
            monitor_name=handle.get("name") or target,
            interval=interval,
            last_state=states,
            monitor_query=monitor_query,
        )

    def get_stats(self, target: str, since: Optional[datetime] = None,
                  include_metrics: bool = True) -> List[ConnectorEvent]:
        """Normalized timeline for a monitor (CONNECTOR_REWRITE_SPEC §4a).

        Sources: Events API v2 (alert/deploy/custom events on the monitor)
        plus one metric-spike context event from the monitor's own query
        when include_metrics is set. Ascending by timestamp, everything
        after `since` (default: the last hour). [] when the monitor doesn't
        resolve or the API fails -- same swallow-as-sentinel posture as
        locate()/fetch_logs().
        """
        if since is None:
            since = _utcnow() - timedelta(hours=1)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        handle = self.locate(target)
        if not handle:
            return []
        monitor_id = handle["monitor_id"]
        monitor_name = handle.get("name") or target
        events = self._monitor_events(monitor_id, monitor_name, since)
        if include_metrics:
            spike = self._metric_spike_event(handle.get("monitor") or {}, monitor_id, monitor_name, since)
            if spike:
                events.append(spike)
        events.sort(key=lambda event: event["timestamp"])
        return events

    def _monitor_events(self, monitor_id: Any, monitor_name: str, since: datetime) -> List[ConnectorEvent]:
        body = {
            "filter": {
                "query": f"monitor_id:{monitor_id}",
                "from": since.isoformat(),
                "to": _utcnow().isoformat(),
            },
            "sort": "timestamp",
            "page": {"limit": 100},
        }
        try:
            resp = self._request("POST", "/api/v2/events/search", body=body)
        except DatadogError:
            return []
        events: List[ConnectorEvent] = []
        for item in resp.get("data", []) if isinstance(resp, dict) else []:
            attrs = item.get("attributes", {}) if isinstance(item, dict) else {}
            ts = _parse_ts(attrs.get("timestamp"))
            if ts is None:
                continue
            source = str(attrs.get("source_type_name") or attrs.get("source") or "").lower()
            title = attrs.get("title") or attrs.get("message") or "(untitled event)"
            events.append(ConnectorEvent(
                timestamp=ts,
                connector=self.name,
                event_type=_EVENT_TYPE_MAP.get(source, "event"),
                summary=str(title),
                raw={"event_id": item.get("id"), "attributes": attrs, "monitor_name": monitor_name},
            ))
        # Belt-and-braces: the events search API already filters on `from`,
        # but a provider-side slip must not leak pre-window events into the
        # brain's timeline.
        return [event for event in events if event["timestamp"] >= since]

    def _metric_spike_event(self, monitor: Dict[str, Any], monitor_id: Any,
                            monitor_name: str, since: datetime) -> Optional[ConnectorEvent]:
        """One metric_spike context event summarizing the monitor's own metric window."""
        query = monitor.get("query")
        if not query:
            return None
        expr = _metric_expr(str(query))
        if not expr:
            return None
        to_ts = _utcnow()
        from_ts = max(since, to_ts - timedelta(hours=6))
        try:
            resp = self._request(
                "GET",
                f"/api/v1/query?from={int(from_ts.timestamp())}&to={int(to_ts.timestamp())}&query={urllib.parse.quote(expr)}",
                timeout=SHORT_TIMEOUT,
            )
        except DatadogError:
            return None
        stats = _series_stats(resp if isinstance(resp, dict) else {})
        if not stats:
            return None
        minutes = max(1, int((to_ts - from_ts).total_seconds() // 60))
        return ConnectorEvent(
            timestamp=_parse_ts(stats.get("peak_at")) or to_ts,
            connector=self.name,
            event_type="metric_spike",
            summary=f"Metric '{expr}' peaked at {stats.get('max')} over the last {minutes}m",
            raw={"monitor_id": monitor_id, "monitor_name": monitor_name, "query": expr,
                 "stats": stats, "response": resp},
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

    def poll_state(self, resource: str, **kwargs: Any) -> ResourceState:
        handle = self.locate(resource)
        if not handle:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
        monitor = handle.get("monitor") or {}
        # /api/v1/monitor/{id} (numeric resource) returns `overall_state`;
        # /api/v1/monitor/search (name lookup -- what every real user actually
        # does, since nobody knows a monitor's numeric id offhand) returns the
        # same value under `status` instead. Checking only overall_state made
        # every name-searched monitor silently report "unknown" regardless of
        # its real state -- found live, 2026-08-24, testing against a monitor
        # deliberately driven into Alert state.
        overall_state = monitor.get("overall_state") or monitor.get("status", "Unknown")
        state = _STATE_MAP.get(overall_state, ConnectorState.UNKNOWN)
        return ResourceState(
            resource,
            state,
            {"monitor_id": handle["monitor_id"], "name": handle["name"], "overall_state": overall_state},
        )

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
        return self._request("POST", f"/api/v1/monitor/{handle['monitor_id']}/mute",
                             body={"end": end_ts}, timeout=SHORT_TIMEOUT)

    def post_event(self, title: str, text: str, tags: Optional[List[str]] = None,
                   priority: str = "normal") -> Dict[str, Any]:
        """Post an event to the Datadog event stream (Events API v2) -- the
        primitive behind the APPROVAL-gated datadog-alert action. The event
        is team-visible and can't be deleted through the API, which is why
        the action that calls this is approval-tier rather than safe."""
        attributes: Dict[str, Any] = {"title": title, "text": text, "priority": priority}
        if tags:
            attributes["tags"] = list(tags)
        return self._request("POST", "/api/v2/events",
                             body={"data": {"type": "event", "attributes": attributes}})

    def get_event(self, event_id: Any) -> Dict[str, Any]:
        """Fetch one event by id -- how the datadog-alert action verifies a
        posted alert actually landed."""
        return self._request("GET", f"/api/v2/events/{event_id}", timeout=SHORT_TIMEOUT)

    def list_monitors(self, query: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Resolve watch targets: a named search, or every monitor (capped).

        The datadog watch loop uses this for DATADOG_WATCH_MONITORS=all --
        polling every monitor by default would be a rate-limit hazard, so
        watching all is always an explicit choice.
        """
        if query:
            resp = self._request("GET", f"/api/v1/monitor/search?query={urllib.parse.quote(query)}",
                                 timeout=SHORT_TIMEOUT)
            monitors = resp.get("monitors", []) if isinstance(resp, dict) else []
        else:
            monitors = self._request("GET", "/api/v1/monitor", timeout=SHORT_TIMEOUT)
        resolved: List[Dict[str, Any]] = []
        for monitor in monitors if isinstance(monitors, list) else []:
            if isinstance(monitor, dict) and monitor.get("id"):
                resolved.append({"monitor_id": monitor["id"], "name": monitor.get("name", "")})
            if len(resolved) >= limit:
                break
        return resolved
