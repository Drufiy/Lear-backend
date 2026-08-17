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
    async def fake_diagnose_k8s_pod(namespace, pod, **kwargs):
        # **kwargs absorbs repo/access_token/default_branch, added 2026-08-16
        # when the k8s path gained manifest-repo access (PRASH_V2.md §9).
        if diagnosis is None:
            raise fix_mod.FixTargetError(f"pod {namespace}/{pod} not found")
        return diagnosis

    async def fake_diagnose_ci_run(run_id, repo_full_name, access_token):
        return multi

    async def fake_diagnose_gitlab_ci_run(pipeline_id, project, access_token):
        return multi

    monkeypatch.setattr(fix_mod, "diagnose_k8s_pod", fake_diagnose_k8s_pod)
    monkeypatch.setattr(fix_mod, "diagnose_ci_run", fake_diagnose_ci_run)
    monkeypatch.setattr(fix_mod, "diagnose_gitlab_ci_run", fake_diagnose_gitlab_ci_run)


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


# ── the "ask, don't quit" options flow (PRASH_V2.md §9, 2026-08-15) ──────────

_OPTIONS_DIAGNOSIS = {
    "recommended_action": None,
    "options": [
        {"action": "restart_pod", "rationale": "pod may be wedged; a fresh pod likely clears it", "is_default": True},
        {"action": None, "rationale": "could be a deterministic config error; escalate to a human", "is_default": False},
    ],
}


def test_render_options_shows_ranked_menu(capsys):
    from rich.console import Console

    d = _diagnosis(**_OPTIONS_DIAGNOSIS)
    fix_mod.render_options(d, Console())
    out = capsys.readouterr().out
    assert "restart_pod" in out
    assert "escalate to a human" in out
    assert "default" in out


def test_cmd_fix_options_noninteractive_reports_and_takes_no_action(tmp_path, monkeypatch, capsys):
    _patch_store(monkeypatch)
    _patch_brain(monkeypatch, diagnosis=_diagnosis(**_OPTIONS_DIAGNOSIS))
    dispatches = []
    monkeypatch.setattr(cli_mod, "_build_dispatcher", lambda mode: dispatches.append(mode) or Dispatcher(mode=mode, breaker=None, audit=cli_mod.AuditLog(path=tmp_path / "audit.log")))

    rc = cli_mod.cmd_fix(_args(noninteractive=True))
    assert rc == 0
    assert dispatches == []
    assert "no automated action" in capsys.readouterr().out


def test_cmd_fix_options_picks_and_dispatches_selected_action(tmp_path, monkeypatch, capsys):
    _patch_store(monkeypatch)
    _patch_brain(monkeypatch, diagnosis=_diagnosis(**_OPTIONS_DIAGNOSIS))
    monkeypatch.setenv("PRASH_CIRCUIT_STATE_PATH", str(tmp_path / "circuit.json"))
    monkeypatch.setenv("PRASH_AUDIT_LOG_PATH", str(tmp_path / "audit.log"))
    monkeypatch.setattr("prash.actions.restart_pod.k8s_restart_pod", lambda ns, name: True)
    monkeypatch.setattr(
        "prash.actions.restart_pod.get_pod_status",
        lambda ns, name: [PodStatus(name=name, namespace=ns, phase="Running", problem=None, restart_count=1, ready=True)],
    )
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *a, **k: "1")

    rc = cli_mod.cmd_fix(_args(noninteractive=False, mode="bypass"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "restart issued" in out
    assert "verified" in out


def test_cmd_fix_options_escalate_choice_takes_no_action(tmp_path, monkeypatch, capsys):
    _patch_store(monkeypatch)
    _patch_brain(monkeypatch, diagnosis=_diagnosis(**_OPTIONS_DIAGNOSIS))
    dispatches = []
    monkeypatch.setattr(cli_mod, "_build_dispatcher", lambda mode: dispatches.append(mode) or Dispatcher(mode=mode, breaker=None, audit=cli_mod.AuditLog(path=tmp_path / "audit.log")))
    monkeypatch.setattr(cli_mod.Prompt, "ask", lambda *a, **k: "2")

    rc = cli_mod.cmd_fix(_args(noninteractive=False))
    assert rc == 0
    assert dispatches == []
    assert "escalating to a human" in capsys.readouterr().out


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


# ── GitLab CI (Sprint 2 Tier 2, PRASH_V2.md §7b) ────────────────────────────

def test_cmd_fix_ci_requires_gitlab_token(monkeypatch, capsys):
    _patch_store(monkeypatch)
    rc = cli_mod.cmd_fix(_args(target="acme/api", ci=True, run_id=123, provider="gitlab"))
    assert rc == 3
    assert "GITLAB_TOKEN" in capsys.readouterr().out


def test_cmd_fix_ci_gitlab_reports_partial_success(monkeypatch, capsys):
    """Same wiring as the GitHub --ci path, just routed through
    diagnose_gitlab_ci_run/apply-gitlab-ci-fix instead -- proves --provider
    gitlab actually reaches the GitLab-specific functions, not that the
    diagnosis rendering logic itself differs (it doesn't; it's shared)."""
    _patch_store(monkeypatch, creds={"GITLAB_TOKEN": "gl-token"})
    fixed = _diagnosis(files_changed=[FileChange(path="backend/app.py", new_content="x = 1", explanation="fix ruff")])
    _patch_brain(
        monkeypatch,
        multi=MultiFailureResult(
            diagnoses=[fixed, _diagnosis(problem_summary="Frontend bundle error persists", files_changed=[])],
            job_names=["backend", "frontend"],
        ),
    )
    rc = cli_mod.cmd_fix(_args(target="acme/api", ci=True, run_id=456, provider="gitlab"))
    out = capsys.readouterr().out
    assert "Diagnosed 1 of 2 independent failures with a proposed fix" in out
    assert rc == 1
    assert "needs_approval" in out


def test_cmd_fix_ci_gitlab_skips_dispatch_when_nothing_is_fixable(monkeypatch, capsys):
    _patch_store(monkeypatch, creds={"GITLAB_TOKEN": "gl-token"})
    _patch_brain(
        monkeypatch,
        multi=MultiFailureResult(
            diagnoses=[_diagnosis(problem_summary="Frontend bundle error persists", files_changed=[])],
            job_names=["frontend"],
        ),
    )
    rc = cli_mod.cmd_fix(_args(target="acme/api", ci=True, run_id=456, provider="gitlab"))
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


def test_diagnose_gitlab_ci_run_passes_logs_to_multi_diagnosis(monkeypatch):
    seen = {}

    async def fake_fetch_pipeline_logs(pipeline_id, project, token):
        return "=== backend (failed) ===\nFAILED"

    async def fake_diagnose_multi_failure(**kwargs):
        seen.update(kwargs)
        return MultiFailureResult(diagnoses=[], job_names=[])

    monkeypatch.setattr(fix_mod, "fetch_pipeline_logs", fake_fetch_pipeline_logs)
    monkeypatch.setattr(fix_mod, "diagnose_multi_failure", fake_diagnose_multi_failure)
    asyncio.run(fix_mod.diagnose_gitlab_ci_run(789, "acme/api", "gl-token"))
    assert seen["repo_full_name"] == "acme/api"
    assert "=== backend (failed) ===" in seen["logs"]
    assert seen["workflow_name"] == "gitlab pipeline 789"


# ── the manifest-fix path (PRASH_V2.md §9, 2026-08-16) ──────────────────────

_MANIFEST_FIX = {
    "recommended_action": None,
    "fix_type": "review_recommended",
    "files_changed": [
        FileChange(
            path="k8s/broken-app.yaml",
            new_content="apiVersion: apps/v1\nkind: Deployment\n# corrected\n",
            explanation="Mount the missing config.yaml the container requires at startup",
        )
    ],
}


def _patch_k8s_gather(monkeypatch, captured):
    """Mock only Track B's connector reads, so diagnose_k8s_pod's real body
    (including the investigation_context wiring) is what's under test."""
    pod = PodStatus(name="api-7f9d", namespace="production", phase="Running", problem="CrashLoopBackOff", restart_count=9, ready=False)
    monkeypatch.setattr(fix_mod, "get_pod_status", lambda ns, name: [pod])
    monkeypatch.setattr(fix_mod, "get_pod_logs", lambda ns, name: "config file missing")
    monkeypatch.setattr(fix_mod, "get_pod_events", lambda ns, name: [])

    async def fake_diagnose_failure(**kwargs):
        captured.update(kwargs)
        return _diagnosis()

    monkeypatch.setattr(fix_mod, "diagnose_failure", fake_diagnose_failure)


def test_diagnose_k8s_pod_without_repo_gets_no_investigation_tools(monkeypatch):
    """No manifest repo => no investigation_context => the brain physically
    cannot read a manifest, and per the prompt must fall back to
    recommended_action only. This is the pre-2026-08-16 behavior, preserved."""
    captured = {}
    _patch_k8s_gather(monkeypatch, captured)
    asyncio.run(fix_mod.diagnose_k8s_pod("production", "api-7f9d"))
    assert captured["investigation_context"] is None
    assert captured["repo_full_name"] == "production/api-7f9d"


def test_diagnose_k8s_pod_with_repo_wires_investigation_context(monkeypatch):
    """The root-cause fix (§9, 2026-08-16): with a manifest repo the brain gets
    fetch_file/list_directory/search_code pointed at it, and repo_full_name
    must name that repo -- otherwise the prompt would claim one identity while
    the investigation tools read from another."""
    captured = {}
    _patch_k8s_gather(monkeypatch, captured)
    asyncio.run(fix_mod.diagnose_k8s_pod("production", "api-7f9d", repo="acme/infra", access_token="gh-token"))
    ctx = captured["investigation_context"]
    assert ctx == {"repo_full_name": "acme/infra", "access_token": "gh-token", "default_branch": "main"}
    assert captured["repo_full_name"] == "acme/infra"


def test_diagnose_k8s_pod_repo_without_token_stays_unwired(monkeypatch):
    """A repo with no token can't call the GitHub API — must not half-wire."""
    captured = {}
    _patch_k8s_gather(monkeypatch, captured)
    asyncio.run(fix_mod.diagnose_k8s_pod("production", "api-7f9d", repo="acme/infra"))
    assert captured["investigation_context"] is None


def test_cmd_fix_manifest_changes_dispatch_apply_manifest_fix(tmp_path, monkeypatch, capsys):
    """The whole point of the 2026-08-16 work: a runtime diagnosis carrying a
    corrected manifest opens a real PR instead of dead-ending on 'a human must
    edit the Deployment'."""
    _patch_store(monkeypatch, creds={"GITHUB_TOKEN": "gh-token", "PRASH_MANIFEST_REPO": "acme/infra"})
    _patch_brain(monkeypatch, diagnosis=_diagnosis(**_MANIFEST_FIX))
    monkeypatch.setenv("PRASH_CIRCUIT_STATE_PATH", str(tmp_path / "circuit.json"))
    monkeypatch.setenv("PRASH_AUDIT_LOG_PATH", str(tmp_path / "audit.log"))

    seen = {}

    class FakeGitHub:
        def authenticate(self):
            return True

        def get_repo(self, repo):
            seen["repo"] = repo
            return {"default_branch": "main"}

        def get_branch_head_sha(self, repo, branch):
            return "base-sha"

        def get_commit_tree_sha(self, repo, sha):
            return "tree-sha"

        def create_blob(self, repo, content):
            seen["content"] = content
            return "blob-sha"

        def create_tree(self, repo, base, entries):
            seen["paths"] = [e["path"] for e in entries]
            return "new-tree"

        def create_commit(self, repo, message, tree, parent):
            return "commit-sha"

        def create_ref(self, repo, branch, sha):
            seen["branch"] = branch

        def create_pr(self, repo, title, head, base, body=""):
            seen["title"] = title
            return {"number": 7, "html_url": "https://github.com/acme/infra/pull/7", "state": "open"}

        def get_pr(self, repo, number):
            return {"number": number, "state": "open"}

    monkeypatch.setattr(cli_mod, "_make_connectors", lambda creds: {"github": FakeGitHub(), "k8s": None})

    rc = cli_mod.cmd_fix(_args(mode="bypass", noninteractive=True))
    assert rc == 0
    assert seen["repo"] == "acme/infra"          # the manifest repo, not the pod
    assert seen["paths"] == ["k8s/broken-app.yaml"]
    assert seen["branch"] == "prash/fix-production-api-7f9d"
    assert "Kubernetes manifest diagnosis" in seen["title"]
    assert "opened PR #7" in capsys.readouterr().out


def test_cmd_fix_manifest_changes_without_repo_reports_instead_of_dropping(monkeypatch, capsys):
    """Defensive: the prompt forbids files_changed with no repo, but if it ever
    happens the fix must be surfaced, never silently discarded."""
    _patch_store(monkeypatch)
    _patch_brain(monkeypatch, diagnosis=_diagnosis(**_MANIFEST_FIX))
    dispatches = []
    monkeypatch.setattr(cli_mod, "_build_dispatcher", lambda mode: dispatches.append(mode) or None)

    rc = cli_mod.cmd_fix(_args())
    assert rc == 0
    assert dispatches == []
    assert "no manifest repo is configured" in capsys.readouterr().out
