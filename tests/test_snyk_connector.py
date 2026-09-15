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


def _capture_urlopen(monkeypatch, body: bytes = b"{}", bodies: list[bytes] | None = None):
    calls = []
    responses = iter(bodies or [body])

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        return _FakeResponse(next(responses))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def test_authenticate_sends_token_header(monkeypatch):
    # /v1/org/{id} is Snyk's now fully-removed v1 API (found live 2026-09-16:
    # 404 "unsupported url" against a real account) -- authenticate() uses
    # the REST replacement, /rest/orgs/{id}.
    calls = _capture_urlopen(monkeypatch, bodies=[
        b'{"data": {"type": "self"}}',
        b'{"data": {"attributes": {"name": "Security Team"}}}',
    ])
    sn = SnykConnector({"SNYK_API_TOKEN": "snyk-secret", "SNYK_ORG_ID": "org-1"})
    assert sn.authenticate() is True
    assert calls[0].get_header("Authorization") == "token snyk-secret"
    assert calls[0].full_url == "https://api.snyk.io/rest/self?version=2024-10-15"
    assert calls[1].full_url == "https://api.snyk.io/rest/orgs/org-1?version=2024-10-15"
    assert sn.auth_identity == {"org": "Security Team"}
    assert sn.auth_error is None


def test_authenticate_succeeds_even_when_org_lookup_is_forbidden(monkeypatch):
    """Found live: a real token on a real account can pass /rest/self but get
    403 Forbidden on /rest/orgs/{id} (a token-scope gap, not proof the
    connection is bad). authenticate() must not fail just because the org
    name couldn't be fetched -- fall back to the raw org id."""
    import io
    import urllib.error

    call_count = {"n": 0}

    def fake_urlopen(req, timeout=30):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _FakeResponse(b'{"data": {"type": "self"}}')
        raise urllib.error.HTTPError(req.full_url, 403, "forbidden", {}, io.BytesIO(b'{"error": "Forbidden"}'))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    sn = SnykConnector({"SNYK_API_TOKEN": "snyk-secret", "SNYK_ORG_ID": "org-1"})
    assert sn.authenticate() is True
    assert sn.auth_identity == {"org": "org-1"}
    assert sn.auth_error is None


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
