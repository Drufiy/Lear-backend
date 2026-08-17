"""GitLab connector (Sprint 2 Tier 2, PRASH_V2.md §7b). Unit-level checks on
the request plumbing itself -- project-path encoding, auth header, and the
create_commit/start_branch payload shape -- the things a fake-connector test
in test_actions.py can't see because it replaces this module entirely."""

from __future__ import annotations

import json
import urllib.request

from prash.connectors.gitlab import GitLabConnector


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


def test_authenticate_sends_private_token_header(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"username": "aradhya"}')
    gl = GitLabConnector({"GITLAB_TOKEN": "glpat-secret"})
    assert gl.authenticate() is True
    assert calls[0].get_header("Private-token") == "glpat-secret"
    assert calls[0].full_url == "https://gitlab.com/api/v4/user"


def test_authenticate_false_without_token():
    gl = GitLabConnector({})
    assert gl.authenticate() is False


def test_locate_url_encodes_namespaced_project():
    gl = GitLabConnector({"GITLAB_TOKEN": "t"})
    located = gl.locate("acme-group/sub-group/api")
    assert located["project"] == "acme-group/sub-group/api"
    assert located["project_id"] == "acme-group%2Fsub-group%2Fapi"


def test_get_repo_uses_encoded_project_id(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"default_branch": "main"}')
    gl = GitLabConnector({"GITLAB_TOKEN": "t"})
    repo = gl.get_repo("acme/api")
    assert repo["default_branch"] == "main"
    assert calls[0].full_url == "https://gitlab.com/api/v4/projects/acme%2Fapi"


def test_create_commit_sends_start_branch_and_actions(monkeypatch):
    calls = _capture_urlopen(monkeypatch, b'{"id": "abc123"}')
    gl = GitLabConnector({"GITLAB_TOKEN": "t"})
    actions = [{"action": "update", "file_path": "app.py", "content": "x = 1\n"}]
    commit = gl.create_commit("acme/api", "prash/fix-1", "Prash: fix", actions, start_branch="main")
    assert commit["id"] == "abc123"
    payload = json.loads(calls[0].data)
    assert payload == {
        "branch": "prash/fix-1",
        "commit_message": "Prash: fix",
        "actions": actions,
        "start_branch": "main",
    }


def test_job_trace_returns_raw_text_not_json(monkeypatch):
    """The trace endpoint is the one place GitLab's API returns plain text
    instead of JSON -- must not be run through json.loads like every other
    call in this connector."""
    _capture_urlopen(monkeypatch, b"Running job...\n$ pytest\nFAILED tests/test_foo.py\n")
    gl = GitLabConnector({"GITLAB_TOKEN": "t"})
    trace = gl.job_trace("acme/api", 42)
    assert "FAILED tests/test_foo.py" in trace
