"""format_pagerduty_context() and the PagerDuty-aware bypass of the CI-shaped
"no error signal" guard in diagnose_failure(). Mirrors
test_brain_datadog_context.py; see diagnosis_agent.py's PAGERDUTY / INCIDENT
PAGES prompt section for the format this locks in.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import prash.brain.diagnosis_agent as da
from prash.brain.diagnosis_agent import (
    _is_pagerduty_context,
    format_pagerduty_context,
)


def _state(**overrides):
    base = {
        "resource": "checkout",
        "state": SimpleNamespace(value="failed"),
        "detail": {
            "service_id": "PSVC1", "name": "checkout",
            "open_incidents": [{"id": "PINC1", "title": "500s spiking", "status": "triggered"}],
        },
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _event(event_type="incident_triggered",
           summary="Incident '500s spiking' on checkout triggered (critical severity, high urgency)"):
    return {
        "timestamp": datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc),
        "connector": "pagerduty",
        "event_type": event_type,
        "summary": summary,
        "raw": {"incident_id": "PINC1", "service_name": "checkout"},
    }


def test_format_includes_both_sections():
    out = format_pagerduty_context(_state(), [_event()])
    assert "=== INCIDENT STATE ===" in out
    assert "=== PAGERDUTY EVENTS ===" in out


def test_format_includes_service_fields():
    out = format_pagerduty_context(_state(), [])
    assert "service: checkout" in out
    assert "service_id: PSVC1" in out
    assert "overall_state: failed" in out
    assert "open_incidents: 1 (worst: triggered)" in out


def test_format_handles_empty_event_window_explicitly():
    """An empty lookback window is a real input (get_stats() is
    swallow-to-[] by contract) — the INCIDENT STATE block still carries
    signal via the open-incident state."""
    out = format_pagerduty_context(_state(), [])
    assert "(no events in the lookback window)" in out


def test_format_healthy_state_has_no_worst_suffix():
    healthy = _state(state=SimpleNamespace(value="healthy"),
                     detail={"service_id": "PSVC1", "name": "checkout", "open_incidents": []})
    out = format_pagerduty_context(healthy, [])
    assert "open_incidents: 0" in out
    assert "worst:" not in out


def test_format_renders_events():
    out = format_pagerduty_context(_state(), [
        _event(),
        _event(event_type="change_event", summary="Production deploy of checkout-service v3.1.0"),
    ])
    assert "- [2026-09-04T12:00:00+00:00] incident_triggered: Incident '500s spiking' on checkout triggered" in out
    assert "change_event: Production deploy of checkout-service v3.1.0" in out


def test_marker_recognized_and_guard_bypassed():
    """The guard must treat an incident block as real signal even with an
    empty event window, and the three context markers must stay distinct."""
    context = format_pagerduty_context(_state(), [])
    assert _is_pagerduty_context(context)
    assert not _is_pagerduty_context("just some CI log output")
    assert not da._is_k8s_context(context)
    assert not da._is_datadog_context(context)


def test_diagnose_failure_accepts_pagerduty_context_without_error_signal(monkeypatch):
    """End-to-end guard check: a pagerduty context block with zero CI-shaped
    error lines must pass the _ERROR_RE no-signal guard. Stub the LLM entry
    points — we only assert the guard didn't reject the input."""
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
                logs=format_pagerduty_context(_state(), []),
                repo_full_name="pagerduty/checkout",
                commit_message="(no commit)",
                workflow_name="pagerduty",
            )
        except _GuardPassed:
            pass  # reached the LLM call — the guard passed
        except DiagnosisValidationError as exc:
            if "no error output" in str(exc):
                raise AssertionError(f"no-signal guard rejected pagerduty context: {exc}")

    asyncio.run(run())
