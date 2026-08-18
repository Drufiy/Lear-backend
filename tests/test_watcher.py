"""Track E — the watcher (PRASH_V2.md §6, days 9-11).

detect_changes() is the module's core logic and fully pure -- these tests
cover it directly. run_watch_loop() is a thin I/O wrapper around it (poll,
detect, notify, sleep); tested with get_pod_status and the notification
call both mocked, bounded to a couple of iterations via max_iterations so a
test can't hang.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

from prash.connectors.kubernetes import PodStatus
from prash.watcher import (
    _applescript_escape,
    _send_desktop_notification,
    detect_changes,
    run_watch_loop,
)


def _pod(name="api-7f9d", namespace="production", problem=None, restart_count=0, ready=True, phase="Running"):
    return PodStatus(name=name, namespace=namespace, phase=phase, problem=problem, restart_count=restart_count, ready=ready)


# ── detect_changes: the core dedup/transition logic ────────────────────────

def test_first_sighting_of_a_broken_pod_is_reported():
    changed, state = detect_changes([_pod(problem="CrashLoopBackOff")], {})
    assert len(changed) == 1
    assert changed[0].problem == "CrashLoopBackOff"
    assert state == {"production/api-7f9d": "CrashLoopBackOff"}


def test_healthy_pod_never_reported():
    changed, state = detect_changes([_pod(problem=None)], {})
    assert changed == []
    assert state == {"production/api-7f9d": None}


def test_same_problem_across_polls_not_reported_again():
    """The core dedup guarantee -- an ongoing CrashLoopBackOff must not spam
    a notification every 30s, only once when it first appears."""
    previous_state = {"production/api-7f9d": "CrashLoopBackOff"}
    changed, state = detect_changes([_pod(problem="CrashLoopBackOff", restart_count=40)], previous_state)
    assert changed == []
    assert state == {"production/api-7f9d": "CrashLoopBackOff"}


def test_problem_changing_is_reported_again():
    """CrashLoopBackOff -> OOMKilled is a materially different situation --
    worth a fresh ping, not silently absorbed into 'already notified'."""
    previous_state = {"production/api-7f9d": "CrashLoopBackOff"}
    changed, _state = detect_changes([_pod(problem="OOMKilled")], previous_state)
    assert len(changed) == 1
    assert changed[0].problem == "OOMKilled"


def test_pod_resolving_updates_state_but_is_not_reported():
    previous_state = {"production/api-7f9d": "CrashLoopBackOff"}
    changed, state = detect_changes([_pod(problem=None)], previous_state)
    assert changed == []
    assert state == {"production/api-7f9d": None}


def test_pod_recovering_then_breaking_again_is_reported():
    """A pod that resolves and later breaks again must re-notify -- 'already
    saw this key' isn't the rule, 'current problem == last recorded problem' is."""
    previous_state = {"production/api-7f9d": None}
    changed, _ = detect_changes([_pod(problem="CrashLoopBackOff")], previous_state)
    assert len(changed) == 1


def test_deleted_pod_drops_out_of_state():
    previous_state = {"production/old-pod": "CrashLoopBackOff"}
    changed, state = detect_changes([], previous_state)
    assert changed == []
    assert state == {}


def test_multiple_pods_tracked_independently():
    pods = [
        _pod(name="a", problem="CrashLoopBackOff"),
        _pod(name="b", problem=None),
        _pod(name="c", problem="OOMKilled"),
    ]
    changed, state = detect_changes(pods, {})
    assert {p.name for p in changed} == {"a", "c"}
    assert len(state) == 3


def test_pod_key_scoped_by_namespace_not_just_name():
    """Same pod name in two namespaces, already-known in one, must still be
    reported as a fresh sighting in the other -- the key must include
    namespace, not just name, or this would be wrongly deduped."""
    previous_state = {"staging/api": "OOMKilled"}  # already known/notified in staging
    pods = [
        _pod(name="api", namespace="staging", problem="OOMKilled"),      # unchanged -- no re-notify
        _pod(name="api", namespace="production", problem="OOMKilled"),  # same name, different namespace -- new
    ]
    changed, state = detect_changes(pods, previous_state)
    assert {p.namespace for p in changed} == {"production"}
    assert state == {"staging/api": "OOMKilled", "production/api": "OOMKilled"}


# ── run_watch_loop: the I/O wrapper, mocked ─────────────────────────────────

def test_watch_loop_notifies_once_for_a_persistent_problem(monkeypatch):
    """Two polls of the SAME ongoing CrashLoopBackOff must notify exactly
    once, not twice -- the actual regression this whole module exists to
    prevent (spamming the user every poll interval)."""
    import prash.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "get_pod_status", lambda ns: [_pod(problem="CrashLoopBackOff")])
    monkeypatch.setattr(watcher_mod, "time", MagicMock())  # no real sleeping in tests
    notify_calls = []
    monkeypatch.setattr(watcher_mod, "_notify", lambda pod, console=None, creds=None: notify_calls.append(pod))

    run_watch_loop("production", interval=0, max_iterations=2)
    assert len(notify_calls) == 1


def test_watch_loop_notifies_again_when_problem_changes(monkeypatch):
    import prash.watcher as watcher_mod

    calls = iter([
        [_pod(problem="CrashLoopBackOff")],
        [_pod(problem="OOMKilled")],
    ])
    monkeypatch.setattr(watcher_mod, "get_pod_status", lambda ns: next(calls))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    notify_calls = []
    monkeypatch.setattr(watcher_mod, "_notify", lambda pod, console=None, creds=None: notify_calls.append(pod.problem))

    run_watch_loop("production", interval=0, max_iterations=2)
    assert notify_calls == ["CrashLoopBackOff", "OOMKilled"]


# ── desktop notification fallback chain ─────────────────────────────────────

def test_applescript_escape_handles_quotes_and_backslashes():
    """Unescaped user-influenced text (pod names, messages) going into an
    AppleScript string literal is a real injection surface, not theoretical --
    escape it properly rather than trusting k8s object names to be quote-free."""
    assert _applescript_escape('say "hi"') == 'say \\"hi\\"'
    assert _applescript_escape("back\\slash") == "back\\\\slash"


def test_send_desktop_notification_true_when_plyer_succeeds(monkeypatch):

    fake_plyer = MagicMock()
    monkeypatch.setitem(sys.modules, "plyer", MagicMock(notification=fake_plyer))
    assert _send_desktop_notification("title", "message") is True
    fake_plyer.notify.assert_called_once()


def test_send_desktop_notification_falls_back_to_osascript_on_macos(monkeypatch):
    """The real bug found live (2026-08-09): plyer's macOS backend needs a
    proper app-bundle identity that a plain CLI process doesn't have --
    raises AttributeError, not ImportError, so this must be caught broadly
    and fall through to osascript rather than propagating."""
    import prash.watcher as watcher_mod

    def boom(*a, **k):
        raise AttributeError("'NoneType' object has no attribute 'setDelegate_'")

    monkeypatch.setitem(sys.modules, "plyer", MagicMock(notification=MagicMock(notify=boom)))
    monkeypatch.setattr(watcher_mod.sys, "platform", "darwin")
    run_mock = MagicMock()
    monkeypatch.setattr(watcher_mod.subprocess, "run", run_mock)

    assert _send_desktop_notification("title", "message") is True
    run_mock.assert_called_once()
    assert run_mock.call_args.args[0][0] == "osascript"


def test_send_desktop_notification_false_when_everything_fails(monkeypatch):
    import prash.watcher as watcher_mod

    monkeypatch.setitem(
        sys.modules, "plyer",
        MagicMock(notification=MagicMock(notify=MagicMock(side_effect=RuntimeError("no backend")))),
    )
    monkeypatch.setattr(watcher_mod.sys, "platform", "darwin")
    monkeypatch.setattr(watcher_mod.subprocess, "run", MagicMock(side_effect=RuntimeError("osascript missing")))

    assert _send_desktop_notification("title", "message") is False


def test_send_desktop_notification_false_on_non_macos_when_plyer_fails(monkeypatch):
    import prash.watcher as watcher_mod

    monkeypatch.setitem(
        sys.modules, "plyer",
        MagicMock(notification=MagicMock(notify=MagicMock(side_effect=RuntimeError("no backend")))),
    )
    monkeypatch.setattr(watcher_mod.sys, "platform", "linux")

    assert _send_desktop_notification("title", "message") is False


def test_watch_loop_returns_final_state(monkeypatch):
    import prash.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "get_pod_status", lambda ns: [_pod(problem="ImagePullBackOff")])
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    monkeypatch.setattr(watcher_mod, "_notify", lambda pod, console=None, creds=None: None)

    state = run_watch_loop("production", interval=0, max_iterations=1)
    assert state == {"production/api-7f9d": "ImagePullBackOff"}


# ── team notifications (Sprint 2 Tier 2, PRASH_V2.md §7b) ───────────────────

def test_notify_pushes_team_notification_when_creds_given(monkeypatch):
    """When .env has a webhook, a new-problem ping must also reach the team
    channel, not just the one laptop's desktop toast."""
    import prash.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "_send_desktop_notification", lambda t, m: True)
    sent: list = []
    monkeypatch.setattr(
        watcher_mod, "send_team_notifications",
        lambda creds, title, message: sent.append((creds, title, message)) or {"slack": True},
    )

    creds = {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/x"}
    watcher_mod._notify(_pod(problem="CrashLoopBackOff"), creds=creds)

    assert len(sent) == 1
    assert sent[0][0] == creds
    assert "CrashLoopBackOff" in sent[0][1]
    assert "api-7f9d" in sent[0][2]


def test_notify_skips_team_channels_without_creds(monkeypatch):
    """No webhook configured -> no team send attempted at all (existing
    watcher behaviour unchanged for the desktop-only setup)."""
    import prash.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "_send_desktop_notification", lambda t, m: True)

    def boom(creds, title, message):
        raise AssertionError("must not send team notifications without creds")

    monkeypatch.setattr(watcher_mod, "send_team_notifications", boom)
    watcher_mod._notify(_pod(problem="CrashLoopBackOff"))


def test_watch_loop_passes_creds_through_to_notify(monkeypatch):
    """The loop must hand the .env dict to _notify so the ping reaches the
    team channel -- otherwise cmd_watch loading creds would be pointless."""
    import prash.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "get_pod_status", lambda ns: [_pod(problem="CrashLoopBackOff")])
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    seen: dict = {}
    monkeypatch.setattr(
        watcher_mod, "_notify",
        lambda pod, console=None, creds=None: seen.setdefault("creds", creds),
    )

    creds = {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/x"}
    run_watch_loop("production", interval=0, max_iterations=1, creds=creds)
    assert seen["creds"] == creds
