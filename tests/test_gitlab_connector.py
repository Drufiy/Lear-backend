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


# ── G3: watch() / get_stats() — the autonomous-loop read surface (mirror of GitHub) ──

from datetime import datetime, timezone  # noqa: E402

from prash.connectors.gitlab import GitLabError  # noqa: E402


def _pipeline(pid, status="failed", updated_at="2026-09-07T12:00:00Z", **kw):
    return {
        "id": pid, "status": status, "ref": kw.get("ref", "main"),
        "sha": kw.get("sha", "abcd1234ef"), "created_at": kw.get("created_at", updated_at),
        "updated_at": updated_at, "web_url": kw.get("web_url", ""),
    }


def _gl_conn():
    return GitLabConnector({"GITLAB_TOKEN": "t"})


def test_get_stats_returns_events_sorted_and_filtered(monkeypatch):
    conn = _gl_conn()
    older, newer, ancient = "2026-09-07T12:00:00Z", "2026-09-07T12:05:00Z", "2026-09-07T02:00:00Z"
    monkeypatch.setattr(conn, "list_pipelines", lambda project, ref="", limit=30: [
        _pipeline(3, status="success", updated_at=newer),
        _pipeline(2, status="failed", updated_at=older),
        _pipeline(1, status="failed", updated_at=ancient),  # before `since`
    ])
    since = datetime(2026, 9, 7, 11, 0, tzinfo=timezone.utc)
    events = conn.get_stats("acme/api", since=since)
    assert len(events) == 2
    assert [e["timestamp"] for e in events] == sorted(e["timestamp"] for e in events)
    assert events[0]["event_type"] == "ci_failure" and events[1]["event_type"] == "ci_success"
    assert all(e["connector"] == "gitlab" for e in events)
    assert events[0]["raw"]["pipeline_id"] == 2


def test_get_stats_maps_running_to_in_progress(monkeypatch):
    conn = _gl_conn()
    monkeypatch.setattr(conn, "list_pipelines",
                        lambda project, ref="", limit=30: [_pipeline(9, status="running")])
    events = conn.get_stats("acme/api", since=datetime(2026, 9, 7, 11, 0, tzinfo=timezone.utc))
    assert len(events) == 1 and events[0]["event_type"] == "ci_in_progress"


def test_get_stats_empty_on_api_error(monkeypatch):
    conn = _gl_conn()

    def boom(*a, **k):
        raise GitLabError("GitLab API 404: not found")

    monkeypatch.setattr(conn, "list_pipelines", boom)
    assert conn.get_stats("acme/api") == []


def test_watch_first_poll_emits_only_failed_pipelines(monkeypatch):
    conn = _gl_conn()
    monkeypatch.setattr(conn, "list_pipelines", lambda project, limit=30: [
        _pipeline(1, status="failed"),
        _pipeline(2, status="success"),   # baselined silent
        _pipeline(3, status="running"),   # baselined silent
    ])
    events = conn.watch("acme/api").poll()
    assert len(events) == 1
    assert events[0]["raw"]["pipeline_id"] == 1 and events[0]["event_type"] == "ci_failure"


def test_watch_dedups_same_pipeline_across_polls(monkeypatch):
    conn = _gl_conn()
    monkeypatch.setattr(conn, "list_pipelines", lambda project, limit=30: [_pipeline(1, status="failed")])
    handle = conn.watch("acme/api")
    assert len(handle.poll()) == 1
    assert handle.poll() == []


def test_watch_emits_on_status_change(monkeypatch):
    conn = _gl_conn()
    scripted = iter([
        [_pipeline(1, status="running")],   # baselined silent
        [_pipeline(1, status="failed")],    # -> emit failure
        [_pipeline(1, status="success")],   # retry flipped -> emit success
    ])
    monkeypatch.setattr(conn, "list_pipelines", lambda project, limit=30: next(scripted))
    handle = conn.watch("acme/api")
    assert handle.poll() == []
    e2 = handle.poll()
    assert len(e2) == 1 and e2[0]["event_type"] == "ci_failure"
    e3 = handle.poll()
    assert len(e3) == 1 and e3[0]["event_type"] == "ci_success"


def test_backoff_honors_retry_after():
    import urllib.error
    exc = urllib.error.HTTPError("u", 429, "rate limited", {"Retry-After": "5"}, None)
    assert GitLabConnector._backoff_seconds(0, exc) == 5.0


def test_backoff_waits_for_ratelimit_reset(monkeypatch):
    import urllib.error
    monkeypatch.setattr("prash.connectors.gitlab.time.time", lambda: 2000.0)
    exc = urllib.error.HTTPError(
        "u", 429, "rate limited", {"RateLimit-Remaining": "0", "RateLimit-Reset": "2012"}, None)
    assert GitLabConnector._backoff_seconds(0, exc) == 12.0
