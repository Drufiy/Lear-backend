"""PagerDuty connector (Sprint 2 Tier 3, PRASH_V2.md §7b). Same style as
test_datadog_connector.py / test_grafana_connector.py: unit-level checks on
request plumbing (auth header, service locate, incident-state mapping, the
required From header on writes) via a monkeypatched urllib.request.urlopen.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from prash.connectors.pagerduty import PagerDutyConnector, PagerDutyError


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture_urlopen(monkeypatch, body: bytes = b"{}"):
    calls = []

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def _sequenced_urlopen(monkeypatch, bodies: list[bytes]):
    calls = []
    index = {"i": 0}

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        body = bodies[index["i"]]
        index["i"] += 1
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def test_authenticate_sends_token_header(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"abilities": []}')
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "pdkey"})
    assert pd.authenticate() is True
    assert calls[0].get_header("Authorization") == "Token token=pdkey"
    assert calls[0].full_url == "https://api.pagerduty.com/abilities"


def test_authenticate_false_without_api_key():
    assert PagerDutyConnector({}).authenticate() is False


def test_authenticate_false_on_401(monkeypatch):
    def fake_urlopen(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "bad"})
    assert pd.authenticate() is False


def test_locate_searches_services_by_query(monkeypatch):
    body = json.dumps({"services": [{"id": "PSVC1", "name": "checkout-service"}]}).encode()
    calls = _capture_urlopen(monkeypatch, body)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    handle = pd.locate("checkout")
    assert handle == {"service_id": "PSVC1", "name": "checkout-service"}
    assert "services?query=checkout" in calls[0].full_url


def test_locate_returns_empty_when_no_service_matches(monkeypatch):
    _capture_urlopen(monkeypatch, json.dumps({"services": []}).encode())
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    assert pd.locate("no such service") == {}


def test_locate_returns_empty_without_api_key():
    assert PagerDutyConnector({}).locate("anything") == {}


def test_poll_state_healthy_when_no_open_incidents(monkeypatch):
    from prash.connectors.base import ConnectorState

    bodies = [
        json.dumps({"services": [{"id": "PSVC1", "name": "checkout"}]}).encode(),
        json.dumps({"incidents": []}).encode(),
    ]
    _sequenced_urlopen(monkeypatch, bodies)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    state = pd.poll_state("checkout")
    assert state.state == ConnectorState.HEALTHY
    assert state.detail["open_incidents"] == []


def test_poll_state_failed_when_triggered_incident_open(monkeypatch):
    from prash.connectors.base import ConnectorState

    bodies = [
        json.dumps({"services": [{"id": "PSVC1", "name": "checkout"}]}).encode(),
        json.dumps({"incidents": [{"id": "PINC1", "title": "500s spiking", "status": "triggered"}]}).encode(),
    ]
    _sequenced_urlopen(monkeypatch, bodies)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    state = pd.poll_state("checkout")
    assert state.state == ConnectorState.FAILED
    assert state.detail["open_incidents"][0]["id"] == "PINC1"


def test_poll_state_degraded_when_only_acknowledged_incidents_open(monkeypatch):
    from prash.connectors.base import ConnectorState

    bodies = [
        json.dumps({"services": [{"id": "PSVC1", "name": "checkout"}]}).encode(),
        json.dumps({"incidents": [{"id": "PINC1", "title": "500s spiking", "status": "acknowledged"}]}).encode(),
    ]
    _sequenced_urlopen(monkeypatch, bodies)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    assert pd.poll_state("checkout").state == ConnectorState.DEGRADED


def test_poll_state_not_found_when_service_missing(monkeypatch):
    from prash.connectors.base import ConnectorState

    _capture_urlopen(monkeypatch, json.dumps({"services": []}).encode())
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    assert pd.poll_state("no such service").state == ConnectorState.NOT_FOUND


def test_acknowledge_incident_sends_from_header_and_status(monkeypatch):
    calls = _capture_urlopen(monkeypatch, json.dumps({"incident": {"id": "PINC1", "status": "acknowledged"}}).encode())
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k", "PAGERDUTY_FROM_EMAIL": "bot@acme.com"})
    result = pd.acknowledge_incident("PINC1")
    assert result["status"] == "acknowledged"
    assert calls[0].get_header("From") == "bot@acme.com"
    assert calls[0].get_method() == "PUT"
    payload = json.loads(calls[0].data)
    assert payload == {"incident": {"type": "incident_reference", "status": "acknowledged"}}


def test_resolve_incident_sends_resolved_status(monkeypatch):
    calls = _capture_urlopen(monkeypatch, json.dumps({"incident": {"id": "PINC1", "status": "resolved"}}).encode())
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k", "PAGERDUTY_FROM_EMAIL": "bot@acme.com"})
    result = pd.resolve_incident("PINC1")
    assert result["status"] == "resolved"
    payload = json.loads(calls[0].data)
    assert payload["incident"]["status"] == "resolved"


def test_write_without_from_email_raises_clean_error():
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    try:
        pd.acknowledge_incident("PINC1")
        assert False, "expected PagerDutyError"
    except PagerDutyError as exc:
        assert "PAGERDUTY_FROM_EMAIL" in str(exc)


def test_trigger_event_hits_events_api_with_routing_key(monkeypatch):
    calls = _capture_urlopen(monkeypatch, json.dumps({"status": "success", "dedup_key": "dk-1"}).encode())
    pd = PagerDutyConnector({"PAGERDUTY_ROUTING_KEY": "rk-secret"})
    result = pd.trigger_event(summary="leaked secret found", source="/repo/path", severity="critical")
    assert result["dedup_key"] == "dk-1"
    assert calls[0].full_url == "https://events.pagerduty.com/v2/enqueue"
    payload = json.loads(calls[0].data)
    assert payload["routing_key"] == "rk-secret"
    assert payload["event_action"] == "trigger"
    assert payload["payload"]["summary"] == "leaked secret found"


def test_trigger_event_without_routing_key_raises_clean_error():
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    try:
        pd.trigger_event(summary="x", source="y")
        assert False, "expected PagerDutyError"
    except PagerDutyError as exc:
        assert "PAGERDUTY_ROUTING_KEY" in str(exc)


def test_trigger_event_never_uses_rest_api_auth_header(monkeypatch):
    """The Events API is a genuinely different PagerDuty product from the
    REST API used by acknowledge/resolve -- must not send the REST
    Authorization/From headers here."""
    calls = _capture_urlopen(monkeypatch, json.dumps({"dedup_key": "dk-1"}).encode())
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "rest-key", "PAGERDUTY_ROUTING_KEY": "rk-secret"})
    pd.trigger_event(summary="x", source="y")
    assert calls[0].get_header("Authorization") is None


# ── Phase 3: request plumbing — retry, backoff, rotation, pagination ────────

import email.message
import io
from datetime import datetime, timezone

import prash.connectors.pagerduty as pagerduty_mod
from prash.connectors.base import WatchHandle


def _http_error(code, retry_after=None, body=b'{"error": {"message": "err"}}'):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://api.pagerduty.com/x", code, "err", headers, io.BytesIO(body))


def test_request_retries_429_with_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr(pagerduty_mod.time, "sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise _http_error(429)
        return _FakeResponse(b'{"abilities": []}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    assert pd.authenticate() is True
    assert attempts["n"] == 3
    assert sleeps == [1, 2]


def test_request_429_honors_retry_after_header(monkeypatch):
    """PagerDuty's documented 900 req/min limit surfaces as 429 + Retry-After;
    the header's value must win over the computed backoff."""
    sleeps = []
    monkeypatch.setattr(pagerduty_mod.time, "sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(429, retry_after=5)
        return _FakeResponse(b'{"abilities": []}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    assert pd.authenticate() is True
    assert sleeps == [5]


def test_request_permanent_404_raises_immediately(monkeypatch):
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        raise _http_error(404)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    try:
        pd._request("GET", "/incidents/NOPE")
        assert False, "expected PagerDutyError"
    except PagerDutyError as exc:
        assert "404" in str(exc)
    assert attempts["n"] == 1


def test_credential_rotation_reauth_on_401(monkeypatch):
    monkeypatch.setenv("PAGERDUTY_API_KEY", "fresh-key")
    calls = []
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(401)
        return _FakeResponse(b'{"abilities": []}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "stale-key"})
    assert pd.authenticate() is True
    assert attempts["n"] == 2
    assert pd.api_key == "fresh-key"
    assert calls[1].get_header("Authorization") == "Token token=fresh-key"


def test_401_without_rotation_fails_after_one_attempt(monkeypatch):
    monkeypatch.delenv("PAGERDUTY_API_KEY", raising=False)
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        raise _http_error(401)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "stale-key"})
    assert pd.authenticate() is False
    assert attempts["n"] == 1


def test_paginates_incident_lists_via_more_flag(monkeypatch):
    """REST v2 lists paginate by limit/offset with a `more` flag -- a page
    boundary must not silently hide incidents from watch()/get_stats()."""
    page1 = _incidents_body(
        {"id": "PINC1", "title": "a", "status": "triggered", "urgency": "high", "priority": None},
        {"id": "PINC2", "title": "b", "status": "acknowledged", "urgency": "low", "priority": None},
        more=True,
    )
    page2 = _incidents_body(
        {"id": "PINC3", "title": "c", "status": "resolved", "urgency": "low", "priority": None},
        more=False,
    )
    calls = _sequenced_urlopen(monkeypatch, [page1, page2])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    incidents = pd._service_incidents("PSVC1")
    assert [i["id"] for i in incidents] == ["PINC1", "PINC2", "PINC3"]
    assert "offset=0" in calls[0].full_url and "limit=100" in calls[0].full_url
    assert "offset=100" in calls[1].full_url


def _incidents_body(*incidents, more=False):
    return json.dumps({"incidents": list(incidents), "more": more}).encode()


def _incident(id="PINC1", title="500s spiking", status="triggered", assignments=("U1",),
              priority="P1", urgency="high", incident_key=None, created_at="2026-09-04T12:00:00Z"):
    inc = {
        "id": id, "title": title, "status": status, "urgency": urgency,
        "created_at": created_at, "last_status_change_at": created_at,
        "assignments": [{"assignee": {"id": u}} for u in assignments],
        "escalation_policy": {"summary": "platform-oncall"},
    }
    inc["priority"] = {"summary": priority} if priority else None
    if incident_key:
        inc["incident_key"] = incident_key
    return inc


_SERVICE = json.dumps({"services": [{"id": "PSVC1", "name": "checkout"}]}).encode()


def test_watch_returns_watch_handle(monkeypatch):
    calls = _sequenced_urlopen(monkeypatch, [
        _SERVICE,                                  # locate
        _incidents_body(_incident()),              # watch() seeds state
    ])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    handle = pd.watch("checkout")
    assert isinstance(handle, WatchHandle)
    assert handle.connector == "pagerduty"
    assert handle.target == "checkout"
    assert handle.service_id == "PSVC1"
    assert handle.service_name == "checkout"
    assert handle.interval == 30
    assert "include[]=assignments" in calls[1].full_url
    assert "statuses[]=resolved" in calls[1].full_url  # resolutions must be visible


def test_watch_detects_new_incident_and_dedups(monkeypatch):
    """The core watcher contract: a new trigger fires once; the same
    incident in the same state on the next poll is silent."""
    _sequenced_urlopen(monkeypatch, [
        _SERVICE,                       # locate
        _incidents_body(),              # seed: nothing open
        _incidents_body(_incident()),   # poll 1: new trigger
        _incidents_body(_incident()),   # poll 2: unchanged -> silent
    ])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    handle = pd.watch("checkout")

    events = handle.poll()
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "incident_triggered"
    assert event["connector"] == "pagerduty"
    assert event["summary"] == "Incident '500s spiking' on checkout triggered (critical severity, high urgency)"
    assert event["raw"]["severity"] == "critical"
    assert event["raw"]["priority"] == "P1"
    assert isinstance(event["timestamp"], datetime)

    assert handle.poll() == []


def test_watch_detects_acknowledgment_transition(monkeypatch):
    _sequenced_urlopen(monkeypatch, [
        _SERVICE,
        _incidents_body(_incident()),
        _incidents_body(_incident(status="acknowledged")),
    ])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    handle = pd.watch("checkout")
    events = handle.poll()
    assert len(events) == 1
    assert events[0]["event_type"] == "incident_acknowledged"
    assert events[0]["raw"]["previous_status"] == "triggered"


def test_watch_detects_resolution_transition(monkeypatch):
    _sequenced_urlopen(monkeypatch, [
        _SERVICE,
        _incidents_body(_incident()),
        _incidents_body(_incident(status="resolved")),
    ])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    handle = pd.watch("checkout")
    events = handle.poll()
    assert len(events) == 1
    assert events[0]["event_type"] == "incident_resolved"


def test_watch_detects_escalation_via_assignment_change(monkeypatch):
    """Same status but a new assignee = escalation/reassignment -- a signal
    nobody is actually on it, worth a fresh ping despite unchanged status."""
    _sequenced_urlopen(monkeypatch, [
        _SERVICE,
        _incidents_body(_incident()),
        _incidents_body(_incident(assignments=("U2",))),
    ])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    handle = pd.watch("checkout")
    events = handle.poll()
    assert len(events) == 1
    assert events[0]["event_type"] == "incident_escalated"


def test_watch_ignores_resolved_incident_on_first_sighting(monkeypatch):
    """A resolved incident appearing for the first time is history predating
    the watch -- baselining it, not paging the team about a dead incident."""
    _sequenced_urlopen(monkeypatch, [
        _SERVICE,
        _incidents_body(),
        _incidents_body(_incident(status="resolved")),
    ])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    handle = pd.watch("checkout")
    assert handle.poll() == []


def test_watch_raises_when_service_not_found(monkeypatch):
    _capture_urlopen(monkeypatch, json.dumps({"services": []}).encode())
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    try:
        pd.watch("no such service")
        assert False, "expected PagerDutyError"
    except PagerDutyError as exc:
        assert "not found" in str(exc)


# ── Phase 3: get_stats() — normalized timeline ──────────────────────────────

_SINCE = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)


def test_get_stats_incident_mode_normalizes_log_entries(monkeypatch):
    incident_body = json.dumps({"incident": _incident()}).encode()
    log_body = json.dumps({"log_entries": [
        {"id": "LE1", "type": "trigger_log_entry", "summary": "triggered", "created_at": "2026-09-04T11:00:00Z"},
        {"id": "LE2", "type": "ack_log_entry", "summary": "ack by on-call", "created_at": "2026-09-04T11:05:00Z"},
        {"id": "LE3", "type": "escalate_log_entry", "summary": "escalated to platform", "created_at": "2026-09-04T11:20:00Z"},
        {"id": "LE4", "type": "resolve_log_entry", "summary": "resolved", "created_at": "2026-09-04T12:00:00Z"},
    ], "more": False}).encode()
    calls = _sequenced_urlopen(monkeypatch, [incident_body, log_body])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})

    events = pd.get_stats("PINC1", since=_SINCE)

    assert [e["event_type"] for e in events] == [
        "incident_triggered", "incident_acknowledged", "incident_escalated", "incident_resolved",
    ]  # ascending by timestamp
    for event in events:
        assert event["connector"] == "pagerduty"
        assert isinstance(event["timestamp"], datetime)
        assert event["raw"]["incident_id"] == "PINC1"
    assert "log_entries" in calls[1].full_url


def test_get_stats_incident_mode_respects_since(monkeypatch):
    incident_body = json.dumps({"incident": _incident()}).encode()
    log_body = json.dumps({"log_entries": [
        {"id": "LE1", "type": "trigger_log_entry", "summary": "old", "created_at": "2026-09-04T11:00:00Z"},
        {"id": "LE2", "type": "ack_log_entry", "summary": "kept", "created_at": "2026-09-04T12:00:00Z"},
    ], "more": False}).encode()
    _sequenced_urlopen(monkeypatch, [incident_body, log_body])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})

    events = pd.get_stats("PINC1", since=datetime(2026, 9, 4, 11, 30, tzinfo=timezone.utc))
    assert [e["summary"] for e in events] == ["kept"]


def test_get_stats_service_mode_lists_incidents_and_change_events(monkeypatch):
    """A service target (the documented resource shape) falls back to the
    incident window + change events; the incident-id probe 404s first."""
    bodies = [
        _SERVICE,
        _incidents_body(_incident(id="PINC1", incident_key="dk-1")),
        json.dumps({"change_events": [
            {"id": "CE1", "summary": "deploy v2", "source": "ci", "timestamp": "2026-09-04T11:58:00Z"},
        ], "more": False}).encode(),
    ]
    calls = []
    index = {"i": 0}

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        if req.full_url.endswith("/incidents/PINC"):
            raise _http_error(404)  # not an incident id -> service mode
        body = bodies[index["i"]]
        index["i"] += 1
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})

    events = pd.get_stats("PINC", since=_SINCE)
    types = [e["event_type"] for e in events]
    assert "incident_triggered" in types and "change_event" in types
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps)
    assert any("services?query=PINC" in c.full_url for c in calls)
    assert any("change_events" in c.full_url for c in calls)


def test_get_stats_empty_when_nothing_matches(monkeypatch):
    _capture_urlopen(monkeypatch, json.dumps({"services": []}).encode())
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    assert pd.get_stats("no such service", since=_SINCE) == []


# ── Phase 3: page_oncall — the pagerduty-page primitive ─────────────────────


def test_page_oncall_posts_events_api_with_dedup_key(monkeypatch):
    calls = _capture_urlopen(monkeypatch, json.dumps({"status": "success", "dedup_key": "dk-9"}).encode())
    pd = PagerDutyConnector({"PAGERDUTY_ROUTING_KEY": "rk-secret"})
    result = pd.page_oncall("DB is down", "prash", severity="warning", dedup_key="dk-9")
    assert result["status"] == "success"
    assert calls[0].full_url == "https://events.pagerduty.com/v2/enqueue"
    assert calls[0].get_header("Authorization") is None  # routing key auth, not REST
    payload = json.loads(calls[0].data)
    assert payload["routing_key"] == "rk-secret"
    assert payload["event_action"] == "trigger"
    assert payload["dedup_key"] == "dk-9"
    assert payload["payload"]["severity"] == "warning"


def test_page_oncall_requires_routing_key():
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    try:
        pd.page_oncall("x", "y")
        assert False, "expected PagerDutyError"
    except PagerDutyError as exc:
        assert "PAGERDUTY_ROUTING_KEY" in str(exc)


def test_page_oncall_validates_severity():
    pd = PagerDutyConnector({"PAGERDUTY_ROUTING_KEY": "rk"})
    try:
        pd.page_oncall("x", "y", severity="banana")
        assert False, "expected PagerDutyError"
    except PagerDutyError as exc:
        assert "severity" in str(exc)


def test_page_oncall_retries_429(monkeypatch):
    sleeps = []
    monkeypatch.setattr(pagerduty_mod.time, "sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(429)
        return _FakeResponse(json.dumps({"status": "success", "dedup_key": "dk"}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pd = PagerDutyConnector({"PAGERDUTY_ROUTING_KEY": "rk"})
    assert pd.page_oncall("x", "y")["status"] == "success"
    assert attempts["n"] == 2
    assert sleeps == [1]


def test_find_incident_by_incident_key_matches_dedup(monkeypatch):
    page = _incidents_body(
        _incident(id="PINC2", incident_key="dk-mine"),
        _incident(id="PINC1", incident_key="dk-other"),
    )
    calls = _sequenced_urlopen(monkeypatch, [page])  # legacy shape: field match, one request
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    found = pd.find_incident_by_incident_key("dk-mine", since=_SINCE)
    assert found is not None and found["id"] == "PINC2"
    assert "incident_key=dk-mine" in calls[0].full_url  # narrowed server-side


def test_find_incident_by_incident_key_null_field_matches_via_alert_key(monkeypatch):
    # Found live 2026-09-09: PagerDuty returns incident_key: null on the
    # incident object even for Events-v2 triggers; the dedup key lives on
    # the incident's alert as alert_key.
    page = _incidents_body(_incident(id="PINC9", incident_key=None))
    alerts = json.dumps({"alerts": [{"id": "AL1", "alert_key": "dk-mine"}], "more": False}).encode()
    calls = _sequenced_urlopen(monkeypatch, [page, alerts])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    found = pd.find_incident_by_incident_key("dk-mine", since=_SINCE)
    assert found is not None and found["id"] == "PINC9"
    assert "/incidents/PINC9/alerts" in calls[1].full_url


def test_find_incident_by_incident_key_rejects_incident_without_matching_key(monkeypatch):
    # A returned incident whose alert doesn't carry the dedup key must not
    # be passed to the page action's verify() as a match.
    page = _incidents_body(_incident(id="PINC9", incident_key=None))
    alerts = json.dumps({"alerts": [{"id": "AL1", "alert_key": "dk-someone-elses"}], "more": False}).encode()
    _sequenced_urlopen(monkeypatch, [page, alerts])
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    assert pd.find_incident_by_incident_key("dk-mine", since=_SINCE) is None


def test_find_incident_by_incident_key_survives_one_incidents_alerts_failing(monkeypatch):
    """Regression: the per-incident /alerts fallback is unguarded, so one
    incident's alerts fetch failing (404 on a purged/merged incident, a 403,
    or an exhausted-retry 5xx) used to raise straight out and abort the whole
    scan -- skipping a genuine match on a LATER incident in the same window.
    A window query can legitimately return several incidents sharing a dedup
    key across trigger/resolve cycles, so this is reachable. The failing fetch
    must now be logged-and-skipped, not fatal."""
    page = _incidents_body(
        _incident(id="PINC-OLD", incident_key=None),   # scanned first; its /alerts 404s
        _incident(id="PINC-NEW", incident_key=None),   # the real match, reached only if we don't abort
    )
    match_alerts = json.dumps({"alerts": [{"id": "AL2", "alert_key": "dk-mine"}], "more": False}).encode()

    def fake_urlopen(req, timeout=30):
        url = req.full_url
        if "/incidents/PINC-OLD/alerts" in url:
            raise urllib.error.HTTPError(url, 404, "not found", {}, None)
        if "/incidents/PINC-NEW/alerts" in url:
            return _FakeResponse(match_alerts)
        return _FakeResponse(page)  # the /incidents window query

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    found = pd.find_incident_by_incident_key("dk-mine", since=_SINCE)
    assert found is not None and found["id"] == "PINC-NEW"


def test_list_services_resolves_watch_targets(monkeypatch):
    _capture_urlopen(monkeypatch, json.dumps({
        "services": [{"id": "PSVC1", "name": "checkout"}, {"id": "PSVC2", "name": "api"}],
        "more": False,
    }).encode())
    pd = PagerDutyConnector({"PAGERDUTY_API_KEY": "k"})
    assert pd.list_services() == [
        {"service_id": "PSVC1", "name": "checkout"},
        {"service_id": "PSVC2", "name": "api"},
    ]


def test_priority_maps_to_internal_severity():
    from prash.connectors.pagerduty import _incident_severity

    assert _incident_severity({"priority": {"summary": "P1"}}) == "critical"
    assert _incident_severity({"priority": {"summary": "P2"}}) == "critical"
    assert _incident_severity({"priority": {"summary": "P3"}}) == "high"
    assert _incident_severity({"priority": {"summary": "P4"}}) == "medium"
    assert _incident_severity({"priority": {"summary": "P5"}}) == "low"
    assert _incident_severity({"priority": None, "urgency": "high"}) == "high"
    assert _incident_severity({"priority": None, "urgency": "low"}) == "low"
