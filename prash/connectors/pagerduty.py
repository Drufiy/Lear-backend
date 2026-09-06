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

trigger_event() (added 2026-08-19, wired to the Gitleaks-escalation action)
uses a genuinely different PagerDuty mechanism from everything else in this
file: the Events API v2 (`events.pagerduty.com`, not `api.pagerduty.com`),
authenticated by a per-service integration/routing key
(PAGERDUTY_ROUTING_KEY), not the REST API key. This is intentional, not an
inconsistency to clean up -- creating a NEW incident from an external
system and updating the status of an EXISTING incident are different
PagerDuty products with different auth models; conflating them would mean
guessing at which key does what.

Full autonomous loop (CONNECTOR_REWRITE_SPEC §4a/§4b/§4c, Phase 3 rollout):
watch() returns a per-service WatchHandle that lists the service's incidents
each poll() and emits ConnectorEvents only on transitions -- new triggers,
acknowledgments, resolutions, and reassignments/escalations -- de-duplicated
by incident id + status + assignment signature across polls. get_stats()
normalizes either an incident's log-entry timeline or a service's incident
window (plus account change events as correlation context) into
ConnectorEvents. page_oncall() is the primitive behind the APPROVAL-gated
pagerduty-page action (Events API v2, routing key, dedup-keyed).

Request plumbing (mirrors datadog.py, Phase E): transient failures
(429/5xx, network, timeout) retry with capped exponential backoff -- a
429's Retry-After wins when present, which is how the 900 req/min account
limit is honored in practice; permanent ones (403/404) raise immediately; a
401 gets one environment re-read (API key rotation) before it's treated as
permanent. REST list endpoints paginate by limit/offset with a `more` flag
(not cursor-based) -- _paginate() walks them under a hard cap. Timeouts are
per-endpoint: 10s for single-document reads/writes, 30s for list queries.
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .base import Connector, ConnectorEvent, ConnectorState, ResourceState, WatchHandle

API_URL = "https://api.pagerduty.com"
EVENTS_URL = "https://events.pagerduty.com"

# Incidents in either of these statuses are still open -- someone hasn't
# declared the problem over yet. "resolved" is excluded on purpose: a
# resolved incident isn't evidence the service is currently unhealthy.
_OPEN_STATUSES = ("triggered", "acknowledged")

# Watch/stats need resolved incidents too -- the transition TO resolved is
# exactly the signal a watcher exists to deliver.
_WATCH_STATUSES = ("triggered", "acknowledged", "resolved")

_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_CAP = 30.0
DEFAULT_TIMEOUT = 30
SHORT_TIMEOUT = 10  # single-document reads/writes, not list queries

# LogEntry type -> normalized event_type (§4c).
_LOG_ENTRY_TYPE_MAP = {
    "trigger_log_entry": "incident_triggered",
    "ack_log_entry": "incident_acknowledged",
    "resolve_log_entry": "incident_resolved",
    "escalate_log_entry": "incident_escalated",
    "assign_log_entry": "incident_assigned",
    "un_ack_log_entry": "incident_unacknowledged",
    "notify_log_entry": "incident_notified",
    "annotate_log_entry": "incident_note",
}

# PagerDuty P1..P5 -> Prash severity vocabulary, for brain correlation
# (a P1 PagerDuty page and a FAILED k8s state should weigh the same).
_PRIORITY_SEVERITY = {"P1": "critical", "P2": "critical", "P3": "high", "P4": "medium", "P5": "low"}

_STATUS_EVENT_MAP = {
    "triggered": "incident_triggered",
    "acknowledged": "incident_acknowledged",
    "resolved": "incident_resolved",
}


class PagerDutyError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> Optional[datetime]:
    """Best-effort PagerDuty timestamp (ISO-8601) -> aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 1e11:  # epoch milliseconds
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


def _incident_severity(incident: Dict[str, Any]) -> str:
    """P1-P5 priority -> severity vocabulary; urgency is the fallback.

    A triggered incident with no priority object still has urgency, and
    "high urgency, no priority" is worth more than a bare "unknown".
    """
    priority = (incident.get("priority") or {}).get("summary")
    if priority:
        return _PRIORITY_SEVERITY.get(str(priority).upper(), "medium")
    return "high" if incident.get("urgency") == "high" else "low"


def _assignments_sig(incident: Dict[str, Any]) -> Tuple[str, ...]:
    return tuple(sorted(
        str((a.get("assignee") or {}).get("id") or "")
        for a in incident.get("assignments") or []
    ))


class _PagerDutyWatchHandle(WatchHandle):
    """Per-service watch handle: one poll() = one incident list, diffed per incident.

    Dedup contract (the whole point of the watcher): the same incident in
    the same state across polls is silent -- only a NEW trigger, a status
    transition, or a reassignment/escalation emits an event.
    """

    def __init__(self, connector: "PagerDutyConnector", target: str, service_id: str,
                 service_name: str, interval: int, last_state: Dict[str, Tuple[str, Tuple[str, ...]]]):
        self.connector = connector.name
        self.target = target
        self.interval = interval
        self.service_id = service_id
        self.service_name = service_name
        self._pd = connector
        self._last_state = last_state

    def poll(self) -> List[ConnectorEvent]:
        incidents = self._pd._service_incidents(self.service_id)
        events: List[ConnectorEvent] = []
        for incident in incidents:
            inc_id = str(incident.get("id") or "")
            if not inc_id:
                continue
            status = incident.get("status") or "unknown"
            sig = _assignments_sig(incident)
            previous = self._last_state.get(inc_id)
            self._last_state[inc_id] = (status, sig)
            if previous is None:
                # First sighting: an open incident is page-worthy; a resolved
                # one is history predating the watch -- baseline it silently.
                if status != "resolved":
                    events.append(self._pd._incident_event(incident, "incident_triggered", self.service_name))
                continue
            prev_status, prev_assignments = previous
            if prev_status == status and prev_assignments == sig:
                continue  # the core dedup guarantee: same incident, same state -> silence
            if status != prev_status:
                event_type = _STATUS_EVENT_MAP.get(status, "incident_state_changed")
            else:
                # Same status, different assignees: escalation to the next
                # rotation or a manual reassignment -- worth a fresh ping.
                event_type = "incident_escalated"
            events.append(self._pd._incident_event(incident, event_type, self.service_name, previous_status=prev_status))
        return events


class PagerDutyConnector(Connector):
    name = "pagerduty"
    read_capabilities = ("incident_state", "watch", "stats")
    write_capabilities = ("acknowledge_incident", "resolve_incident", "trigger_event", "page_oncall")

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.api_key = credentials.get("PAGERDUTY_API_KEY")
        self.from_email = credentials.get("PAGERDUTY_FROM_EMAIL")
        self.routing_key = credentials.get("PAGERDUTY_ROUTING_KEY")

    def _headers(self, need_from: bool = False) -> Dict[str, str]:
        headers = {
            "Authorization": f"Token token={self.api_key or ''}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.pagerduty+json;version=2",
        }
        if need_from:
            headers["From"] = self.from_email or ""
        return headers

    def _refresh_credentials(self) -> bool:
        """Re-read the REST credentials from the environment (key rotation).

        Returns True when the API key actually changed, i.e. a retry has a
        chance of succeeding. Absent env vars fall back to current values.
        """
        new_api = os.environ.get("PAGERDUTY_API_KEY") or self.api_key
        new_from = os.environ.get("PAGERDUTY_FROM_EMAIL") or self.from_email
        changed = bool(new_api) and new_api != self.api_key
        self.api_key = new_api
        self.from_email = new_from
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

    def _request(self, method: str, path: str, body: Any = None, need_from: bool = False,
                 timeout: int = DEFAULT_TIMEOUT) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        rotated = False
        attempt = 0
        while True:
            req = urllib.request.Request(f"{API_URL}{path}", data=data, headers=self._headers(need_from), method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                message = f"PagerDuty API {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}"
                if exc.code == 401 and not rotated:
                    # The key may have been rotated since startup; re-read the
                    # environment once before treating this as permanent.
                    rotated = True
                    if self._refresh_credentials():
                        continue
                    raise PagerDutyError(message) from exc
                if exc.code in _TRANSIENT_STATUS and attempt < _MAX_RETRIES:
                    time.sleep(self._backoff_seconds(attempt, exc))
                    attempt += 1
                    continue
                raise PagerDutyError(message) from exc
            except (socket.timeout, urllib.error.URLError) as exc:
                if attempt < _MAX_RETRIES:
                    time.sleep(min(2 ** attempt, _BACKOFF_CAP))
                    attempt += 1
                    continue
                raise PagerDutyError(f"PagerDuty API unreachable: {exc}") from exc

    def _events_request(self, method: str, path: str, body: Any) -> Any:
        """Events API v2 (events.pagerduty.com) with the same retry/backoff
        discipline as the REST path -- but its own auth model: the routing
        key travels IN the body, never as a REST Authorization header."""
        data = json.dumps(body).encode("utf-8")
        attempt = 0
        while True:
            req = urllib.request.Request(
                f"{EVENTS_URL}{path}", data=data,
                headers={"Content-Type": "application/json"}, method=method,
            )
            try:
                with urllib.request.urlopen(req, timeout=SHORT_TIMEOUT) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                message = f"PagerDuty Events API {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}"
                if exc.code in _TRANSIENT_STATUS and attempt < _MAX_RETRIES:
                    time.sleep(self._backoff_seconds(attempt, exc))
                    attempt += 1
                    continue
                raise PagerDutyError(message) from exc
            except (socket.timeout, urllib.error.URLError) as exc:
                if attempt < _MAX_RETRIES:
                    time.sleep(min(2 ** attempt, _BACKOFF_CAP))
                    attempt += 1
                    continue
                raise PagerDutyError(f"PagerDuty Events API unreachable: {exc}") from exc

    def _paginate(self, path: str, cap: int = 200) -> List[Dict[str, Any]]:
        """Walk a REST v2 list endpoint (limit/offset + `more` flag, NOT
        cursor-based) under a hard cap -- the rate-limit-friendly guard
        against a runaway list call. Understands the collection keys of the
        four endpoints this connector actually paginates."""
        items: List[Dict[str, Any]] = []
        offset = 0
        limit = 100
        while True:
            sep = "&" if "?" in path else "?"
            resp = self._request("GET", f"{path}{sep}offset={offset}&limit={limit}")
            if not isinstance(resp, dict):
                break
            batch = (resp.get("incidents") or resp.get("log_entries")
                     or resp.get("services") or resp.get("change_events") or [])
            items.extend(item for item in batch if isinstance(item, dict))
            if len(items) >= cap or not resp.get("more", False):
                break
            offset += limit
        return items[:cap]

    def authenticate(self) -> bool:
        if not self.api_key:
            return False
        try:
            self._request("GET", "/abilities", timeout=SHORT_TIMEOUT)
            return True
        except PagerDutyError:
            return False

    def locate(self, resource: str) -> Dict[str, Any]:
        if not self.api_key:
            return {}
        try:
            resp = self._request("GET", f"/services?query={urllib.parse.quote(resource)}", timeout=SHORT_TIMEOUT)
        except PagerDutyError:
            return {}
        services = resp.get("services", []) if isinstance(resp, dict) else []
        if not services:
            return {}
        first = services[0]
        if not first.get("id"):
            return {}
        return {"service_id": first["id"], "name": first.get("name", "")}

    def list_services(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Resolve watch targets for PAGERDUTY_WATCH_SERVICES=all (capped --
        watching every service pages on every trigger across the account,
        which must always be an explicit choice)."""
        return [
            {"service_id": service["id"], "name": service.get("name", "")}
            for service in self._paginate("/services", cap=limit)
            if service.get("id")
        ]

    def _service_incidents(self, service_id: str) -> List[Dict[str, Any]]:
        status_query = "&".join(f"statuses[]={s}" for s in _WATCH_STATUSES)
        path = (f"/incidents?service_ids[]={service_id}&{status_query}"
                f"&sort_by=created_at:desc&include[]=assignments")
        return self._paginate(path)

    def _incident_event(self, incident: Dict[str, Any], event_type: str,
                        service_name: str, previous_status: Optional[str] = None) -> ConnectorEvent:
        title = incident.get("title", "")
        severity = _incident_severity(incident)
        priority = (incident.get("priority") or {}).get("summary")
        urgency = incident.get("urgency")
        escalation = (incident.get("escalation_policy") or {}).get("summary")
        service = incident.get("service") if isinstance(incident.get("service"), dict) else {}
        if event_type == "incident_escalated":
            summary = f"Incident '{title}' on {service_name} escalated/reassigned"
        else:
            status_word = event_type.removeprefix("incident_")
            summary = f"Incident '{title}' on {service_name} {status_word} ({severity} severity"
            if urgency:
                summary += f", {urgency} urgency"
            summary += ")"
        raw: Dict[str, Any] = {
            "incident_id": incident.get("id"),
            "incident_key": incident.get("incident_key"),
            "service_id": service.get("id"),
            "service_name": service_name,
            "status": incident.get("status"),
            "previous_status": previous_status,
            "severity": severity,
            "priority": priority,
            "urgency": urgency,
            "escalation_policy": escalation,
            "incident": incident,
        }
        return ConnectorEvent(
            timestamp=_parse_ts(incident.get("last_status_change_at") or incident.get("created_at")) or _utcnow(),
            connector=self.name,
            event_type=event_type,
            summary=summary,
            raw=raw,
        )

    def watch(self, target: str, interval: int = 30) -> WatchHandle:
        """Begin watching a service (CONNECTOR_REWRITE_SPEC §4a).

        The returned handle lists the service's incidents (all statuses, so
        resolutions are visible) each poll() and emits ConnectorEvents only
        for transitions: new triggers, acknowledgments, resolutions, and
        reassignments/escalations -- de-duplicated across polls by incident
        id + status + assignment signature. Multiple services = multiple
        handles; the shared watcher loop owns the cadence.
        """
        handle = self.locate(target)
        if not handle:
            raise PagerDutyError(f"service not found: {target}")
        last_state: Dict[str, Tuple[str, Tuple[str, ...]]] = {}
        for incident in self._service_incidents(handle["service_id"]):
            inc_id = str(incident.get("id") or "")
            if inc_id:
                last_state[inc_id] = (incident.get("status") or "unknown", _assignments_sig(incident))
        return _PagerDutyWatchHandle(self, target, handle["service_id"], handle.get("name") or target, interval, last_state)

    def get_stats(self, target: str, since: Optional[datetime] = None,
                  include_change_events: bool = True) -> List[ConnectorEvent]:
        """Normalized timeline for a PagerDuty target (CONNECTOR_REWRITE_SPEC §4a).

        Two modes, resolved automatically: an incident id gets its full
        log-entry timeline (trigger/ack/escalate/resolve per entry); a
        service name/id gets its incident window (one event per incident)
        plus account-wide change events as deploy-correlation context --
        the /change_events endpoint has no service filter, so these are
        context, not per-service facts. Ascending by timestamp, everything
        after `since` (default: the last hour). [] when nothing resolves.
        """
        if since is None:
            since = _utcnow() - timedelta(hours=1)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        events = self._incident_log_events(target, since)
        if events is None:
            handle = self.locate(target)
            if not handle:
                return []
            events = self._service_window_events(handle, since, include_change_events)
        events.sort(key=lambda event: event["timestamp"])
        return events

    def _incident_log_events(self, target: str, since: datetime) -> Optional[List[ConnectorEvent]]:
        """Log-entry timeline for one incident, or None when `target` isn't
        an incident id (falls through to service mode)."""
        try:
            resp = self._request("GET", f"/incidents/{target}", timeout=SHORT_TIMEOUT)
        except PagerDutyError:
            return None
        incident = resp.get("incident", resp) if isinstance(resp, dict) else {}
        if not isinstance(incident, dict) or not incident.get("id"):
            return None
        entries = self._paginate(f"/incidents/{target}/log_entries?include[]=channels")
        events: List[ConnectorEvent] = []
        for entry in entries:
            ts = _parse_ts(entry.get("created_at"))
            if ts is None or ts < since:
                continue
            events.append(ConnectorEvent(
                timestamp=ts,
                connector=self.name,
                event_type=_LOG_ENTRY_TYPE_MAP.get(str(entry.get("type", "")), "log_entry"),
                summary=str(entry.get("summary") or entry.get("type") or "(log entry)"),
                raw={"entry_id": entry.get("id"), "log_entry": entry, "incident_id": target},
            ))
        return events

    def _service_window_events(self, handle: Dict[str, Any], since: datetime,
                               include_change_events: bool) -> List[ConnectorEvent]:
        service_id = handle["service_id"]
        service_name = handle.get("name") or service_id
        status_query = "&".join(f"statuses[]={s}" for s in _WATCH_STATUSES)
        until = _utcnow()
        path = (f"/incidents?service_ids[]={service_id}&{status_query}"
                f"&since={urllib.parse.quote(since.isoformat())}&until={urllib.parse.quote(until.isoformat())}"
                f"&sort_by=created_at:desc&include[]=assignments")
        events: List[ConnectorEvent] = []
        for incident in self._paginate(path):
            status = incident.get("status") or "unknown"
            events.append(self._incident_event(incident, _STATUS_EVENT_MAP.get(status, "incident_state_changed"), service_name))
        if include_change_events:
            try:
                resp = self._request(
                    "GET",
                    f"/change_events?since={urllib.parse.quote(since.isoformat())}&until={urllib.parse.quote(until.isoformat())}&limit=100",
                )
            except PagerDutyError:
                resp = {}
            for change in resp.get("change_events", []) if isinstance(resp, dict) else []:
                ts = _parse_ts(change.get("timestamp") or change.get("created_at"))
                if ts is None:
                    continue
                events.append(ConnectorEvent(
                    timestamp=ts,
                    connector=self.name,
                    event_type="change_event",
                    summary=str(change.get("summary") or "(change event)"),
                    raw={"change_event": change, "source": change.get("source"), "service_name": service_name},
                ))
        return events

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
        resp = self._request("PUT", f"/incidents/{incident_id}", body=body, need_from=True, timeout=SHORT_TIMEOUT)
        return resp.get("incident", resp) if isinstance(resp, dict) else resp

    def trigger_event(self, summary: str, source: str, severity: str = "critical", custom_details: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Create a brand new incident via the Events API v2 -- a different
        product from the REST /incidents endpoints above, with a different
        auth model (see the module docstring). Used when something Prash
        found needs to escalate to a human as a NEW paged incident, rather
        than acting on an existing one."""
        if not self.routing_key:
            raise PagerDutyError("PAGERDUTY_ROUTING_KEY not configured -- required to trigger a new incident via the Events API")
        body = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "payload": {"summary": summary, "source": source, "severity": severity, "custom_details": custom_details or {}},
        }
        req = urllib.request.Request(
            "https://events.pagerduty.com/v2/enqueue",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise PagerDutyError(f"PagerDuty Events API {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}") from exc

    def page_oncall(self, summary: str, source: str, severity: str = "critical",
                    dedup_key: Optional[str] = None,
                    custom_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Page the on-call engineer: a NEW incident via Events API v2 with a
        dedup key (same key updates the existing incident instead of stacking
        a second page). The primitive behind the APPROVAL-gated
        pagerduty-page action -- paging a human is irreversible (there is no
        un-page; the incident must be resolved by hand) and disruptive by
        design. Same auth model as trigger_event: routing key in the body,
        never the REST token. Distinct from trigger_event so the existing
        Gitleaks-escalation path stays untouched."""
        if not self.routing_key:
            raise PagerDutyError("PAGERDUTY_ROUTING_KEY not configured -- required to page on-call via the Events API")
        if severity not in ("critical", "error", "warning", "info"):
            raise PagerDutyError(f"invalid severity {severity!r}: must be critical, error, warning, or info")
        body: Dict[str, Any] = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "payload": {"summary": summary, "source": source, "severity": severity, "custom_details": custom_details or {}},
            "client": "Prash",
        }
        if dedup_key:
            body["dedup_key"] = dedup_key
        return self._events_request("POST", "/v2/enqueue", body=body)

    def find_incident_by_incident_key(self, incident_key: str, since: datetime) -> Optional[Dict[str, Any]]:
        """Find the incident an Events API trigger created, by dedup key --
        the Events API returns only the dedup_key (no incident id), so the
        pagerduty-page action's verify() scans the recent window for the
        matching incident_key."""
        status_query = "&".join(f"statuses[]={s}" for s in _WATCH_STATUSES)
        path = (f"/incidents?{status_query}"
                f"&since={urllib.parse.quote(since.isoformat())}&until={urllib.parse.quote(_utcnow().isoformat())}"
                f"&sort_by=created_at:desc")
        for incident in self._paginate(path):
            if incident.get("incident_key") == incident_key:
                return incident
        return None
