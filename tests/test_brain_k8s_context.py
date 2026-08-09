"""Track D days 6-8: format_k8s_context() and the k8s-aware bypass of the
CI-shaped "no error signal" guard in diagnose_failure(). See diagnosis_agent.py's
KUBERNETES / RUNTIME FAILURES prompt section for the format this locks in.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import prash.brain.diagnosis_agent as da
from prash.brain.diagnosis_agent import (
    _is_k8s_context,
    diagnose_failure,
    format_k8s_context,
)


def _pod(**overrides):
    base = {
        "name": "api-7f9d", "namespace": "production", "phase": "Running",
        "problem": "CrashLoopBackOff", "restart_count": 18, "ready": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_format_includes_all_three_sections():
    out = format_k8s_context(_pod(), "some log line", [])
    assert "=== POD STATUS ===" in out
    assert "=== POD LOGS ===" in out
    assert "=== POD EVENTS ===" in out


def test_format_includes_pod_fields():
    out = format_k8s_context(_pod(name="worker-1", namespace="staging", problem="OOMKilled", restart_count=7), "", [])
    assert "name: worker-1" in out
    assert "namespace: staging" in out
    assert "problem: OOMKilled" in out
    assert "restart_count: 7" in out
    assert "ready: false" in out


def test_format_handles_empty_logs_explicitly():
    """Empty pod logs are the common case (see kubernetes.py's get_pod_logs
    docstring) -- must render an explicit marker, not a blank/confusing gap."""
    out = format_k8s_context(_pod(), "", [])
    assert "(empty — no output before the container exited)" in out


def test_format_handles_no_events():
    out = format_k8s_context(_pod(), "logs here", [])
    assert "(no events)" in out


def test_format_renders_events_with_count_suffix():
    events = [{"type": "Warning", "reason": "BackOff", "message": "Back-off restarting failed container", "count": 15}]
    out = format_k8s_context(_pod(), "", events)
    assert "- Warning BackOff: Back-off restarting failed container (x15)" in out


def test_format_omits_count_suffix_when_count_is_one():
    events = [{"type": "Normal", "reason": "Pulled", "message": "Successfully pulled image", "count": 1}]
    out = format_k8s_context(_pod(), "", events)
    assert "(x1)" not in out
    assert "- Normal Pulled: Successfully pulled image" in out


def test_is_k8s_context_true_for_formatted_output():
    out = format_k8s_context(_pod(), "", [])
    assert _is_k8s_context(out) is True


def test_is_k8s_context_false_for_ci_logs():
    assert _is_k8s_context("=== build/1_Run tests.txt ===\nFAILED test_foo") is False


def test_is_k8s_context_false_for_empty_string():
    assert _is_k8s_context("") is False
    assert _is_k8s_context(None) is False


def test_diagnose_failure_does_not_raise_on_empty_pod_logs(monkeypatch):
    """The actual regression this guards against: a crash-looping pod with
    empty logs (the common case, per get_pod_logs' own docstring) has no
    _ERROR_RE match, so without the k8s bypass this would have raised
    DiagnosisValidationError before the model was ever called."""
    k8s_logs = format_k8s_context(_pod(), "", [])

    async def fake_call_with_tool(**kwargs):
        return {
            "problem_summary": "Pod crash-looping with no log signal",
            "root_cause": "No revealing traceback or event, consistent with a wedged process on startup.",
            "fix_description": "Restart may clear a transient state; investigate further if it recurs.",
            "fix_type": "manual_required",
            "confidence": 0.55,
            "is_flaky_test": False,
            "files_changed": [],
            "category": "runtime",
            "logs_truncated_warning": False,
            "recommended_action": "restart_pod",
        }

    monkeypatch.setattr(da, "call_with_tool", fake_call_with_tool)
    diagnosis = asyncio.run(diagnose_failure(
        logs=k8s_logs,
        repo_full_name="acme/worker",
        commit_message="(no commit)",
        workflow_name="kubernetes",
    ))
    assert diagnosis.category == "runtime"
    assert diagnosis.recommended_action == "restart_pod"
