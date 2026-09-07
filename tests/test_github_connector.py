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


# ── G1: watch() / get_stats() — the autonomous-loop read surface ──

from datetime import datetime, timezone  # noqa: E402

from prash.connectors.base import ConnectorState  # noqa: E402
from prash.connectors.github import GitHubError, _GitHubWatchHandle  # noqa: E402


def _run(run_id, status="completed", conclusion="failure", updated_at="2026-09-06T20:00:00Z", **kw):
    return {
        "id": run_id, "status": status, "conclusion": conclusion,
        "name": kw.get("name", "CI"), "run_number": kw.get("run_number", run_id),
        "head_branch": kw.get("branch", "main"), "head_sha": kw.get("sha", "abc1234def56"),
        "created_at": kw.get("created_at", updated_at), "updated_at": updated_at,
    }


def _conn():
    return GitHubConnector({"GITHUB_TOKEN": "t"})


def test_get_stats_returns_events_sorted_ascending_and_filtered(monkeypatch):
    conn = _conn()
    older, newer, ancient = "2026-09-06T20:00:00Z", "2026-09-06T20:05:00Z", "2026-09-06T10:00:00Z"
    monkeypatch.setattr(conn, "workflow_runs", lambda repo, branch="", limit=30: [
        _run(3, conclusion="success", updated_at=newer),
        _run(2, conclusion="failure", updated_at=older),
        _run(1, conclusion="failure", updated_at=ancient),  # before `since` -> filtered
    ])
    since = datetime(2026, 9, 6, 19, 0, tzinfo=timezone.utc)
    events = conn.get_stats("acme/api", since=since)

    assert len(events) == 2
    assert [e["timestamp"] for e in events] == sorted(e["timestamp"] for e in events)  # ascending
    assert events[0]["event_type"] == "ci_failure" and events[1]["event_type"] == "ci_success"
    assert all(e["connector"] == "github" for e in events)
    assert events[0]["raw"]["run_id"] == 2


def test_get_stats_maps_in_progress_runs(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(conn, "workflow_runs",
                        lambda repo, branch="", limit=30: [_run(9, status="in_progress", conclusion=None)])
    events = conn.get_stats("acme/api", since=datetime(2026, 9, 6, 19, 0, tzinfo=timezone.utc))
    assert len(events) == 1 and events[0]["event_type"] == "ci_in_progress"


def test_get_stats_empty_on_api_error(monkeypatch):
    conn = _conn()

    def boom(*a, **k):
        raise GitHubError("GitHub API 404: not found")

    monkeypatch.setattr(conn, "workflow_runs", boom)
    assert conn.get_stats("acme/api") == []


def test_watch_first_poll_emits_only_completed_failures(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(conn, "workflow_runs", lambda repo, limit=30: [
        _run(1, conclusion="failure"),
        _run(2, conclusion="success"),                       # baselined silent
        _run(3, status="in_progress", conclusion=None),      # baselined silent
    ])
    events = conn.watch("acme/api").poll()
    assert len(events) == 1
    assert events[0]["raw"]["run_id"] == 1 and events[0]["event_type"] == "ci_failure"


def test_watch_dedups_same_run_across_polls(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(conn, "workflow_runs", lambda repo, limit=30: [_run(1, conclusion="failure")])
    handle = conn.watch("acme/api")
    assert len(handle.poll()) == 1     # first sighting of a broken run -> emit
    assert handle.poll() == []          # unchanged -> silent


def test_watch_emits_on_outcome_change(monkeypatch):
    conn = _conn()
    scripted = iter([
        [_run(1, status="in_progress", conclusion=None)],   # poll 1: baselined silent
        [_run(1, conclusion="failure")],                     # poll 2: now failed -> emit
        [_run(1, conclusion="success")],                     # poll 3: rerun flipped -> emit
    ])
    monkeypatch.setattr(conn, "workflow_runs", lambda repo, limit=30: next(scripted))
    handle = conn.watch("acme/api")
    assert handle.poll() == []
    e2 = handle.poll()
    assert len(e2) == 1 and e2[0]["event_type"] == "ci_failure"
    e3 = handle.poll()
    assert len(e3) == 1 and e3[0]["event_type"] == "ci_success"


def test_backoff_honors_retry_after():
    import urllib.error
    exc = urllib.error.HTTPError("u", 429, "rate limited", {"Retry-After": "7"}, None)
    assert GitHubConnector._backoff_seconds(0, exc) == 7.0


def test_backoff_waits_for_primary_ratelimit_reset(monkeypatch):
    import urllib.error
    monkeypatch.setattr("prash.connectors.github.time.time", lambda: 1000.0)
    exc = urllib.error.HTTPError(
        "u", 403, "forbidden", {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1010"}, None)
    assert GitHubConnector._backoff_seconds(0, exc) == 10.0
