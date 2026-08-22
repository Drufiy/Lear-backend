"""Snyk connector (Sprint 2 Tier 3, PRASH_V2.md §7b). Same style as
test_datadog_connector.py / test_grafana_connector.py: unit-level checks on
request plumbing (auth header, org-scoped project locate, severity->state
mapping) via a monkeypatched urllib.request.urlopen."""

from __future__ import annotations

import json
import urllib.request

from prash.connectors.snyk import SnykConnector


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


def test_authenticate_sends_token_header(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"username": "aradhya"}')
    sn = SnykConnector({"SNYK_API_TOKEN": "snyk-secret"})
    assert sn.authenticate() is True
    assert calls[0].get_header("Authorization") == "token snyk-secret"
    assert calls[0].full_url == "https://api.snyk.io/v1/user/me"


def test_authenticate_false_without_token():
    assert SnykConnector({}).authenticate() is False


def test_locate_requires_org_id():
    assert SnykConnector({"SNYK_API_TOKEN": "t"}).locate("some-project") == {}


def test_locate_matches_by_id_or_name(monkeypatch):
    body = json.dumps({"projects": [{"id": "proj-uuid", "name": "checkout-service", "issueCountsBySeverity": {"critical": 0, "high": 0, "medium": 0, "low": 2}}]}).encode()
    calls = _capture_urlopen(monkeypatch, body)
    sn = SnykConnector({"SNYK_API_TOKEN": "t", "SNYK_ORG_ID": "org1"})
    handle = sn.locate("checkout-service")
    assert handle["project_id"] == "proj-uuid"
    assert "org/org1/projects" in calls[0].full_url


def test_locate_returns_empty_when_no_project_matches(monkeypatch):
    _capture_urlopen(monkeypatch, json.dumps({"projects": []}).encode())
    sn = SnykConnector({"SNYK_API_TOKEN": "t", "SNYK_ORG_ID": "org1"})
    assert sn.locate("no such project") == {}


def test_poll_state_failed_when_critical_issues_present(monkeypatch):
    from prash.connectors.base import ConnectorState

    body = json.dumps({"projects": [{"id": "p1", "name": "api", "issueCountsBySeverity": {"critical": 1, "high": 0, "medium": 0, "low": 0}}]}).encode()
    _capture_urlopen(monkeypatch, body)
    sn = SnykConnector({"SNYK_API_TOKEN": "t", "SNYK_ORG_ID": "org1"})
    state = sn.poll_state("p1")
    assert state.state == ConnectorState.FAILED
    assert state.detail["critical"] == 1


def test_poll_state_failed_when_high_issues_present(monkeypatch):
    from prash.connectors.base import ConnectorState

    body = json.dumps({"projects": [{"id": "p1", "name": "api", "issueCountsBySeverity": {"critical": 0, "high": 3, "medium": 0, "low": 0}}]}).encode()
    _capture_urlopen(monkeypatch, body)
    sn = SnykConnector({"SNYK_API_TOKEN": "t", "SNYK_ORG_ID": "org1"})
    assert sn.poll_state("p1").state == ConnectorState.FAILED


def test_poll_state_degraded_when_only_medium_issues(monkeypatch):
    from prash.connectors.base import ConnectorState

    body = json.dumps({"projects": [{"id": "p1", "name": "api", "issueCountsBySeverity": {"critical": 0, "high": 0, "medium": 4, "low": 1}}]}).encode()
    _capture_urlopen(monkeypatch, body)
    sn = SnykConnector({"SNYK_API_TOKEN": "t", "SNYK_ORG_ID": "org1"})
    assert sn.poll_state("p1").state == ConnectorState.DEGRADED


def test_poll_state_healthy_when_clean(monkeypatch):
    from prash.connectors.base import ConnectorState

    body = json.dumps({"projects": [{"id": "p1", "name": "api", "issueCountsBySeverity": {"critical": 0, "high": 0, "medium": 0, "low": 0}}]}).encode()
    _capture_urlopen(monkeypatch, body)
    sn = SnykConnector({"SNYK_API_TOKEN": "t", "SNYK_ORG_ID": "org1"})
    assert sn.poll_state("p1").state == ConnectorState.HEALTHY


def test_poll_state_not_found_when_project_missing(monkeypatch):
    from prash.connectors.base import ConnectorState

    _capture_urlopen(monkeypatch, json.dumps({"projects": []}).encode())
    sn = SnykConnector({"SNYK_API_TOKEN": "t", "SNYK_ORG_ID": "org1"})
    assert sn.poll_state("no such project").state == ConnectorState.NOT_FOUND


def test_fetch_logs_returns_severity_breakdown(monkeypatch):
    body = json.dumps({"projects": [{"id": "p1", "name": "api", "issueCountsBySeverity": {"critical": 1, "high": 2, "medium": 3, "low": 4}}]}).encode()
    _capture_urlopen(monkeypatch, body)
    sn = SnykConnector({"SNYK_API_TOKEN": "t", "SNYK_ORG_ID": "org1"})
    lines = sn.fetch_logs("p1")
    assert lines == ["critical: 1", "high: 2", "medium: 3", "low: 4"]


def test_ignore_issue_sends_temporary_ignore_with_reason(monkeypatch):
    calls = _capture_urlopen(monkeypatch, json.dumps({"ok": True}).encode())
    sn = SnykConnector({"SNYK_API_TOKEN": "t", "SNYK_ORG_ID": "org1"})
    sn.ignore_issue("proj-uuid", "issue-1", "false positive, verified manually")
    assert calls[0].full_url == "https://api.snyk.io/v1/org/org1/project/proj-uuid/ignore/issue-1"
    payload = json.loads(calls[0].data)
    assert payload["reason"] == "false positive, verified manually"
    assert payload["reasonType"] == "temporary-ignore"
    assert "expires" in payload
