"""Grafana connector (Sprint 2 Tier 3, PRASH_V2.md §7b). Same style as
test_datadog_connector.py: unit-level checks on request plumbing (auth
header, uid vs. title locate, alert-state mapping, annotation query shape)
via a monkeypatched urllib.request.urlopen."""

from __future__ import annotations

import json
import urllib.request

from prash.connectors.grafana import GrafanaConnector


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


def test_authenticate_sends_bearer_token(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"id": 1, "name": "Main Org."}')
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "gf-secret"})
    assert gf.authenticate() is True
    assert calls[0].get_header("Authorization") == "Bearer gf-secret"
    assert calls[0].full_url == "https://acme.grafana.net/api/org"


def test_authenticate_false_without_url_or_key():
    assert GrafanaConnector({"GRAFANA_API_KEY": "k"}).authenticate() is False
    assert GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net"}).authenticate() is False


def test_authenticate_false_on_401(monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "bad"})
    assert gf.authenticate() is False


def test_url_trailing_slash_stripped(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{}')
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net/", "GRAFANA_API_KEY": "k"})
    gf.authenticate()
    assert calls[0].full_url == "https://acme.grafana.net/api/org"


def test_locate_matches_by_uid(monkeypatch):
    body = json.dumps([{"uid": "abc123", "title": "High error rate"}]).encode()
    calls = _capture_urlopen(monkeypatch, body)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    handle = gf.locate("abc123")
    assert handle == {"uid": "abc123", "title": "High error rate"}
    assert calls[0].full_url == "https://acme.grafana.net/api/v1/provisioning/alert-rules"


def test_locate_matches_by_title_case_insensitive(monkeypatch):
    body = json.dumps([{"uid": "abc123", "title": "High Error Rate"}]).encode()
    _capture_urlopen(monkeypatch, body)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    handle = gf.locate("high error rate")
    assert handle["uid"] == "abc123"


def test_locate_returns_empty_when_no_rule_matches(monkeypatch):
    body = json.dumps([{"uid": "abc123", "title": "Something else"}]).encode()
    _capture_urlopen(monkeypatch, body)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    assert gf.locate("no such rule") == {}


def test_locate_returns_empty_without_credentials():
    assert GrafanaConnector({}).locate("anything") == {}


def test_poll_state_healthy_when_no_matching_alert(monkeypatch):
    from prash.connectors.base import ConnectorState

    calls_body = [
        json.dumps([{"uid": "abc123", "title": "High error rate"}]).encode(),
        json.dumps([]).encode(),
    ]
    call_index = {"i": 0}

    def fake_urlopen(req, timeout=30):
        body = calls_body[call_index["i"]]
        call_index["i"] += 1
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    state = gf.poll_state("abc123")
    assert state.state == ConnectorState.HEALTHY
    assert state.detail["alert_state"] == "none"


def test_poll_state_failed_when_alert_active(monkeypatch):
    from prash.connectors.base import ConnectorState

    calls_body = [
        json.dumps([{"uid": "abc123", "title": "High error rate"}]).encode(),
        json.dumps([{"labels": {"alertname": "High error rate"}, "status": {"state": "active"}}]).encode(),
    ]
    call_index = {"i": 0}

    def fake_urlopen(req, timeout=30):
        body = calls_body[call_index["i"]]
        call_index["i"] += 1
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    state = gf.poll_state("abc123")
    assert state.state == ConnectorState.FAILED
    assert state.detail["active_alert_count"] == 1


def test_poll_state_not_found_when_rule_missing(monkeypatch):
    from prash.connectors.base import ConnectorState

    _capture_urlopen(monkeypatch, json.dumps([]).encode())
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    assert gf.poll_state("no such rule").state == ConnectorState.NOT_FOUND


def test_fetch_logs_defaults_tag_to_resource(monkeypatch):
    body = json.dumps([{"time": 1000, "text": "deploy started"}]).encode()
    calls = _capture_urlopen(monkeypatch, body)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    lines = gf.fetch_logs("checkout-service")
    assert "tags=checkout-service" in calls[0].full_url
    assert lines == ["1000 deploy started"]


def test_fetch_logs_explicit_tags_override_resource(monkeypatch):
    calls = _capture_urlopen(monkeypatch, json.dumps([]).encode())
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    gf.fetch_logs("checkout-service", tags=["deploy", "prod"])
    url = calls[0].full_url
    assert "tags=deploy" in url and "tags=prod" in url


def test_fetch_logs_returns_empty_without_credentials():
    assert GrafanaConnector({}).fetch_logs("anything") == []


def test_silence_alert_sends_alertname_matcher(monkeypatch):
    bodies = [
        json.dumps([{"uid": "abc123", "title": "High error rate"}]).encode(),
        json.dumps({"silenceID": "sil-1"}).encode(),
    ]
    calls = []
    index = {"i": 0}

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        body = bodies[index["i"]]
        index["i"] += 1
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    result = gf.silence_alert("abc123", minutes=30)
    assert result["silenceID"] == "sil-1"
    assert calls[1].full_url == "https://acme.grafana.net/api/alertmanager/grafana/api/v2/silences"
    payload = json.loads(calls[1].data)
    assert payload["matchers"] == [{"name": "alertname", "value": "High error rate", "isRegex": False}]


def test_silence_alert_raises_when_rule_not_found(monkeypatch):
    from prash.connectors.grafana import GrafanaError

    _capture_urlopen(monkeypatch, json.dumps([]).encode())
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    try:
        gf.silence_alert("no such rule")
        assert False, "expected GrafanaError"
    except GrafanaError as exc:
        assert "not found" in str(exc)


# ── watch()/get_stats() (connector rewrite, Phase 3 rollout) ─────────────────
# Same scaffolding as above (monkeypatched urlopen with a scripted body
# queue), extended to multi-call flows: watch() = locate + baseline alerts
# list; each poll() = one alerts list; get_stats() = locate + annotations +
# alerts list.

import email.message
import io
from datetime import datetime, timezone

import prash.connectors.grafana as grafana_mod
from prash.connectors.base import WatchHandle
from prash.connectors.grafana import GrafanaError

RULES_BODY = json.dumps([{"uid": "abc123", "title": "High error rate"}]).encode()

STARTS = "2026-09-09T12:00:00+00:00"


def _alert(state, labels=None, starts_at=STARTS, updated_at=None):
    return {
        "labels": {"alertname": "High error rate", **(labels or {})},
        "status": {"state": state},
        "startsAt": starts_at,
        "updatedAt": updated_at or starts_at,
    }


def _queue_urlopen(monkeypatch, bodies):
    """Serve scripted bodies (bytes or exceptions) in call order; the last
    body repeats once the queue is exhausted. Returns the recorded calls."""
    calls = []
    index = {"i": 0}

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        i = min(index["i"], len(bodies) - 1)
        index["i"] += 1
        body = bodies[i]
        if isinstance(body, Exception):
            raise body
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def _watch_flow(monkeypatch, alert_lists):
    """bodies for: locate, watch() baseline, then one alerts list per poll().
    Items may be exceptions (passed through as scripted errors)."""
    bodies = [RULES_BODY]
    for alerts in alert_lists:
        bodies.append(alerts if isinstance(alerts, Exception) else json.dumps(alerts).encode())
    return _queue_urlopen(monkeypatch, bodies)


def _http_error(code, retry_after=None):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://acme.grafana.net/x", code, "err", headers, io.BytesIO(b'{"message": "err"}'))


def test_watch_baselines_current_firing_silently_and_dedups(monkeypatch):
    """watch() seeds silently: a rule already firing when the watch starts
    does not page immediately, and the same instance in the same state
    across polls stays silent -- the core dedup guarantee."""
    _watch_flow(monkeypatch, [[_alert("active")], [_alert("active")], [_alert("active")]])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    handle = gf.watch("abc123")
    assert isinstance(handle, WatchHandle)
    assert handle.connector == "grafana"
    assert handle.poll() == []
    assert handle.poll() == []


def test_watch_emits_firing_then_recovery_then_refire(monkeypatch):
    _watch_flow(monkeypatch, [
        [],                          # watch() baseline: quiet
        [_alert("active")],          # poll 1: new firing
        [_alert("active")],          # poll 2: unchanged -> silence
        [],                          # poll 3: gone from the list -> recovery
        [_alert("active")],          # poll 4: fires again
    ])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    handle = gf.watch("abc123")
    firing = handle.poll()
    assert [e["event_type"] for e in firing] == ["alert_firing"]
    assert firing[0]["timestamp"].isoformat() == STARTS  # anchored at startsAt, not poll time
    assert "High error rate" in firing[0]["summary"]
    assert handle.poll() == []
    recovered = handle.poll()
    assert [e["event_type"] for e in recovered] == ["alert_recovered"]
    assert "detection time" in recovered[0]["raw"]["inferred"]
    assert [e["event_type"] for e in handle.poll()] == ["alert_firing"]


def test_watch_treats_silence_as_state_change_not_recovery(monkeypatch):
    """A silenced instance is still listed by the Alertmanager -- it left
    the firing set but the problem did not go away."""
    _watch_flow(monkeypatch, [
        [_alert("active")],
        [_alert("suppressed")],
        [_alert("suppressed")],
    ])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    handle = gf.watch("abc123")
    events = handle.poll()
    assert [e["event_type"] for e in events] == ["alert_state_changed"]
    assert "active -> suppressed" in events[0]["summary"]
    assert handle.poll() == []


def test_watch_dedups_instances_independently(monkeypatch):
    """One rule can fire several instances (one per label set); each is
    deduped and recovered separately."""
    _watch_flow(monkeypatch, [
        [_alert("active", {"env": "prod"})],
        [_alert("active", {"env": "prod"}), _alert("active", {"env": "dev"})],
    ])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    handle = gf.watch("abc123")
    events = handle.poll()
    assert [e["event_type"] for e in events] == ["alert_firing"]
    assert events[0]["raw"]["labels"] == {"env": "dev"}  # prod was baselined


def test_watch_raises_when_rule_not_found(monkeypatch):
    _watch_flow(monkeypatch, [[]])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    try:
        gf.watch("no such rule")
        assert False, "expected GrafanaError"
    except GrafanaError as exc:
        assert "not found" in str(exc)


def test_get_stats_maps_annotations_and_current_firing(monkeypatch):
    since = datetime(2026, 9, 9, 11, 30, tzinfo=timezone.utc)
    epoch_ms = lambda dt: int(dt.timestamp() * 1000)
    annotations = [
        # matched by title in text; Alerting -> alert_firing
        {"time": epoch_ms(datetime(2026, 9, 9, 11, 40, tzinfo=timezone.utc)),
         "newState": "Alerting", "prevState": "Pending", "text": "High error rate", "tags": []},
        # matched by uid in tags; OK -> alert_recovered
        {"time": epoch_ms(datetime(2026, 9, 9, 11, 35, tzinfo=timezone.utc)),
         "newState": "OK", "prevState": "Alerting", "text": "unrelated note", "tags": ["abc123"]},
        # references neither uid nor title -> unattributed, omitted entirely
        {"time": epoch_ms(datetime(2026, 9, 9, 11, 50, tzinfo=timezone.utc)),
         "newState": "Alerting", "prevState": "Pending", "text": "some other rule", "tags": ["other"]},
        # matched but predates the window -> dropped
        {"time": epoch_ms(datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc)),
         "newState": "Alerting", "prevState": "Pending", "text": "High error rate", "tags": []},
    ]
    _watch_flow(monkeypatch, [annotations, [_alert("active", starts_at="2026-09-09T11:45:00+00:00")]])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    events = gf.get_stats("abc123", since=since)
    assert [(e["event_type"], e["timestamp"].isoformat()) for e in events] == [
        ("alert_recovered", "2026-09-09T11:35:00+00:00"),
        ("alert_firing", "2026-09-09T11:40:00+00:00"),
        ("alert_firing", "2026-09-09T11:45:00+00:00"),
    ]
    assert "Alerting" not in events[0]["event_type"]  # vocabulary normalized
    assert "Pending -> Alerting" in events[1]["summary"]


def test_get_stats_skips_ongoing_firing_predating_window(monkeypatch):
    """A firing whose startsAt predates `since` is ongoing state (poll_state's
    surface), not a window event -- get_stats stays 'what happened' and
    returns [] rather than fabricating a timestamp inside the window."""
    _watch_flow(monkeypatch, [[], [_alert("active", starts_at="2026-09-08T12:00:00+00:00")]])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    assert gf.get_stats("abc123", since=datetime(2026, 9, 9, 11, 30, tzinfo=timezone.utc)) == []


def test_get_stats_accepts_naive_since_as_utc(monkeypatch):
    _watch_flow(monkeypatch, [[], []])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    assert gf.get_stats("abc123", since=datetime(2026, 9, 9, 11, 30)) == []  # noqa: DTZ001 — naive on purpose: the connector treats it as UTC


def test_get_stats_returns_empty_without_credentials():
    assert GrafanaConnector({}).get_stats("anything") == []


def test_get_stats_returns_empty_when_rule_missing(monkeypatch):
    _queue_urlopen(monkeypatch, [json.dumps([]).encode()])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    assert gf.get_stats("no such rule") == []


def test_get_stats_swallows_api_errors_to_empty(monkeypatch):
    """get_stats() is swallow-to-[] by contract (fix.py's diagnosis seam
    relies on an empty window being a valid input)."""
    _watch_flow(monkeypatch, [_http_error(500), _http_error(500), _http_error(500), _http_error(500)])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    assert gf.get_stats("abc123") == []


def test_list_rules_maps_and_caps(monkeypatch):
    body = json.dumps([
        {"uid": "a", "title": "A"},
        {"uid": "b", "title": ""},
        {"title": "no uid, skipped"},
    ]).encode()
    _queue_urlopen(monkeypatch, [body])
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    assert gf.list_rules() == [{"uid": "a", "title": "A"}, {"uid": "b", "title": ""}]


# ── request plumbing: retry, backoff, rotation (mirrors pagerduty.py) ────────


def test_request_retries_503_with_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr(grafana_mod.time, "sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(503)
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    assert gf._request("GET", "/api/org") == {"ok": True}
    assert attempts["n"] == 2
    assert sleeps == [1.0]


def test_request_honors_retry_after_on_429(monkeypatch):
    sleeps = []
    monkeypatch.setattr(grafana_mod.time, "sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(429, retry_after=7)
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    assert gf._request("GET", "/api/org") == {"ok": True}
    assert sleeps == [7.0]


def test_request_rotates_key_on_401(monkeypatch):
    """A 401 gets one environment re-read (token rotation) before it's
    treated as permanent."""
    monkeypatch.setenv("GRAFANA_API_KEY", "fresh-key")
    calls = []
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _http_error(401)
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "stale-key"})
    assert gf._request("GET", "/api/org") == {"ok": True}
    assert calls[0].get_header("Authorization") == "Bearer stale-key"
    assert calls[1].get_header("Authorization") == "Bearer fresh-key"


def test_request_gives_up_after_exhausted_transient_retries(monkeypatch):
    sleeps = []
    monkeypatch.setattr(grafana_mod.time, "sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        raise _http_error(503)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    try:
        gf._request("GET", "/api/org")
        assert False, "expected GrafanaError"
    except GrafanaError:
        pass
    assert attempts["n"] == 4  # initial + _MAX_RETRIES
    assert sleeps == [1.0, 2.0, 4.0]


def test_request_does_not_retry_permanent_errors(monkeypatch):
    monkeypatch.setattr(grafana_mod.time, "sleep", lambda s: None)
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=30):
        attempts["n"] += 1
        raise _http_error(404)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    gf = GrafanaConnector({"GRAFANA_URL": "https://acme.grafana.net", "GRAFANA_API_KEY": "k"})
    try:
        gf._request("GET", "/api/org")
        assert False, "expected GrafanaError"
    except GrafanaError:
        pass
    assert attempts["n"] == 1
