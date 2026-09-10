"""format_datadog_context() and the datadog-aware bypass of the CI-shaped
"no error signal" guard in diagnose_failure(). Mirrors test_brain_k8s_context.py;
see diagnosis_agent.py's DATADOG / MONITOR ALERTS prompt section for the
format this locks in.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import prash.brain.diagnosis_agent as da
from prash.brain.diagnosis_agent import (
    _is_datadog_context,
    format_datadog_context,
)


def _state(**overrides):
    base = {
        "resource": "cpu-high",
        "state": SimpleNamespace(value="failed"),
        "detail": {"monitor_id": 1234567, "name": "cpu-high", "overall_state": "Alert"},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _event(event_type="monitor_alert", summary="Monitor 'cpu-high' entered Alert state", raw=None):
    return {
        "timestamp": datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
        "connector": "datadog",
        "event_type": event_type,
        "summary": summary,
        "raw": raw if raw is not None else {"monitor_id": 1234567},
    }


def test_format_includes_both_sections():
    out = format_datadog_context(_state(), [_event()])
    assert "=== MONITOR STATE ===" in out
    assert "=== DATADOG EVENTS ===" in out


def test_format_includes_monitor_fields():
    out = format_datadog_context(_state(), [])
    assert "monitor: cpu-high" in out
    assert "monitor_id: 1234567" in out
    assert "overall_state: Alert" in out
    assert "connector_state: failed" in out


def test_format_handles_empty_event_window_explicitly():
    """An empty lookback window is a real input (get_stats() is
    swallow-to-[] by contract) — must render an explicit marker, not a
    blank/confusing gap, and the MONITOR STATE block still carries signal."""
    out = format_datadog_context(_state(), [])
    assert "(no events in the lookback window)" in out


def test_format_renders_events_with_metric_context():
    metric_event = _event(raw={"metric": {"query": "avg:system.cpu.user{*}", "max": 96.4, "mean": 88.1, "peak_at": "2026-09-04T11:59:00+00:00"}})
    out = format_datadog_context(_state(), [metric_event])
    assert "- [2026-09-04T12:00:00+00:00] monitor_alert: Monitor 'cpu-high' entered Alert state" in out
    assert "query=avg:system.cpu.user{*} max=96.4 mean=88.1" in out


def test_marker_recognized_and_guard_bypassed():
    """The guard must treat a monitor block as real signal even with an
    empty event window — mirror of the k8s empty-pod-logs bypass."""
    context = format_datadog_context(_state(), [])
    assert _is_datadog_context(context)
    assert not _is_datadog_context("just some CI log output")
    assert not da._is_k8s_context(context)  # markers must stay distinct


def test_diagnose_failure_accepts_datadog_context_without_error_signal(monkeypatch):
    """End-to-end guard check: a datadog context block with zero CI-shaped
    error lines must pass the _ERROR_RE no-signal guard (the only path into
    diagnose_failure before this change). Stub the LLM entry points — we only
    assert the guard didn't reject the input; whatever fires after it is fine."""
    import asyncio

    from prash.brain.diagnosis_agent import DiagnosisValidationError

    class _GuardPassed(Exception):
        pass

    async def fake_llm(*args, **kwargs):
        raise _GuardPassed()

    monkeypatch.setattr(da, "call_with_investigation", fake_llm)
    monkeypatch.setattr(da, "call_with_tool", fake_llm)

    async def run():
        try:
            await da.diagnose_failure(
                logs=format_datadog_context(_state(), []),
                repo_full_name="datadog/cpu-high",
                commit_message="(no commit)",
                workflow_name="datadog",
            )
        except _GuardPassed:
            pass  # reached the LLM call — the guard passed
        except DiagnosisValidationError as exc:
            # The no-signal guard's message is specific; any other validation
            # error (e.g. missing KIMI_API_KEY) means we got past the guard.
            if "no error output" in str(exc):
                raise AssertionError(f"no-signal guard rejected datadog context: {exc}")

    asyncio.run(run())
