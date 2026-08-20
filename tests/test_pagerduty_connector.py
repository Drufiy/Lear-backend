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
