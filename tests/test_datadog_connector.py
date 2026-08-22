"""Datadog connector (Sprint 2 Tier 3, PRASH_V2.md §7b). Same style as
test_gitlab_connector.py: unit-level checks on the request plumbing itself
(auth headers, site selection, monitor-id vs. monitor-name locate, state
mapping) via a monkeypatched urllib.request.urlopen."""

from __future__ import annotations

import json
import urllib.request

from prash.connectors.datadog import DatadogConnector


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
