"""Track A day 13 — the `prash fix` integration seam (prash/fix.py).

Ties Track B (kubernetes connector) + Track D (brain) into Track A's
dispatcher: diagnose -> render -> recommended_action -> permission pipeline.
See PRASH_V2.md §6 day 13 and §10.
"""
from __future__ import annotations

import asyncio
from argparse import Namespace

import prash.cli as cli_mod
import prash.fix as fix_mod
from prash.brain.multi_diagnosis import MultiFailureResult
from prash.brain.schemas import Diagnosis, FileChange
from prash.connectors.kubernetes import PodStatus
from prash.dispatch import Dispatcher


def _diagnosis(**over) -> Diagnosis:
    base = {
        "problem_summary": "Pod is crash-looping with repeated BackOff",
        "root_cause": "The container exits on startup with no output before crash.",
        "fix_description": "Restart the pod to clear the transient wedged state.",
        "fix_type": "manual_required",
        "confidence": 0.7,
        "is_flaky_test": False,
        "files_changed": [],
        "category": "runtime",
        "logs_truncated_warning": False,
        "recommended_action": "restart_pod",
    }
    base.update(over)
    return Diagnosis(**base)


def _args(**over) -> Namespace:
    base = {
        "target": "production/api-7f9d",
        "ci": False,
        "run_id": None,
        "env": None,
        "mode": None,
        "dry_run": False,
        "noninteractive": True,
        "grant": False,
        "secret_name": "",
        "secret_hint": "",
        "head": None,
        "base": None,
        "title": None,
        "body": None,
    }
    base.update(over)
    return Namespace(**base)


def _patch_store(monkeypatch, creds=None):
    """Stand-in for CredentialStore.from_env(), matching test_cli.py's pattern."""
    monkeypatch.setattr(
        cli_mod,
        "CredentialStore",
        type("FakeStore", (), {"from_env": staticmethod(lambda: type("S", (), {"load": lambda self: creds or {}, "secrets": lambda self: {}, "path": "fake"})())}),
    )


def _patch_brain(monkeypatch, diagnosis=None, multi=None):
    async def fake_diagnose_k8s_pod(namespace, pod):
        if diagnosis is None:
            raise fix_mod.FixTargetError(f"pod {namespace}/{pod} not found")
        return diagnosis

    async def fake_diagnose_ci_run(run_id, repo_full_name, access_token):
        return multi

    monkeypatch.setattr(fix_mod, "diagnose_k8s_pod", fake_diagnose_k8s_pod)
    monkeypatch.setattr(fix_mod, "diagnose_ci_run", fake_diagnose_ci_run)


# ── pure helpers ────────────────────────────────────────────────────────────

def test_split_k8s_target():
    assert fix_mod.split_k8s_target("production/api-7f9d") == ("production", "api-7f9d")


def test_split_k8s_target_rejects_bad_shapes():
    for bad in ("api-7f9d", "/api", "a/b/c", ""):
        try:
            fix_mod.split_k8s_target(bad)
        except fix_mod.FixTargetError:
            continue
        raise AssertionError(f"expected FixTargetError for {bad!r}")


def test_recommended_action_id_maps_only_auto_actions():
    assert fix_mod.recommended_action_id("restart_pod") == "restart-pod"
    assert fix_mod.recommended_action_id("rollback") is None
    assert fix_mod.recommended_action_id("scale") is None
    assert fix_mod.recommended_action_id(None) is None
    assert fix_mod.recommended_action_id("") is None


# ── diagnosis gather ────────────────────────────────────────────────────────

def test_diagnose_k8s_pod_feeds_brain_the_formatted_context(monkeypatch):
    pod = PodStatus(name="api-7f9d", namespace="production", phase="Running", problem="CrashLoopBackOff", restart_count=18, ready=False)
    monkeypatch.setattr(fix_mod, "get_pod_status", lambda ns, name: [pod])
    monkeypatch.setattr(fix_mod, "get_pod_logs", lambda ns, name: "boot error line")
    monkeypatch.setattr(fix_mod, "get_pod_events", lambda ns, name: [{"type": "Warning", "reason": "BackOff", "message": "back-off restarting", "count": 18}])

    seen = {}

    async def fake_diagnose_failure(**kwargs):
        seen.update(kwargs)
        return _diagnosis()

    monkeypatch.setattr(fix_mod, "diagnose_failure", fake_diagnose_failure)
    diagnosis = asyncio.run(fix_mod.diagnose_k8s_pod("production", "api-7f9d"))
    assert diagnosis.recommended_action == "restart_pod"
    assert seen["logs"].startswith("=== POD STATUS ===")
    assert "=== POD LOGS ===" in seen["logs"]
    assert "boot error line" in seen["logs"]
    assert "BackOff" in seen["logs"]


def test_diagnose_k8s_pod_not_found_raises(monkeypatch):
    monkeypatch.setattr(fix_mod, "get_pod_status", lambda ns, name: [])
    try:
        asyncio.run(fix_mod.diagnose_k8s_pod("production", "missing"))
    except fix_mod.FixTargetError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected FixTargetError")


# ── cmd_fix: k8s pod mode ───────────────────────────────────────────────────

def test_cmd_fix_k8s_runs_recommended_action_through_pipeline(tmp_path, monkeypatch, capsys):
    _patch_store(monkeypatch)
    _patch_brain(monkeypatch, diagnosis=_diagnosis())
    monkeypatch.setenv("PRASH_CIRCUIT_STATE_PATH", str(tmp_path / "circuit.json"))
    monkeypatch.setenv("PRASH_AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    monkeypatch.setattr("prash.actions.restart_pod.k8s_restart_pod", lambda ns, name: True)
    monkeypatch.setattr(
        "prash.actions.restart_pod.get_pod_status",
        lambda ns, name: [PodStatus(name=name, namespace=ns, phase="Running", problem=None, restart_count=1, ready=True)],
    )

    rc = cli_mod.cmd_fix(_args(mode="bypass"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "restart issued" in out
    assert "verified" in out


def test_cmd_fix_k8s_manual_required_dispatches_nothing(tmp_path, monkeypatch, capsys):
    _patch_store(monkeypatch)
    _patch_brain(monkeypatch, diagnosis=_diagnosis(recommended_action=None, fix_type="manual_required"))
    dispatches = []
    monkeypatch.setattr(cli_mod, "_build_dispatcher", lambda mode: dispatches.append(mode) or Dispatcher(mode=mode, breaker=None, audit=cli_mod.AuditLog(path=tmp_path / "audit.log")))

    rc = cli_mod.cmd_fix(_args())
    assert rc == 0
    assert dispatches == []
    assert "did not recommend an automated action" in capsys.readouterr().out


def test_cmd_fix_k8s_rollback_surfaces_escalation_not_guess(tmp_path, monkeypatch, capsys):
    _patch_store(monkeypatch)
    _patch_brain(monkeypatch, diagnosis=_diagnosis(recommended_action="rollback"))
    dispatches = []
    monkeypatch.setattr(cli_mod, "_build_dispatcher", lambda mode: dispatches.append(mode) or Dispatcher(mode=mode, breaker=None, audit=cli_mod.AuditLog(path=tmp_path / "audit.log")))

    rc = cli_mod.cmd_fix(_args())
    assert rc == 0
    assert dispatches == []
    assert "rollback" in capsys.readouterr().out


def test_cmd_fix_k8s_unknown_pod_returns_error(monkeypatch, capsys):
    _patch_store(monkeypatch)
    _patch_brain(monkeypatch, diagnosis=None)
    assert cli_mod.cmd_fix(_args()) == 2
    assert "not found" in capsys.readouterr().out


# ── cmd_fix: CI multi-failure mode ──────────────────────────────────────────

def test_cmd_fix_ci_requires_run_id(monkeypatch, capsys):
    _patch_store(monkeypatch)
    assert cli_mod.cmd_fix(_args(ci=True, run_id=None)) == 2
    assert "--run-id" in capsys.readouterr().out


def test_cmd_fix_ci_requires_github_token(monkeypatch, capsys):
    _patch_store(monkeypatch)
    assert cli_mod.cmd_fix(_args(target="acme/api", ci=True, run_id=123)) == 3


def test_cmd_fix_ci_reports_partial_success(monkeypatch, capsys):
    """Diagnosis renders and reports honestly regardless of what happens
    next. noninteractive=True (the _args() default) means the apply-ci-fix
    dispatch that follows can't get an approval, so it reports
    needs_approval rather than silently proceeding or crashing -- this test
    is about the diagnosis summary wording, dispatch behavior is covered
    separately below and in test_actions.py."""
    _patch_store(monkeypatch, creds={"GITHUB_TOKEN": "gh-token"})
    fixed = _diagnosis(files_changed=[FileChange(path="backend/app.py", new_content="x = 1", explanation="fix ruff")])
    _patch_brain(
        monkeypatch,
        multi=MultiFailureResult(
            diagnoses=[fixed, _diagnosis(problem_summary="Frontend bundle error persists", files_changed=[])],
            job_names=["backend", "frontend"],
        ),
    )
    rc = cli_mod.cmd_fix(_args(target="acme/api", ci=True, run_id=456))
    out = capsys.readouterr().out
    assert "Diagnosed 1 of 2 independent failures with a proposed fix" in out
    assert "still broken" in out
    assert rc == 1
    assert "needs_approval" in out


def test_cmd_fix_ci_skips_dispatch_when_nothing_is_fixable(monkeypatch, capsys):
    _patch_store(monkeypatch, creds={"GITHUB_TOKEN": "gh-token"})
    _patch_brain(
        monkeypatch,
        multi=MultiFailureResult(
            diagnoses=[_diagnosis(problem_summary="Frontend bundle error persists", files_changed=[])],
            job_names=["frontend"],
        ),
    )
    rc = cli_mod.cmd_fix(_args(target="acme/api", ci=True, run_id=456))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Diagnosed 0 of 1 independent failures" in out


# ── diagnose_ci_run ─────────────────────────────────────────────────────────

def test_diagnose_ci_run_passes_logs_to_multi_diagnosis(monkeypatch):
    seen = {}

    async def fake_fetch_workflow_logs(run_id, repo, token):
        return "=== backend/1_Run tests.txt ===\nFAILED"

    async def fake_diagnose_multi_failure(**kwargs):
        seen.update(kwargs)
        return MultiFailureResult(diagnoses=[], job_names=[])

    monkeypatch.setattr(fix_mod, "fetch_workflow_logs", fake_fetch_workflow_logs)
    monkeypatch.setattr(fix_mod, "diagnose_multi_failure", fake_diagnose_multi_failure)
    asyncio.run(fix_mod.diagnose_ci_run(456, "acme/api", "gh-token"))
    assert seen["repo_full_name"] == "acme/api"
    assert "=== backend/1_Run tests.txt ===" in seen["logs"]
    assert seen["workflow_name"] == "github run 456"
