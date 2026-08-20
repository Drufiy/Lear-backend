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
