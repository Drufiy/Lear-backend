"""GitHubConnector.get_dependabot_alerts() (Sprint 2 Tier 3, PRASH_V2.md
§7b). The connector predates this repo's monkeypatched-urlopen test
convention (it's tested indirectly via FakeGitHub elsewhere), so this file
covers only the new method, same style as the other Tier 3 connector
tests."""

from __future__ import annotations

import json
import urllib.request

from prash.connectors.github import GitHubConnector


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture_urlopen(monkeypatch, body: bytes = b"[]"):
    calls = []

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def test_get_dependabot_alerts_defaults_to_open_state(monkeypatch):
    body = json.dumps([{"number": 1, "dependency": {"package": {"name": "lodash"}}, "security_vulnerability": {"severity": "high"}}]).encode()
    calls = _capture_urlopen(monkeypatch, body)
    gh = GitHubConnector({"GITHUB_TOKEN": "t"})
    alerts = gh.get_dependabot_alerts("acme/api")
    assert calls[0].full_url == "https://api.github.com/repos/acme/api/dependabot/alerts?state=open"
    assert alerts[0]["number"] == 1


def test_get_dependabot_alerts_empty_state_omits_query_param(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b"[]")
    gh = GitHubConnector({"GITHUB_TOKEN": "t"})
    gh.get_dependabot_alerts("acme/api", state="")
    assert calls[0].full_url == "https://api.github.com/repos/acme/api/dependabot/alerts"
