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

Full autonomous loop (CONNECTOR_REWRITE_SPEC §4a/§4b/§4c, Phase 3 rollout,
2026-09-09): watch() returns a per-alert-rule WatchHandle that lists the
rule's firing alert instances each poll() and emits ConnectorEvents only on
transitions -- new firings, silences/re-fires, and recoveries --
de-duplicated by alert instance (its label set minus `alertname`) + state +
startsAt across polls. A rule already firing when watch() starts baselines
silently (mirrors PagerDuty's service watch: start watching mid-incident
doesn't page immediately). get_stats() normalizes alert-rule state-change
annotations (`type=alert`, which carry prevState/newState) plus the rule's
currently-firing instances into ConnectorEvents.

Request plumbing (mirrors pagerduty.py, Phase E): transient failures
(429/5xx, network, timeout) retry with capped exponential backoff -- a 429's
Retry-After wins when present. This matters more here than on most
connectors: Grafana Cloud free tier hibernates when idle and answers the
first call after idle with a 503 "instance is loading" (documented in
scripts/testing/break_grafana.py), which a watch loop should ride out
rather than report as a poll failure. Permanent ones (403/404) raise
immediately; a 401 gets one environment re-read (token rotation) before
it's treated as permanent. Timeouts are per-endpoint: 10s for single-
document reads, 30s for list queries.
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

_ALERT_STATE_MAP = {
    "active": ConnectorState.FAILED,
    "suppressed": ConnectorState.DEGRADED,
    "unprocessed": ConnectorState.UNKNOWN,
}

_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_CAP = 30.0
DEFAULT_TIMEOUT = 30
SHORT_TIMEOUT = 10  # single-document reads, not list queries

# Two state vocabularies describe the same underlying thing: the
# Alertmanager-compatible alerts API uses "active"/"suppressed"/"unprocessed",
# while state-change annotations record Grafana's internal rule states
# ("OK", "Pending", "Alerting", ...). Both map onto the same three watch
# event types.
_ANNOTATION_STATE_EVENT_MAP = {
    "alerting": "alert_firing",
    "ok": "alert_recovered",
    "normal": "alert_recovered",
}


class GrafanaError(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> Optional[datetime]:
    """Best-effort Grafana timestamp -> aware UTC datetime. Handles ISO-8601
    (alerts' startsAt/updatedAt) and epoch milliseconds (annotations' time)."""
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


def _instance_key(alert: Dict[str, Any]) -> Optional[Tuple[Tuple[str, str], ...]]:
    """Stable identity for one alert instance: its label set minus
    `alertname` (which is the rule match itself). One rule can have several
    concurrently-firing instances (e.g. one per env/team); each is deduped
    and recovered independently."""
    labels = alert.get("labels")
    if not isinstance(labels, dict):
        return None
    return tuple(sorted((str(k), str(v)) for k, v in labels.items() if k != "alertname"))


class _GrafanaWatchHandle(WatchHandle):
    """Per-alert-rule watch handle: one poll() = one Alertmanager alerts list,
    diffed per alert instance.

    Dedup contract (the whole point of the watcher): the same instance in
    the same state across polls is silent -- only a NEW firing, a state
    transition, or a recovery emits an event. A previously-firing instance
    that vanishes from the list IS the recovery signal: resolved alerts
    leave the Alertmanager list entirely, there is no separate resolved
    listing to read -- so the recovery event is timestamped at detection
    time and says so honestly in raw.inferred.
    """

    def __init__(self, connector: "GrafanaConnector", target: str, rule_uid: str,
                 rule_title: str, interval: int,
                 last_state: Dict[Tuple[Tuple[str, str], ...], Tuple[str, str]]):
        self.connector = connector.name
        self.target = target
        self.interval = interval
        self.rule_uid = rule_uid
        self.rule_title = rule_title
        self._gf = connector
        self._last_state = last_state

    def poll(self) -> List[ConnectorEvent]:
        # raise_on_error=True: a failed fetch must NOT look like "everything
        # recovered" -- let it propagate so the shared loop skips this cycle
        # without pruning _last_state. See _rule_alerts' docstring.
        alerts = self._gf._rule_alerts(self.rule_title, raise_on_error=True)
        events: List[ConnectorEvent] = []
        seen: Dict[Tuple[Tuple[str, str], ...], Tuple[str, str]] = {}
        for alert in alerts:
            key = _instance_key(alert)
            if key is None:
                continue
            state = (alert.get("status") or {}).get("state") or "unknown"
            starts = str(alert.get("startsAt") or "")
            seen[key] = (state, starts)
            previous = self._last_state.get(key)
            self._last_state[key] = (state, starts)
            if previous is None:
                # First sighting mid-watch: a firing instance is page-worthy;
                # a non-firing one is background -- baseline it silently.
                # (watch() itself seeds silently, so this only fires for
                # instances that appear after the watch started.)
                if state == "active":
                    events.append(self._gf._alert_event(alert, "alert_firing", self.rule_title))
                continue
            prev_state, prev_starts = previous
            if prev_state == state and prev_starts == starts:
                continue  # the core dedup guarantee: same instance, same state -> silence
            if state == "active":
                # (re)entered the firing set -- from not-listed, suppressed, or unprocessed
                events.append(self._gf._alert_event(alert, "alert_firing", self.rule_title, previous_state=prev_state))
            else:
                # still listed but left the firing set (silenced/inhibited), or a
                # non-firing state change -- a silence is NOT a recovery.
                events.append(self._gf._alert_event(alert, "alert_state_changed", self.rule_title, previous_state=prev_state))
        for key in [k for k in self._last_state if k not in seen]:
            prev_state, _ = self._last_state.pop(key)
            if prev_state == "active":
                events.append(self._gf._recovery_event(self.rule_uid, self.rule_title, key))
        return events


class GrafanaConnector(Connector):
    name = "grafana"
    read_capabilities = ("alert_state", "annotations", "watch", "stats")
    write_capabilities = ("silence_alert",)

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        raw_url = credentials.get("GRAFANA_URL") or ""
        self.url = raw_url.rstrip("/")
        self.api_key = credentials.get("GRAFANA_API_KEY")

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key or ''}", "Content-Type": "application/json"}

    def _refresh_credentials(self) -> bool:
        """Re-read the token from the environment (rotation). Returns True
        when the key actually changed, i.e. a retry has a chance of
        succeeding. An absent env var falls back to the current value."""
        new_key = os.environ.get("GRAFANA_API_KEY") or self.api_key
        changed = bool(new_key) and new_key != self.api_key
        self.api_key = new_key
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

    def _request(self, method: str, path: str, body: Any = None, timeout: int = DEFAULT_TIMEOUT) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        rotated = False
        attempt = 0
        while True:
            req = urllib.request.Request(f"{self.url}{path}", data=data, headers=self._headers(), method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                message = f"Grafana API {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}"
                if exc.code == 401 and not rotated:
                    # The token may have been rotated since startup; re-read
                    # the environment once before treating this as permanent.
                    rotated = True
                    if self._refresh_credentials():
                        continue
                    raise GrafanaError(message) from exc
                if exc.code in _TRANSIENT_STATUS and attempt < _MAX_RETRIES:
                    time.sleep(self._backoff_seconds(attempt, exc))
                    attempt += 1
                    continue
                raise GrafanaError(message) from exc
            except (socket.timeout, urllib.error.URLError) as exc:
                if attempt < _MAX_RETRIES:
                    time.sleep(min(2 ** attempt, _BACKOFF_CAP))
                    attempt += 1
                    continue
                raise GrafanaError(f"Grafana API unreachable: {exc}") from exc

    def authenticate(self) -> bool:
        if not self.url or not self.api_key:
            return False
        try:
            self._request("GET", "/api/org", timeout=SHORT_TIMEOUT)
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

    def list_rules(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Resolve watch targets for GRAFANA_WATCH_RULES=all (capped --
        polling every rule in the org fires on every firing anywhere, which
        must always be an explicit choice)."""
        try:
            rules = self._request("GET", "/api/v1/provisioning/alert-rules")
        except GrafanaError:
            return []
        out: List[Dict[str, Any]] = []
        for rule in rules if isinstance(rules, list) else []:
            if isinstance(rule, dict) and rule.get("uid"):
                out.append({"uid": rule["uid"], "title": rule.get("title", "")})
                if len(out) >= limit:
                    break
        return out

    def _rule_alerts(self, rule_title: str, raise_on_error: bool = False) -> List[Dict[str, Any]]:
        """Current Alertmanager instances whose `alertname` label equals the
        rule title -- the same matching poll_state() uses, so a watcher and
        an investigate() call always agree on what "this rule is firing"
        means.

        raise_on_error controls what a failed fetch means. The watch handle's
        poll() MUST pass raise_on_error=True: there, "empty" is the recovery
        signal (a resolved instance simply drops out of the list), so
        swallowing a 5xx/timeout/401 to [] would make every firing instance
        look recovered -- a false stand-down, then a false re-page next cycle.
        Letting the error propagate instead lets run_watchhandle_loop skip the
        bad cycle WITHOUT mutating _last_state, matching Datadog/PagerDuty.
        poll_state()/get_stats() pass the default (False): a one-shot read has
        no prior state to corrupt, so [] on error is the safe degradation."""
        try:
            alerts = self._request("GET", "/api/alertmanager/grafana/api/v2/alerts")
        except GrafanaError:
            if raise_on_error:
                raise
            return []
        if not isinstance(alerts, list):
            return []
        return [
            a for a in alerts
            if isinstance(a, dict) and (a.get("labels") or {}).get("alertname") == rule_title
        ]

    def _alert_event(self, alert: Dict[str, Any], event_type: str, rule_title: str,
                     previous_state: Optional[str] = None) -> ConnectorEvent:
        state = (alert.get("status") or {}).get("state") or "unknown"
        labels = {str(k): str(v) for k, v in (alert.get("labels") or {}).items() if k != "alertname"}
        instance = f" instance {labels}" if labels else ""
        if event_type == "alert_firing":
            summary = f"Alert rule '{rule_title}'{instance} is firing"
        elif event_type == "alert_state_changed":
            summary = f"Alert rule '{rule_title}'{instance} state changed {previous_state or '?'} -> {state}"
        else:
            summary = f"Alert rule '{rule_title}'{instance} {event_type.removeprefix('alert_').replace('_', ' ')}"
        # Firing is anchored at when the instance STARTED firing (startsAt);
        # other transitions are anchored at updatedAt -- both honest to the
        # second best available, falling back to now only when the payload
        # carries neither.
        ts = _parse_ts(alert.get("startsAt")) if event_type == "alert_firing" else _parse_ts(alert.get("updatedAt"))
        return ConnectorEvent(
            timestamp=ts or _utcnow(),
            connector=self.name,
            event_type=event_type,
            summary=summary,
            raw={
                "rule_title": rule_title,
                "state": state,
                "previous_state": previous_state,
                "labels": labels,
                "starts_at": alert.get("startsAt"),
                "alert": alert,
            },
        )

    def _recovery_event(self, rule_uid: str, rule_title: str,
                        key: Tuple[Tuple[str, str], ...]) -> ConnectorEvent:
        labels = {k: v for k, v in key}
        instance = f" instance {labels}" if labels else ""
        return ConnectorEvent(
            timestamp=_utcnow(),
            connector=self.name,
            event_type="alert_recovered",
            summary=f"Alert rule '{rule_title}'{instance} returned to normal (no longer listed by the Alertmanager)",
            raw={
                "rule_uid": rule_uid,
                "rule_title": rule_title,
                "instance_labels": labels,
                "inferred": "resolved alerts leave the alerts list entirely; timestamp is detection time",
            },
        )

    def watch(self, target: str, interval: int = 30) -> WatchHandle:
        """Begin watching an alert rule (CONNECTOR_REWRITE_SPEC §4a).

        The returned handle lists the rule's firing instances each poll()
        and emits ConnectorEvents only for transitions: new firings,
        silences/re-fires, and recoveries -- de-duplicated across polls by
        instance label set + state + startsAt. Baseline contract (mirrors
        PagerDuty's service watch): instances already firing when the watch
        starts are seeded silently -- start watching mid-incident and you
        get the NEXT transition, not a replay of the current one. Multiple
        rules = multiple handles; the shared watcher loop owns the cadence.
        """
        handle = self.locate(target)
        if not handle:
            raise GrafanaError(f"alert rule not found: {target}")
        last_state: Dict[Tuple[Tuple[str, str], ...], Tuple[str, str]] = {}
        for alert in self._rule_alerts(handle["title"]):
            key = _instance_key(alert)
            if key is not None:
                last_state[key] = ((alert.get("status") or {}).get("state") or "unknown",
                                   str(alert.get("startsAt") or ""))
        return _GrafanaWatchHandle(self, target, handle["uid"], handle.get("title") or target, interval, last_state)

    def get_stats(self, target: str, since: Optional[datetime] = None) -> List[ConnectorEvent]:
        """Normalized timeline for a Grafana alert rule (CONNECTOR_REWRITE_SPEC §4a).

        Two surfaces, ascending by timestamp, everything after `since`
        (default: the last hour); [] when nothing resolves. (1) State-change
        annotations (`type=alert`, which carry prevState/newState) that
        reference the rule -- by uid in a tag or the title in the text. The
        annotations endpoint has no rule-uid filter, so attribution is
        client-side and a record referencing neither stays unattributed
        (omitted, not mislabeled) -- known limitation, not silently glossed
        over. (2) The rule's currently-firing instances, anchored at their
        startsAt when that falls inside the window. A firing that predates
        `since` is skipped here on purpose: it is ongoing state
        (poll_state's surface, and what the ALERT RULE STATE block carries),
        while get_stats() is 'what happened, on a shared clock'.
        """
        if since is None:
            since = _utcnow() - timedelta(hours=1)
        elif since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        handle = self.locate(target)
        if not handle:
            return []
        events = self._annotation_events(handle, since) + self._current_state_events(handle, since)
        events.sort(key=lambda event: event["timestamp"])
        return events

    def _annotation_events(self, handle: Dict[str, Any], since: datetime) -> List[ConnectorEvent]:
        uid, title = handle["uid"], handle["title"]
        from_ms = int(since.timestamp() * 1000)
        to_ms = int(_utcnow().timestamp() * 1000)
        path = f"/api/annotations?type=alert&from={from_ms}&to={to_ms}&limit=100"
        try:
            resp = self._request("GET", path)
        except GrafanaError:
            return []
        annotations = resp if isinstance(resp, list) else []
        events: List[ConnectorEvent] = []
        for ann in annotations:
            if not isinstance(ann, dict):
                continue
            tags = [str(t) for t in (ann.get("tags") or [])]
            text = str(ann.get("text") or "")
            referenced = uid in tags or any(uid in t for t in tags) or title in text
            if not referenced:
                continue
            ts = _parse_ts(ann.get("time"))
            if ts is None or ts < since:
                continue
            new_state = str(ann.get("newState") or "")
            prev_state = str(ann.get("prevState") or "")
            event_type = _ANNOTATION_STATE_EVENT_MAP.get(new_state.lower(), "alert_state_changed")
            summary = f"Alert rule '{title}' state change: {prev_state or '?'} -> {new_state or '?'}"
            if text and text != title:
                summary += f": {text[:120]}"
            events.append(ConnectorEvent(
                timestamp=ts,
                connector=self.name,
                event_type=event_type,
                summary=summary,
                raw={"rule_uid": uid, "rule_title": title, "annotation": ann},
            ))
        return events

    def _current_state_events(self, handle: Dict[str, Any], since: datetime) -> List[ConnectorEvent]:
        title = handle["title"]
        events: List[ConnectorEvent] = []
        for alert in self._rule_alerts(title):
            if (alert.get("status") or {}).get("state") != "active":
                continue
            starts = _parse_ts(alert.get("startsAt"))
            if starts is None or starts < since:
                continue
            events.append(self._alert_event(alert, "alert_firing", title))
        return events

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
