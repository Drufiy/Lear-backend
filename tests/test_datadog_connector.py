"""Datadog connector (Sprint 2 Tier 3, PRASH_V2.md §7b). Same style as
test_gitlab_connector.py: unit-level checks on the request plumbing itself
(auth headers, site selection, monitor-id vs. monitor-name locate, state
mapping) via a monkeypatched urllib.request.urlopen.

Extended for the connector-rewrite milestones (M2/M4): watch() handle
behavior (transitions, dedup, groups, metric correlation), get_stats()
normalization (shape, since, ordering), request retry/rotation plumbing,
and the events-post primitives behind the datadog-alert action.
"""

from __future__ import annotations

import datetime
import email.message
import io
import json
import urllib.error
import urllib.request

import prash.connectors.datadog as datadog_mod
from prash.connectors.base import ConnectorEvent, WatchHandle
from prash.connectors.datadog import DatadogConnector, DatadogError


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


def test_authenticate_sends_api_key_header_without_app_key(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"valid": true}')
    dd = DatadogConnector({"DATADOG_API_KEY": "key123"})
    assert dd.authenticate() is True
    assert calls[0].get_header("Dd-api-key") == "key123"
    assert calls[0].get_header("Dd-application-key") is None
    assert calls[0].full_url == "https://api.datadoghq.com/api/v1/validate"


def test_authenticate_false_without_api_key():
    dd = DatadogConnector({})
    assert dd.authenticate() is False


def test_authenticate_false_when_api_says_invalid(monkeypatch):
    _capture_urlopen(monkeypatch, b'{"valid": false}')
    dd = DatadogConnector({"DATADOG_API_KEY": "bad-key"})
    assert dd.authenticate() is False


def test_custom_site_changes_base_url(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"valid": true}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_SITE": "datadoghq.eu"})
    dd.authenticate()
    assert calls[0].full_url == "https://api.datadoghq.eu/api/v1/validate"


def test_blank_site_defaults_to_us1(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"valid": true}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_SITE": ""})
    dd.authenticate()
    assert calls[0].full_url == "https://api.datadoghq.com/api/v1/validate"


def test_locate_by_numeric_id_hits_monitor_endpoint_directly(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"id": 42, "name": "api errors", "overall_state": "OK"}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    handle = dd.locate("42")
    assert handle["monitor_id"] == 42
    assert calls[0].full_url == "https://api.datadoghq.com/api/v1/monitor/42"
    assert calls[0].get_header("Dd-application-key") == "a"


def test_locate_by_name_searches_and_takes_first_match(monkeypatch):
    body = json.dumps({"monitors": [{"id": 7, "name": "prod api", "overall_state": "Alert"}]}).encode()
    calls = _capture_urlopen(monkeypatch, body)
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    handle = dd.locate("prod api")
    assert handle["monitor_id"] == 7
    assert "monitor/search?query=prod%20api" in calls[0].full_url


def test_locate_returns_empty_without_app_key():
    dd = DatadogConnector({"DATADOG_API_KEY": "k"})
    assert dd.locate("42") == {}


def test_locate_returns_empty_when_search_has_no_matches(monkeypatch):
    _capture_urlopen(monkeypatch, b'{"monitors": []}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    assert dd.locate("nonexistent monitor") == {}


def test_poll_state_maps_alert_to_failed(monkeypatch):
    _capture_urlopen(monkeypatch, b'{"id": 1, "name": "m", "overall_state": "Alert"}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    from prash.connectors.base import ConnectorState

    state = dd.poll_state("1")
    assert state.state == ConnectorState.FAILED
    assert state.detail["overall_state"] == "Alert"


def test_poll_state_maps_ok_to_healthy(monkeypatch):
    _capture_urlopen(monkeypatch, b'{"id": 1, "name": "m", "overall_state": "OK"}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    from prash.connectors.base import ConnectorState

    assert dd.poll_state("1").state == ConnectorState.HEALTHY


def test_poll_state_not_found_when_monitor_missing(monkeypatch):
    _capture_urlopen(monkeypatch, b'{"monitors": []}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    from prash.connectors.base import ConnectorState

    assert dd.poll_state("no such monitor").state == ConnectorState.NOT_FOUND


def test_fetch_logs_defaults_query_to_resource_string(monkeypatch):
    body = json.dumps({"data": [{"attributes": {"timestamp": "t1", "message": "boom"}}]}).encode()
    calls = _capture_urlopen(monkeypatch, body)
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    lines = dd.fetch_logs("api errors")
    payload = json.loads(calls[0].data)
    assert payload["filter"]["query"] == "api errors"
    assert lines == ["t1 boom"]


def test_fetch_logs_explicit_query_overrides_resource(monkeypatch):
    body = json.dumps({"data": []}).encode()
    calls = _capture_urlopen(monkeypatch, body)
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    dd.fetch_logs("api errors", query="service:checkout status:error")
    payload = json.loads(calls[0].data)
    assert payload["filter"]["query"] == "service:checkout status:error"


def test_fetch_logs_returns_empty_without_app_key():
    dd = DatadogConnector({"DATADOG_API_KEY": "k"})
    assert dd.fetch_logs("anything") == []


def test_mute_monitor_hits_mute_endpoint_with_end_timestamp(monkeypatch):
    bodies = [
        b'{"id": 42, "name": "api errors", "overall_state": "Alert"}',
        b'{"active": true}',
    ]
    calls = []
    index = {"i": 0}

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        body = bodies[index["i"]]
        index["i"] += 1
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    dd.mute_monitor("42", minutes=30)
    assert calls[1].full_url == "https://api.datadoghq.com/api/v1/monitor/42/mute"
    payload = json.loads(calls[1].data)
    assert "end" in payload


def test_mute_monitor_raises_when_monitor_not_found(monkeypatch):
    from prash.connectors.datadog import DatadogError

    _capture_urlopen(monkeypatch, b'{"monitors": []}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    try:
        dd.mute_monitor("no such monitor")
        assert False, "expected DatadogError"
    except DatadogError as exc:
        assert "not found" in str(exc)


# ── M2/M4: request plumbing — retry, backoff, rotation ──────────────────────


def _http_error(code, retry_after=None, body=b'{"errors": []}'):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://api.datadoghq.com/x", code, "err", headers, io.BytesIO(body))


def test_request_retries_429_with_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr(datadog_mod.time, "sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise _http_error(429)
        return _FakeResponse(b'{"valid": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dd = DatadogConnector({"DATADOG_API_KEY": "k"})
    assert dd.authenticate() is True
    assert attempts["n"] == 3
    assert sleeps == [1, 2]  # capped exponential: 2**0, 2**1


def test_request_429_honors_retry_after_header(monkeypatch):
    sleeps = []
    monkeypatch.setattr(datadog_mod.time, "sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(429, retry_after=7)
        return _FakeResponse(b'{"valid": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dd = DatadogConnector({"DATADOG_API_KEY": "k"})
    assert dd.authenticate() is True
    assert sleeps == [7]  # Retry-After wins over the computed backoff


def test_request_retries_transient_network_errors(monkeypatch):
    sleeps = []
    monkeypatch.setattr(datadog_mod.time, "sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise urllib.error.URLError("connection reset")
        return _FakeResponse(b'{"valid": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dd = DatadogConnector({"DATADOG_API_KEY": "k"})
    assert dd.authenticate() is True
    assert attempts["n"] == 3
    assert sleeps == [1, 2]


def test_request_permanent_404_raises_immediately(monkeypatch):
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        raise _http_error(404)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    try:
        dd._request("GET", "/api/v1/monitor/5")
        assert False, "expected DatadogError"
    except DatadogError as exc:
        assert "404" in str(exc)
    assert attempts["n"] == 1  # no retry on a permanent failure


def test_credential_rotation_reauth_on_401(monkeypatch):
    monkeypatch.setenv("DATADOG_API_KEY", "fresh-key")
    calls = []
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(401)
        return _FakeResponse(b'{"valid": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dd = DatadogConnector({"DATADOG_API_KEY": "stale-key", "DATADOG_APP_KEY": "a"})
    assert dd.authenticate() is True
    assert attempts["n"] == 2
    assert dd.api_key == "fresh-key"
    assert calls[1].get_header("Dd-api-key") == "fresh-key"  # retry used the rotated key


def test_401_without_rotation_raises_immediately(monkeypatch):
    monkeypatch.delenv("DATADOG_API_KEY", raising=False)
    monkeypatch.delenv("DATADOG_APP_KEY", raising=False)
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        raise _http_error(401)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dd = DatadogConnector({"DATADOG_API_KEY": "stale-key"})
    # authenticate() never raises (its contract) — but it must NOT retry, and
    # the single attempt must fail honestly.
    assert dd.authenticate() is False
    assert attempts["n"] == 1  # nothing new in the env -> no retry


def test_regional_site_urls():
    sites = {
        "datadoghq.com": "https://api.datadoghq.com",    # US1 (default)
        "datadoghq.eu": "https://api.datadoghq.eu",      # EU
        "us3.datadoghq.com": "https://api.us3.datadoghq.com",
        "us5.datadoghq.com": "https://api.us5.datadoghq.com",
        "ap1.datadoghq.com": "https://api.ap1.datadoghq.com",
    }
    for site, expected_base in sites.items():
        dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_SITE": site})
        assert dd.base_url == expected_base, site


def test_timeout_varies_by_endpoint(monkeypatch):
    seen = []

    def fake_urlopen_body(body):
        def inner(req, timeout=30):
            seen.append(timeout)
            return _FakeResponse(body)
        return inner

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_body(b'{"valid": true}'))
    dd = DatadogConnector({"DATADOG_API_KEY": "k"})
    dd.authenticate()
    assert seen[-1] == 10  # single-document validate read

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_body(b'{"id": 1, "name": "m", "overall_state": "OK"}'))
    dd.locate("1")
    assert seen[-1] == 10  # monitor read

    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})  # fetch_logs needs both keys
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_body(b'{"data": []}'))
    dd.fetch_logs("api errors")
    assert seen[-1] == 30  # log search can legitimately take longer


# ── M4: watch() — the WatchHandle contract ──────────────────────────────────


def _monitor_body(overall="OK", groups=None, query="avg(last_5m):avg:system.cpu.user{*} by {host} > 90"):
    monitor = {"id": 42, "name": "CPU High", "overall_state": overall, "query": query}
    if groups is None:
        monitor["state"] = {"groups": []}
    else:
        monitor["state"] = {"groups": [{"name": name, "status": status} for name, status in groups]}
    return json.dumps(monitor).encode()


def _sequenced_urlopen(monkeypatch, bodies, route=None):
    """Serve bodies in order; `route(req, index)` may override/raise per call."""
    calls = []
    index = {"i": 0}

    def fake_urlopen(req, timeout=30):
        i = index["i"]
        index["i"] += 1
        calls.append(req)
        if route is not None:
            return route(req, i)
        body = bodies[i] if i < len(bodies) else bodies[-1]
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def test_watch_returns_watch_handle(monkeypatch):
    calls = _sequenced_urlopen(monkeypatch, [
        _monitor_body("OK"),   # locate
        _monitor_body("OK"),   # watch() seeds state (group_states=all)
    ])
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    handle = dd.watch("42")
    assert isinstance(handle, WatchHandle)
    assert handle.connector == "datadog"
    assert handle.target == "42"
    assert handle.monitor_id == 42
    assert handle.monitor_name == "CPU High"
    assert handle.interval == 30
    assert "group_states=all" in calls[1].full_url


def test_watch_detects_state_transition_and_dedups(monkeypatch):
    _sequenced_urlopen(monkeypatch, [
        _monitor_body("OK"),    # locate
        _monitor_body("OK"),    # seed
        _monitor_body("OK"),    # poll 1: unchanged
        _monitor_body("Alert"),  # poll 2: OK -> Alert
        _monitor_body("Alert"),  # poll 3: same state -> silent
    ])
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    handle = dd.watch("42")
    assert handle.poll() == []  # baseline agrees with the seed

    events = handle.poll()
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "monitor_alert"
    assert event["summary"] == "Monitor 'CPU High' entered Alert state"
    assert event["connector"] == "datadog"
    assert isinstance(event["timestamp"], datetime.datetime)
    assert event["raw"]["previous_state"] == "OK"
    assert event["raw"]["current_state"] == "Alert"

    assert handle.poll() == []  # the core dedup guarantee: no re-notify


def test_watch_detects_recovery(monkeypatch):
    _sequenced_urlopen(monkeypatch, [
        _monitor_body("OK"),
        _monitor_body("OK"),
        _monitor_body("Alert"),
        _monitor_body("OK"),
    ])
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    handle = dd.watch("42")
    fired = handle.poll()
    assert len(fired) == 1 and fired[0]["event_type"] == "monitor_alert"

    recovered = handle.poll()
    assert len(recovered) == 1
    assert recovered[0]["event_type"] == "monitor_recovered"
    assert recovered[0]["summary"] == "Monitor 'CPU High' recovered to OK"


def test_watch_handles_monitor_groups(monkeypatch):
    groups_ok = [("host:web-1", "OK"), ("host:web-2", "OK")]
    groups_fired = [("host:web-1", "OK"), ("host:web-2", "Alert")]
    _sequenced_urlopen(monkeypatch, [
        _monitor_body("OK"),                      # locate
        _monitor_body("OK", groups=groups_ok),    # seed
        _monitor_body("OK", groups=groups_ok),    # poll 1: unchanged
        _monitor_body("OK", groups=groups_fired),  # poll 2: one group flips
    ])
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    handle = dd.watch("42")
    assert handle.poll() == []

    events = handle.poll()
    assert len(events) == 1
    assert events[0]["raw"]["group"] == "host:web-2"
    assert events[0]["summary"] == "Monitor 'CPU High' [host:web-2] entered Alert state"


def test_watch_alert_attaches_metric_context(monkeypatch):
    metric_body = json.dumps({"series": [{"pointlist": [[1725400000000, 96.4], [1725400300000, 90.0]]}]}).encode()
    _sequenced_urlopen(monkeypatch, [
        _monitor_body("OK"),
        _monitor_body("OK"),
        _monitor_body("Alert"),
        metric_body,  # /api/v1/query correlation fetch
    ])
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    handle = dd.watch("42")
    events = handle.poll()  # seed OK -> poll Alert
    assert len(events) == 1
    metric = events[0]["raw"]["metric"]
    assert metric["max"] == 96.4
    assert metric["mean"] == 93.2
    assert metric["query"] == "avg:system.cpu.user{*} by {host}"


def test_watch_metric_failure_does_not_block_transition(monkeypatch):
    def route(req, i):
        if "/api/v1/query" in req.full_url:
            raise _http_error(404)  # metric correlation is best-effort
        bodies = [_monitor_body("OK"), _monitor_body("OK"), _monitor_body("Alert")]
        return _FakeResponse(bodies[i] if i < len(bodies) else bodies[-1])

    _sequenced_urlopen(monkeypatch, [], route=route)
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    handle = dd.watch("42")
    events = handle.poll()
    assert len(events) == 1
    assert events[0]["event_type"] == "monitor_alert"
    assert "metric" not in events[0]["raw"]


def test_watch_raises_when_monitor_not_found(monkeypatch):
    _capture_urlopen(monkeypatch, b'{"monitors": []}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    try:
        dd.watch("no such monitor")
        assert False, "expected DatadogError"
    except DatadogError as exc:
        assert "not found" in str(exc)


# ── M4: get_stats() — normalized timeline ───────────────────────────────────

_SINCE = datetime.datetime(2026, 9, 4, 10, 0, tzinfo=datetime.timezone.utc)


def _events_body(*events):
    return json.dumps({"data": [
        {"id": f"e{i}", "attributes": attrs} for i, attrs in enumerate(events)
    ]}).encode()


def test_get_stats_returns_connector_events(monkeypatch):
    events_body = _events_body(
        {"timestamp": "2026-09-04T11:00:00Z", "title": "monitor alert fired", "source_type_name": "alert"},
        {"timestamp": "2026-09-04T12:00:00Z", "title": "deploy finished", "source_type_name": "deploy"},
    )
    metric_body = json.dumps({"series": [{"pointlist": [[1725410000000, 5.0], [1725412000000, 99.0]]}]}).encode()
    calls = _sequenced_urlopen(monkeypatch, [_monitor_body("Alert"), events_body, metric_body])
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})

    events = dd.get_stats("42", since=_SINCE)

    assert {e["event_type"] for e in events} == {"monitor_alert", "deploy_event", "metric_spike"}
    for event in events:
        assert event["connector"] == "datadog"
        assert isinstance(event["timestamp"], datetime.datetime)
        assert isinstance(event["raw"], dict)
        assert event["summary"]
    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps)  # ascending, oldest first

    payload = json.loads(calls[1].data)
    assert payload["filter"]["query"] == "@monitor_id:42"
    assert payload["filter"]["from"] == _SINCE.isoformat()
    assert payload["sort"] == "timestamp"


def test_get_stats_respects_since_parameter(monkeypatch):
    events_body = _events_body(
        {"timestamp": "2026-09-04T11:00:00Z", "title": "old event", "source_type_name": "alert"},
        {"timestamp": "2026-09-04T12:00:00Z", "title": "kept event", "source_type_name": "alert"},
    )
    _sequenced_urlopen(monkeypatch, [_monitor_body("Alert"), events_body])
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})

    events = dd.get_stats("42", since=datetime.datetime(2026, 9, 4, 11, 30, tzinfo=datetime.timezone.utc),
                          include_metrics=False)
    assert [e["summary"] for e in events] == ["kept event"]


def test_get_stats_sorts_by_timestamp(monkeypatch):
    events_body = _events_body(
        {"timestamp": "2026-09-04T12:00:00Z", "title": "later", "source_type_name": "alert"},
        {"timestamp": "2026-09-04T11:00:00Z", "title": "earlier", "source_type_name": "alert"},
    )
    _sequenced_urlopen(monkeypatch, [_monitor_body("Alert"), events_body])
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})

    events = dd.get_stats("42", since=_SINCE, include_metrics=False)
    assert [e["summary"] for e in events] == ["earlier", "later"]


def test_get_stats_empty_result(monkeypatch):
    _sequenced_urlopen(monkeypatch, [_monitor_body("OK"), _events_body()])
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    assert dd.get_stats("42", since=_SINCE, include_metrics=False) == []


def test_get_stats_returns_empty_when_monitor_missing(monkeypatch):
    _capture_urlopen(monkeypatch, b'{"monitors": []}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    assert dd.get_stats("no such monitor", since=_SINCE) == []


def test_get_stats_parses_datadog_monitor_alert_event_shape(monkeypatch):
    """Real bug found live (2026-09-07): monitor-alert events carry their
    title, source tags, and state transition inside a NESTED
    attributes.attributes dict (the flat top-level fields are absent), and
    timestamps arrive as epoch milliseconds. get_stats must normalize that
    shape into a monitor_alert ConnectorEvent with the transition surfaced,
    not drop or mislabel it."""
    events_body = _events_body({
        "timestamp": 1788805347000,  # epoch ms, as Datadog sends them
        "attributes": {
            "monitor_id": 42,
            "sourcecategory": "monitor_alert",
            "source_type_name_tag": "monitor_alert",
            "title": "[Triggered] synthetic error rate",
            "transition": {"source_state": "OK", "destination_state": "Alert", "transition_type": "alert"},
        },
    })
    _sequenced_urlopen(monkeypatch, [_monitor_body("Alert"), events_body])
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})

    events = dd.get_stats("42", since=_SINCE, include_metrics=False)

    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "monitor_alert"
    assert event["summary"] == "[Triggered] synthetic error rate"
    assert event["timestamp"] == datetime.datetime(2026, 9, 7, 18, 22, 27, tzinfo=datetime.timezone.utc)
    assert event["raw"]["transition"]["destination_state"] == "Alert"


# ── M4: events-post primitives behind the datadog-alert action ──────────────


def test_post_event_sends_v2_payload(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"data": {"id": "evt-1"}}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    resp = dd.post_event("t", "x", tags=["team:db"], priority="low")
    assert resp["data"]["id"] == "evt-1"
    assert calls[0].full_url == "https://api.datadoghq.com/api/v2/events"
    assert calls[0].get_method() == "POST"
    payload = json.loads(calls[0].data)
    assert payload == {"data": {"type": "event", "attributes": {
        "title": "t", "text": "x", "priority": "low", "tags": ["team:db"],
    }}}


def test_post_event_falls_back_to_v1_when_v2_intake_denied(monkeypatch):
    """Found live (2026-09-07): this org's API key is denied Events v2 intake
    (403 both keys / 401 api-only) while v1 intake accepts the same key. The
    permission-shaped failure must fall back to v1 -- same event stream --
    and the returned payload must carry the v1 event id plus a via marker
    naming the intake that actually landed. Other errors (404, 5xx after
    retries) still propagate; the fallback is not a catch-all."""
    responses = [
        _http_error(403, body=b''),
        b'{"status": "ok", "event": {"id": 8800392108675975624, "title": "t"}}',
    ]
    calls = []

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeResponse(item)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})

    resp = dd.post_event("t", "x", tags=["team:db"])

    assert calls[0].full_url == "https://api.datadoghq.com/api/v2/events"
    assert calls[1].full_url == "https://api.datadoghq.com/api/v1/events"
    v1_payload = json.loads(calls[1].data)
    assert v1_payload == {"title": "t", "text": "x", "priority": "normal", "tags": ["team:db"]}
    assert resp == {"data": {"id": "8800392108675975624", "via": "v1"}}


def test_get_event_falls_back_to_v1_on_404(monkeypatch):
    """A v1-posted event must still be verifiable: v2 GET 404s on it, and the
    v1 GET result is normalized to the same data.id shape so callers compare
    ids identically regardless of which intake landed the event."""
    responses = [
        _http_error(404, body=b'{"errors": ["not found"]}'),
        b'{"event": {"id": 8800392108675975624, "title": "t"}}',
    ]
    calls = []

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeResponse(item)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})

    resp = dd.get_event("8800392108675975624")

    assert calls[0].full_url == "https://api.datadoghq.com/api/v2/events/8800392108675975624"
    assert calls[1].full_url == "https://api.datadoghq.com/api/v1/events/8800392108675975624"
    assert resp["data"]["id"] == "8800392108675975624"


def test_get_event_hits_v2_endpoint(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"data": {"id": "evt-1"}}')
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    dd.get_event("evt-1")
    assert calls[0].full_url == "https://api.datadoghq.com/api/v2/events/evt-1"


def test_list_monitors_resolves_watch_targets(monkeypatch):
    calls = _capture_urlopen(monkeypatch, json.dumps([
        {"id": 1, "name": "api errors"}, {"id": 2, "name": "cpu high"},
    ]).encode())
    dd = DatadogConnector({"DATADOG_API_KEY": "k", "DATADOG_APP_KEY": "a"})
    monitors = dd.list_monitors()
    assert monitors == [{"monitor_id": 1, "name": "api errors"}, {"monitor_id": 2, "name": "cpu high"}]
    assert calls[0].full_url == "https://api.datadoghq.com/api/v1/monitor"

    dd.list_monitors(query="cpu")
    assert "monitor/search?query=cpu" in calls[1].full_url
