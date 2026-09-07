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
    run_datadog_watch_loop,
    run_pagerduty_watch_loop,
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


# ── M5: the unified interface-driven multi-connector loop ───────────────────

import datetime as _dt

from prash.connectors.base import ConnectorState, ResourceState
from prash.watcher import run_connector_watch_loop


class _FakeConn:
    """Minimal Connector stand-in: canned poll_state + get_stats."""

    def __init__(self, state="healthy", events=None, stats_error=None):
        self._state = state
        self._events = events or []
        self._stats_error = stats_error
        self.stats_calls = 0

    def poll_state(self, target):
        return ResourceState(target, ConnectorState(self._state), {})

    def get_stats(self, target, since=None):
        self.stats_calls += 1
        if self._stats_error is not None:
            raise self._stats_error
        return list(self._events)


def _event(event_type="cpu_spike", summary="CPU high", ts=None):
    return {
        "timestamp": ts or _dt.datetime(2026, 9, 6, 12, 0, tzinfo=_dt.timezone.utc),
        "connector": "aws",
        "event_type": event_type,
        "summary": summary,
        "raw": {},
    }


def _capture_notifications(monkeypatch):
    fired = []
    monkeypatch.setattr(
        "prash.watcher._notify_event",
        lambda provider, target, event_type, summary, console=None, creds=None: fired.append(
            (provider, target, event_type)
        ),
    )
    monkeypatch.setattr("prash.watcher.time", MagicMock())  # no real sleeping in tests
    return fired


def test_connector_loop_notifies_on_new_event(monkeypatch):
    fired = _capture_notifications(monkeypatch)
    conn = _FakeConn(state="healthy", events=[_event("cpu_spike")])
    run_connector_watch_loop([(conn, "i-1", "aws")], interval=0, max_iterations=1)
    assert ("aws", "i-1", "cpu_spike") in fired


def test_connector_loop_dedups_same_event_across_cycles(monkeypatch):
    fired = _capture_notifications(monkeypatch)
    conn = _FakeConn(state="healthy", events=[_event("cpu_spike")])
    run_connector_watch_loop([(conn, "i-1", "aws")], interval=0, max_iterations=3)
    # same event_type+timestamp every cycle -> notified exactly once
    assert fired.count(("aws", "i-1", "cpu_spike")) == 1
    assert conn.stats_calls == 3  # but it did poll all three cycles


def test_connector_loop_notifies_on_degraded_state(monkeypatch):
    fired = _capture_notifications(monkeypatch)
    conn = _FakeConn(state="failed", events=[])
    run_connector_watch_loop([(conn, "i-1", "aws")], interval=0, max_iterations=2)
    # failed state notified once (deduped), no get_stats events
    assert fired == [("aws", "i-1", "failed")]


def test_connector_loop_reads_all_watches_in_one_cycle(monkeypatch):
    fired = _capture_notifications(monkeypatch)
    aws = _FakeConn(state="healthy", events=[_event("cpu_spike", "aws cpu")])
    gcp = _FakeConn(state="healthy", events=[_event("disk_full", "gcp disk")])
    run_connector_watch_loop(
        [(aws, "i-1", "aws"), (gcp, "vm-2", "gcp")], interval=0, max_iterations=1
    )
    assert ("aws", "i-1", "cpu_spike") in fired
    assert ("gcp", "vm-2", "disk_full") in fired
    assert aws.stats_calls == 1 and gcp.stats_calls == 1  # both read, parallel fan-out


def test_connector_loop_survives_a_flaky_connector(monkeypatch):
    _capture_notifications(monkeypatch)
    boom = _FakeConn(state="healthy", stats_error=ValueError("api blew up"))
    ok = _FakeConn(state="healthy", events=[_event("cpu_spike")])
    # must not raise even though one connector's get_stats throws
    seen = run_connector_watch_loop(
        [(boom, "i-1", "aws"), (ok, "vm-2", "gcp")], interval=0, max_iterations=1
    )
    assert ("gcp", "vm-2") in seen  # healthy one still tracked


def test_connector_loop_skips_connectors_without_get_stats(monkeypatch):
    fired = _capture_notifications(monkeypatch)

    class _NoStats(_FakeConn):
        def get_stats(self, target, since=None):
            raise NotImplementedError

    conn = _NoStats(state="failed")
    # NotImplementedError is swallowed; poll_state-based notify still fires
    run_connector_watch_loop([(conn, "x", "azure")], interval=0, max_iterations=1)
    assert ("azure", "x", "failed") in fired


# ── datadog watch loop (connector rewrite M4) ────────────────────────────────

def _dd_event(event_type="monitor_alert", summary="Monitor 'cpu-high' entered Alert state"):
    from prash.connectors.base import ConnectorEvent
    from datetime import datetime, timezone

    return ConnectorEvent(
        timestamp=datetime.now(timezone.utc),
        connector="datadog",
        event_type=event_type,
        summary=summary,
        raw={"monitor_id": 42, "monitor_name": "cpu-high", "previous_state": "OK", "current_state": "Alert"},
    )


class _FakeDdHandle:
    """Mimics DatadogConnector.watch()'s WatchHandle: scripted poll() results."""

    def __init__(self, script):
        self.script = iter(script)
        self.target = "cpu-high"
        self.monitor_name = "cpu-high"

    def poll(self):
        result = next(self.script)
        if isinstance(result, Exception):
            raise result
        return result


class _FakeDdConnector:
    def __init__(self, handle, auth_ok=True):
        self._handle = handle
        self._auth_ok = auth_ok
        self.watched = []

    def authenticate(self):
        return self._auth_ok

    def watch(self, monitor, interval=30):
        self.watched.append(monitor)
        return self._handle


def test_datadog_watch_loop_notifies_on_transition(monkeypatch):
    import prash.watcher as watcher_mod

    handle = _FakeDdHandle(script=[[_dd_event()], []])
    monkeypatch.setattr(watcher_mod, "DatadogConnector", lambda creds: _FakeDdConnector(handle))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    notified = []
    monkeypatch.setattr(watcher_mod, "_notify_datadog", lambda event, console=None, creds=None: notified.append(event))

    run_datadog_watch_loop(["cpu-high"], interval=0, max_iterations=2)

    assert len(notified) == 1  # the transition fires once; the next poll is silent
    assert notified[0]["event_type"] == "monitor_alert"


def test_datadog_watch_loop_survives_poll_errors(monkeypatch):
    """A rate-limited or unreachable API must warn and skip the cycle — the
    watch loop never dies on a bad API day."""
    import prash.watcher as watcher_mod
    from prash.connectors.datadog import DatadogError

    handle = _FakeDdHandle(script=[DatadogError("Datadog API 429: rate limited"), [_dd_event()]])
    monkeypatch.setattr(watcher_mod, "DatadogConnector", lambda creds: _FakeDdConnector(handle))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    notified = []
    monkeypatch.setattr(watcher_mod, "_notify_datadog", lambda event, console=None, creds=None: notified.append(event))

    run_datadog_watch_loop(["cpu-high"], interval=0, max_iterations=2)
    assert len(notified) == 1  # cycle 1 skipped, cycle 2 still delivered


def test_datadog_watch_loop_skips_unwatchable_monitor(monkeypatch):
    import prash.watcher as watcher_mod
    from prash.connectors.datadog import DatadogError

    class _BrokenWatchConnector(_FakeDdConnector):
        def watch(self, monitor, interval=30):
            raise DatadogError(f"monitor not found: {monitor}")

    monkeypatch.setattr(watcher_mod, "DatadogConnector", lambda creds: _BrokenWatchConnector(None))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())

    run_datadog_watch_loop(["ghost"], interval=0, max_iterations=1)  # must not raise


def test_datadog_watch_loop_warns_on_failed_auth(monkeypatch):
    import prash.watcher as watcher_mod

    handle = _FakeDdHandle(script=[[]])
    fake = _FakeDdConnector(handle, auth_ok=False)
    monkeypatch.setattr(watcher_mod, "DatadogConnector", lambda creds: fake)
    monkeypatch.setattr(watcher_mod, "time", MagicMock())

    run_datadog_watch_loop(["cpu-high"], interval=0, max_iterations=1)  # warns, still watches


def test_resolve_datadog_monitors_splits_comma_list():
    from prash.watcher import resolve_datadog_monitors

    assert resolve_datadog_monitors("cpu-high, api-errors") == ["cpu-high", "api-errors"]


def test_resolve_datadog_monitors_requires_targets(monkeypatch):
    from prash.watcher import resolve_datadog_monitors

    monkeypatch.delenv("DATADOG_WATCH_MONITORS", raising=False)
    try:
        resolve_datadog_monitors(None)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "DATADOG_WATCH_MONITORS" in str(exc)


def test_resolve_datadog_monitors_env_fallback(monkeypatch):
    from prash.watcher import resolve_datadog_monitors

    monkeypatch.setenv("DATADOG_WATCH_MONITORS", "cpu-high")
    assert resolve_datadog_monitors(None) == ["cpu-high"]


def test_resolve_datadog_monitors_all_expands_via_connector(monkeypatch):
    import prash.watcher as watcher_mod

    class _ListConnector:
        def list_monitors(self, query=None, limit=100):
            return [{"monitor_id": 1, "name": "api errors"}, {"monitor_id": 2, "name": ""}]

    monkeypatch.setattr(watcher_mod, "DatadogConnector", lambda creds: _ListConnector())
    assert watcher_mod.resolve_datadog_monitors("all") == ["api errors", "2"]


def test_notify_datadog_pushes_team_notification_when_creds_given(monkeypatch):
    import prash.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "_send_desktop_notification", lambda t, m: True)
    sent = []
    monkeypatch.setattr(
        watcher_mod, "send_team_notifications",
        lambda creds, title, message: sent.append((title, message)) or {"slack": True},
    )

    creds = {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/x"}
    watcher_mod._notify_datadog(_dd_event(), creds=creds)

    assert len(sent) == 1
    assert "entered Alert state" in sent[0][0]
    assert "prash investigate cpu-high --provider datadog" in sent[0][1]


# ── pagerduty watch loop (connector rewrite, Phase 3 rollout) ────────────────

def _pd_event(event_type="incident_triggered",
              summary="Incident '500s spiking' on checkout triggered (critical severity, high urgency)"):
    from datetime import datetime, timezone

    return ConnectorEvent(
        timestamp=datetime.now(timezone.utc),
        connector="pagerduty",
        event_type=event_type,
        summary=summary,
        raw={"incident_id": "PINC1", "service_name": "checkout", "severity": "critical",
             "previous_status": None, "status": "triggered"},
    )


from prash.connectors.base import ConnectorEvent  # noqa: E402 — used by the _pd_event helper above


class _FakePdHandle:
    def __init__(self, script):
        self.script = iter(script)
        self.target = "checkout"
        self.service_name = "checkout"

    def poll(self):
        result = next(self.script)
        if isinstance(result, Exception):
            raise result
        return result


class _FakePdConnector:
    def __init__(self, handle, auth_ok=True):
        self._handle = handle
        self._auth_ok = auth_ok
        self.watched = []

    def authenticate(self):
        return self._auth_ok

    def watch(self, service, interval=30):
        self.watched.append(service)
        return self._handle


def test_pagerduty_watch_loop_notifies_on_transition(monkeypatch):
    import prash.watcher as watcher_mod

    handle = _FakePdHandle(script=[[_pd_event()], []])
    monkeypatch.setattr(watcher_mod, "PagerDutyConnector", lambda creds: _FakePdConnector(handle))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    notified = []
    monkeypatch.setattr(watcher_mod, "_notify_pagerduty", lambda event, console=None, creds=None: notified.append(event))

    run_pagerduty_watch_loop(["checkout"], interval=0, max_iterations=2)

    assert len(notified) == 1
    assert notified[0]["event_type"] == "incident_triggered"


def test_pagerduty_watch_loop_survives_poll_errors(monkeypatch):
    """A rate-limited or unreachable PagerDuty API must warn and skip the
    cycle -- the loop never dies on a bad API day."""
    import prash.watcher as watcher_mod
    from prash.connectors.pagerduty import PagerDutyError

    handle = _FakePdHandle(script=[PagerDutyError("PagerDuty API 429: rate limited"), [_pd_event()]])
    monkeypatch.setattr(watcher_mod, "PagerDutyConnector", lambda creds: _FakePdConnector(handle))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    notified = []
    monkeypatch.setattr(watcher_mod, "_notify_pagerduty", lambda event, console=None, creds=None: notified.append(event))

    run_pagerduty_watch_loop(["checkout"], interval=0, max_iterations=2)
    assert len(notified) == 1


def test_pagerduty_watch_loop_skips_unwatchable_service(monkeypatch):
    import prash.watcher as watcher_mod
    from prash.connectors.pagerduty import PagerDutyError

    class _BrokenWatchConnector(_FakePdConnector):
        def watch(self, service, interval=30):
            raise PagerDutyError(f"service not found: {service}")

    monkeypatch.setattr(watcher_mod, "PagerDutyConnector", lambda creds: _BrokenWatchConnector(None))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())

    run_pagerduty_watch_loop(["ghost"], interval=0, max_iterations=1)  # must not raise


def test_pagerduty_watch_loop_warns_on_failed_auth(monkeypatch):
    import prash.watcher as watcher_mod

    handle = _FakePdHandle(script=[[]])
    monkeypatch.setattr(watcher_mod, "PagerDutyConnector", lambda creds: _FakePdConnector(handle, auth_ok=False))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())

    run_pagerduty_watch_loop(["checkout"], interval=0, max_iterations=1)  # warns, still watches


def test_resolve_pagerduty_services_splits_comma_list():
    from prash.watcher import resolve_pagerduty_services

    assert resolve_pagerduty_services("checkout, api") == ["checkout", "api"]


def test_resolve_pagerduty_services_requires_targets(monkeypatch):
    from prash.watcher import resolve_pagerduty_services

    monkeypatch.delenv("PAGERDUTY_WATCH_SERVICES", raising=False)
    try:
        resolve_pagerduty_services(None)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "PAGERDUTY_WATCH_SERVICES" in str(exc)


def test_resolve_pagerduty_services_env_fallback(monkeypatch):
    from prash.watcher import resolve_pagerduty_services

    monkeypatch.setenv("PAGERDUTY_WATCH_SERVICES", "checkout")
    assert resolve_pagerduty_services(None) == ["checkout"]


def test_resolve_pagerduty_services_all_expands_via_connector(monkeypatch):
    import prash.watcher as watcher_mod

    class _ListConnector:
        def list_services(self, limit=100):
            return [{"service_id": "PSVC1", "name": "checkout"}, {"service_id": "PSVC2", "name": ""}]

    monkeypatch.setattr(watcher_mod, "PagerDutyConnector", lambda creds: _ListConnector())
    assert watcher_mod.resolve_pagerduty_services("all") == ["checkout", "PSVC2"]


def test_notify_pagerduty_pushes_team_notification_when_creds_given(monkeypatch):
    import prash.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "_send_desktop_notification", lambda t, m: True)
    sent = []
    monkeypatch.setattr(
        watcher_mod, "send_team_notifications",
        lambda creds, title, message: sent.append((title, message)) or {"slack": True},
    )

    creds = {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/x"}
    watcher_mod._notify_pagerduty(_pd_event(), creds=creds)

    assert len(sent) == 1
    assert "500s spiking" in sent[0][0]
    assert "prash investigate checkout --provider pagerduty" in sent[0][1]


# ── G2: GitHub Actions watch loop + repo resolution ──

def _gh_event(event_type="ci_failure", repo="acme/api"):
    import datetime as _dt
    return {
        "timestamp": _dt.datetime(2026, 9, 7, 12, 0, tzinfo=_dt.timezone.utc),
        "connector": "github", "event_type": event_type,
        "summary": f"CI run #7 {event_type} on main (abc1234)",
        "raw": {"run_id": 7, "repo": repo},
    }


class _FakeGhHandle:
    def __init__(self, script):
        self.script = iter(script)
        self.connector = "github"
        self.target = "acme/api"

    def poll(self):
        result = next(self.script)
        if isinstance(result, Exception):
            raise result
        return result


class _FakeGhConnector:
    def __init__(self, handle, auth_ok=True):
        self._handle = handle
        self._auth_ok = auth_ok
        self.watched = []

    def authenticate(self):
        return self._auth_ok

    def watch(self, repo, interval=30):
        self.watched.append(repo)
        return self._handle


def test_github_watch_loop_notifies_on_new_failure(monkeypatch):
    import prash.watcher as watcher_mod

    handle = _FakeGhHandle(script=[[_gh_event()], []])
    monkeypatch.setattr(watcher_mod, "GitHubConnector", lambda creds: _FakeGhConnector(handle))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    notified = []
    monkeypatch.setattr(watcher_mod, "_notify_github", lambda event, console=None, creds=None: notified.append(event))

    watcher_mod.run_github_watch_loop(["acme/api"], interval=0, max_iterations=2)

    assert len(notified) == 1  # failure fires once; next poll (unchanged) is silent
    assert notified[0]["event_type"] == "ci_failure"


def test_github_watch_loop_survives_poll_errors(monkeypatch):
    import prash.watcher as watcher_mod
    from prash.connectors.github import GitHubError

    handle = _FakeGhHandle(script=[GitHubError("GitHub API 429: rate limited"), [_gh_event()]])
    monkeypatch.setattr(watcher_mod, "GitHubConnector", lambda creds: _FakeGhConnector(handle))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    notified = []
    monkeypatch.setattr(watcher_mod, "_notify_github", lambda event, console=None, creds=None: notified.append(event))

    watcher_mod.run_github_watch_loop(["acme/api"], interval=0, max_iterations=2)
    assert len(notified) == 1  # cycle 1 skipped, cycle 2 delivered


def test_resolve_github_repos_splits_comma_list():
    from prash.watcher import resolve_github_repos
    assert resolve_github_repos("acme/api, acme/web") == ["acme/api", "acme/web"]


def test_resolve_github_repos_requires_targets(monkeypatch):
    import prash.watcher as watcher_mod
    from prash.watcher import resolve_github_repos

    monkeypatch.setattr(watcher_mod.os, "environ", {})
    import pytest
    with pytest.raises(ValueError):
        resolve_github_repos(None)


def test_resolve_github_repos_reads_env(monkeypatch):
    import prash.watcher as watcher_mod
    from prash.watcher import resolve_github_repos

    monkeypatch.setattr(watcher_mod.os, "environ", {"GITHUB_WATCH_REPOS": "acme/api"})
    assert resolve_github_repos(None) == ["acme/api"]


# ── G3: GitLab CI watch loop + project resolution ──

def _gl_event(event_type="ci_failure", project="acme/api"):
    import datetime as _dt
    return {
        "timestamp": _dt.datetime(2026, 9, 7, 12, 0, tzinfo=_dt.timezone.utc),
        "connector": "gitlab", "event_type": event_type,
        "summary": f"pipeline #7 {event_type} on main (abcd1234)",
        "raw": {"pipeline_id": 7, "project": project},
    }


class _FakeGlHandle:
    def __init__(self, script):
        self.script = iter(script)
        self.connector = "gitlab"
        self.target = "acme/api"

    def poll(self):
        result = next(self.script)
        if isinstance(result, Exception):
            raise result
        return result


class _FakeGlConnector:
    def __init__(self, handle, auth_ok=True):
        self._handle = handle
        self._auth_ok = auth_ok
        self.watched = []

    def authenticate(self):
        return self._auth_ok

    def watch(self, project, interval=30):
        self.watched.append(project)
        return self._handle


def test_gitlab_watch_loop_notifies_on_new_failure(monkeypatch):
    import prash.watcher as watcher_mod

    handle = _FakeGlHandle(script=[[_gl_event()], []])
    monkeypatch.setattr(watcher_mod, "GitLabConnector", lambda creds: _FakeGlConnector(handle))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    notified = []
    monkeypatch.setattr(watcher_mod, "_notify_gitlab", lambda event, console=None, creds=None: notified.append(event))

    watcher_mod.run_gitlab_watch_loop(["acme/api"], interval=0, max_iterations=2)
    assert len(notified) == 1 and notified[0]["event_type"] == "ci_failure"


def test_gitlab_watch_loop_survives_poll_errors(monkeypatch):
    import prash.watcher as watcher_mod
    from prash.connectors.gitlab import GitLabError

    handle = _FakeGlHandle(script=[GitLabError("GitLab API 429: rate limited"), [_gl_event()]])
    monkeypatch.setattr(watcher_mod, "GitLabConnector", lambda creds: _FakeGlConnector(handle))
    monkeypatch.setattr(watcher_mod, "time", MagicMock())
    notified = []
    monkeypatch.setattr(watcher_mod, "_notify_gitlab", lambda event, console=None, creds=None: notified.append(event))

    watcher_mod.run_gitlab_watch_loop(["acme/api"], interval=0, max_iterations=2)
    assert len(notified) == 1


def test_resolve_gitlab_projects_splits_comma_list():
    from prash.watcher import resolve_gitlab_projects
    assert resolve_gitlab_projects("acme/api, acme/web") == ["acme/api", "acme/web"]


def test_resolve_gitlab_projects_requires_targets(monkeypatch):
    import prash.watcher as watcher_mod
    from prash.watcher import resolve_gitlab_projects
    import pytest

    monkeypatch.setattr(watcher_mod.os, "environ", {})
    with pytest.raises(ValueError):
        resolve_gitlab_projects(None)


def test_resolve_gitlab_projects_reads_env(monkeypatch):
    import prash.watcher as watcher_mod
    from prash.watcher import resolve_gitlab_projects

    monkeypatch.setattr(watcher_mod.os, "environ", {"GITLAB_WATCH_PROJECTS": "acme/api"})
    assert resolve_gitlab_projects(None) == ["acme/api"]
