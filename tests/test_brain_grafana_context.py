"""format_grafana_context() and the Grafana-aware bypass of the CI-shaped
"no error signal" guard in diagnose_failure(). Mirrors
test_brain_pagerduty_context.py; see diagnosis_agent.py's GRAFANA / ALERT
RULES prompt section for the format this locks in.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import prash.brain.diagnosis_agent as da
from prash.brain.diagnosis_agent import (
    _is_grafana_context,
    format_grafana_context,
)


def _state(**overrides):
    base = {
        "resource": "High error rate",
        "state": SimpleNamespace(value="failed"),
        "detail": {
            "uid": "abc123", "title": "High error rate",
            "alert_state": "active", "active_alert_count": 1,
        },
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _event(event_type="alert_firing",
           summary="Alert rule 'High error rate' is firing"):
    return {
        "timestamp": datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
        "connector": "grafana",
        "event_type": event_type,
        "summary": summary,
        "raw": {"rule_uid": "abc123", "rule_title": "High error rate"},
    }


def test_format_includes_both_sections():
    out = format_grafana_context(_state(), [_event()])
    assert "=== ALERT RULE STATE ===" in out
    assert "=== GRAFANA EVENTS ===" in out


def test_format_includes_rule_fields():
    out = format_grafana_context(_state(), [])
    assert "rule: High error rate" in out
    assert "rule_uid: abc123" in out
    assert "overall_state: failed" in out
    assert "alert_state: active" in out
    assert "active_alert_count: 1" in out


def test_format_handles_empty_event_window_explicitly():
    """An empty lookback window is a real input (get_stats() is
    swallow-to-[] by contract) — the ALERT RULE STATE block still carries
    signal via the rule's firing state."""
    out = format_grafana_context(_state(), [])
    assert "(no events in the lookback window)" in out


def test_format_healthy_state_has_zero_alert_count():
    healthy = _state(state=SimpleNamespace(value="healthy"),
                     detail={"uid": "abc123", "title": "High error rate",
                             "alert_state": "none", "active_alert_count": 0})
    out = format_grafana_context(healthy, [])
    assert "alert_state: none" in out
    assert "active_alert_count: 0" in out


def test_format_renders_events():
    out = format_grafana_context(_state(), [
        _event(),
        _event(event_type="alert_recovered",
               summary="Alert rule 'High error rate' returned to normal (no longer listed by the Alertmanager)"),
    ])
    assert "- [2026-09-09T12:00:00+00:00] alert_firing: Alert rule 'High error rate' is firing" in out
    assert "alert_recovered: Alert rule 'High error rate' returned to normal" in out


def test_marker_recognized_and_guard_bypassed():
    """The guard must treat an alert-rule block as real signal even with an
    empty event window, and the four context markers must stay distinct."""
    context = format_grafana_context(_state(), [])
    assert _is_grafana_context(context)
    assert not _is_grafana_context("just some CI log output")
    assert not da._is_k8s_context(context)
    assert not da._is_datadog_context(context)
    assert not da._is_pagerduty_context(context)


def test_diagnose_failure_accepts_grafana_context_without_error_signal(monkeypatch):
    """End-to-end guard check: a grafana context block with zero CI-shaped
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
                logs=format_grafana_context(_state(), []),
                repo_full_name="grafana/High error rate",
                commit_message="(no commit)",
                workflow_name="grafana",
            )
        except _GuardPassed:
            pass  # reached the LLM call — the guard passed
        except DiagnosisValidationError as exc:
            if "no error output" in str(exc):
                raise AssertionError(f"no-signal guard rejected grafana context: {exc}")

    asyncio.run(run())
