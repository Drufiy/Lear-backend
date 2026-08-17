from prash.actions.apply_ci_fix import ApplyCiFixAction
from prash.actions.contract import ActionContext, ActionResultStatus, Decision, Target
from prash.actions.missing_secret import RequestSecretAction
from prash.actions.open_pr import OpenPrAction
from prash.actions.restart_pod import RestartPodAction
from prash.actions.rollback import RollbackAction
from prash.actions.scale import ScaleAction
from prash.brain.schemas import FileChange, FileEdit
from prash.circuit_breaker import CircuitBreaker
from prash.credentials import CredentialStore
from prash.dispatch import AskFn, Dispatcher, ExecutionOutcome
from prash.permissions import PermissionMode


class FakeAsk(AskFn):
    def __init__(self, answer: bool):
        self.answer = answer
        self.called = False

    def ask(self, action, plan, ctx):
        self.called = True
        return self.answer


class FakeGitHub:
    def __init__(self, creds=None):
        self.pulls = {}
        self.refs = {}
        self.default_branch = "main"
        self.raise_ref_exists = False
        self.files = {}  # path -> current content, for get_file_content
        self.blobs = {}  # blob sha -> content actually written, for assertions

    def get_file_content(self, repo, path, ref):
        if path not in self.files:
            raise KeyError(f"{path} not found in fake repo at {ref}")
        return self.files[path]

    def authenticate(self):
        return True

    def create_pr(self, repo, title, head, base, body=""):
        number = len(self.pulls) + 1
        self.pulls[number] = {"number": number, "html_url": f"https://github.com/{repo}/pull/{number}", "state": "open"}
        return self.pulls[number]

    def get_pr(self, repo, number):
        return self.pulls.get(number, {})

    def get_repo(self, repo):
        return {"default_branch": self.default_branch}

    def get_branch_head_sha(self, repo, branch):
        return "base-sha"

    def get_commit_tree_sha(self, repo, commit_sha):
        return "base-tree-sha"

    def create_blob(self, repo, content):
        sha = f"blob-sha-{abs(hash(content))}"
        self.blobs[sha] = content
        return sha

    def create_tree(self, repo, base_tree_sha, entries):
        return "new-tree-sha"

    def create_commit(self, repo, message, tree_sha, parent_sha):
        return "new-commit-sha"

    def create_ref(self, repo, branch, commit_sha):
        if self.raise_ref_exists:
            raise RuntimeError(f"GitHub API 422: Reference already exists for {branch}")
        self.refs[branch] = commit_sha


def _store(tmp_path):
    return CredentialStore(path=tmp_path / "creds.env")


def _ctx(tmp_path, extra=None, secrets=None, resource="acme/widget", env="staging"):
    return ActionContext(
        target=Target(resource=resource, environment=env),
        credentials={},
        secrets=secrets or {},
        dry_run=False,
        grant=False,
        extra={
            "store": _store(tmp_path),
            "connectors": {"github": FakeGitHub(), "k8s": None},
            **({"secret_name": "DEPLOY_KEY"} if extra is None else extra),
        },
    )


def test_request_secret_succeeds_from_supplied_secret(tmp_path):
    ctx = _ctx(tmp_path, secrets={"DEPLOY_KEY": "s3cr3t"})
    action = RequestSecretAction()
    result = action.execute(ctx)
    assert result.status is ActionResultStatus.SUCCEEDED
    assert _store(tmp_path).secrets()["DEPLOY_KEY"] == "s3cr3t"
    assert action.verify(ctx, result).ok


def test_request_secret_needs_input_when_no_value_and_noninteractive(tmp_path):
    ctx = _ctx(tmp_path, extra={"secret_name": "DEPLOY_KEY", "secret_input": None})
    result = RequestSecretAction().execute(ctx)
    assert result.status is ActionResultStatus.NEEDS_INPUT


def test_request_secret_uses_interactive_input(tmp_path):
    ctx = _ctx(tmp_path, extra={"secret_name": "DEPLOY_KEY", "secret_input": lambda n, h: "typed-value"})
    result = RequestSecretAction().execute(ctx)
    assert result.status is ActionResultStatus.SUCCEEDED
    assert _store(tmp_path).secrets()["DEPLOY_KEY"] == "typed-value"


def test_request_secret_dry_run_stores_nothing(tmp_path):
    ctx = ActionContext(
        target=Target(resource="job-123", environment="staging"),
        credentials={},
        secrets={"DEPLOY_KEY": "s3cr3t"},
        dry_run=True,
        extra={"secret_name": "DEPLOY_KEY", "store": _store(tmp_path)},
    )
    dispatcher = Dispatcher(mode=PermissionMode.ASK)
    dispatcher.register_all([RequestSecretAction()])
    result = dispatcher.run("request-secret", ctx)
    assert result.plan is not None and len(result.plan.steps) == 3
    assert _store(tmp_path).secrets() == {}


def test_dry_run_under_read_only_mode_refuses_instead_of_showing_a_plan(tmp_path):
    """Real bug, caught live (2026-08-14): --dry-run always reported
    SUCCEEDED with a plan regardless of the permission decision, so
    `--mode read-only --dry-run` printed "refuse / succeeded" -- the
    decision label said refused, the status said it worked. execute() was
    never called either way (so --dry-run's own "never touches real
    infrastructure" contract always held), but read-only's whole point is
    "refused outright" and that must be true under --dry-run too."""
    ctx = _ctx(tmp_path, extra={"connectors": {"github": FakeGitHub()}}, resource="acme/widget")
    ctx.dry_run = True
    dispatcher = Dispatcher(mode=PermissionMode.READ_ONLY)
    dispatcher.register_all([OpenPrAction()])
    result = dispatcher.run("open-pr", ctx)
    assert result.outcome is ExecutionOutcome.REFUSED
    assert result.result.status is ActionResultStatus.SKIPPED
    assert "refused by permission engine" in result.result.summary


def test_dry_run_under_ask_mode_still_shows_a_plan(tmp_path):
    """The common case must keep working: previewing what WOULD happen
    before a real approval prompt is the entire point of --dry-run under
    the default ask mode. Only an actual REFUSE decision should block the
    plan, not a PROMPT decision."""
    ctx = _ctx(tmp_path, extra={"connectors": {"github": FakeGitHub()}}, resource="acme/widget")
    ctx.dry_run = True
    dispatcher = Dispatcher(mode=PermissionMode.ASK)
    dispatcher.register_all([OpenPrAction()])
    result = dispatcher.run("open-pr", ctx)
    assert result.outcome is ExecutionOutcome.EXECUTED
    assert result.result.status is ActionResultStatus.SUCCEEDED
    assert "dry-run plan prepared" in result.result.summary


def test_open_pr_runs_end_to_end_with_prompt(tmp_path):
    ctx = _ctx(tmp_path, extra={"connectors": {"github": FakeGitHub()}}, resource="acme/widget")
    dispatcher = Dispatcher(mode=PermissionMode.ASK)
    dispatcher.register_all([OpenPrAction()])
    ask = FakeAsk(answer=True)
    result = dispatcher.run("open-pr", ctx, ask=ask)
    assert ask.called is True
    assert result.ok
    assert result.result.verification.ok
    assert result.result.detail["pr_number"] == 1


def test_open_pr_skipped_when_user_declines(tmp_path):
    ctx = _ctx(tmp_path, extra={"connectors": {"github": FakeGitHub()}}, resource="acme/widget")
    dispatcher = Dispatcher(mode=PermissionMode.ASK)
    dispatcher.register_all([OpenPrAction()])
    result = dispatcher.run("open-pr", ctx, ask=FakeAsk(answer=False))
    assert result.outcome.value == "skipped"
    assert result.result.status is ActionResultStatus.SKIPPED


def test_apply_ci_fix_runs_end_to_end_with_prompt(tmp_path):
    changes = [FileChange(path="backend/app.py", new_content="x = 1\n", explanation="fix ruff violation")]
    ctx = _ctx(
        tmp_path,
        extra={"connectors": {"github": FakeGitHub()}, "file_changes": changes, "run_id": 456},
        resource="acme/widget",
    )
    dispatcher = Dispatcher(mode=PermissionMode.ASK)
    dispatcher.register_all([ApplyCiFixAction()])
    ask = FakeAsk(answer=True)
    result = dispatcher.run("apply-ci-fix", ctx, ask=ask)
    assert ask.called is True
    assert result.ok
    assert result.result.verification.ok
    assert result.result.detail["pr_number"] == 1
    assert result.result.detail["branch"] == "prash/fix-run-456"


def test_apply_ci_fix_skipped_when_user_declines(tmp_path):
    changes = [FileChange(path="backend/app.py", new_content="x = 1\n", explanation="fix ruff violation")]
    ctx = _ctx(
        tmp_path,
        extra={"connectors": {"github": FakeGitHub()}, "file_changes": changes, "run_id": 456},
        resource="acme/widget",
    )
    dispatcher = Dispatcher(mode=PermissionMode.ASK)
    dispatcher.register_all([ApplyCiFixAction()])
    result = dispatcher.run("apply-ci-fix", ctx, ask=FakeAsk(answer=False))
    assert result.outcome.value == "skipped"
    assert result.result.status is ActionResultStatus.SKIPPED


def test_apply_ci_fix_fails_cleanly_with_no_file_changes(tmp_path):
    """Defense in depth: if the action is ever dispatched with an empty
    file_changes list (a caller bug upstream), it must fail honestly rather
    than open an empty PR or crash."""
    ctx = _ctx(
        tmp_path,
        extra={"connectors": {"github": FakeGitHub()}, "file_changes": [], "run_id": 456},
        resource="acme/widget",
    )
    action = ApplyCiFixAction()
    result = action.execute(ctx)
    assert result.status is ActionResultStatus.FAILED
    assert "no file changes" in result.summary


def test_apply_ci_fix_fails_cleanly_when_branch_already_exists(tmp_path):
    """Real risk this guards against: re-running `prash fix --ci --run-id
    N` for a run already fixed once must report clearly, not crash with a
    raw GitHub API exception."""
    changes = [FileChange(path="backend/app.py", new_content="x = 1\n", explanation="fix ruff violation")]
    github = FakeGitHub()
    github.raise_ref_exists = True
    ctx = _ctx(
        tmp_path,
        extra={"connectors": {"github": github}, "file_changes": changes, "run_id": 456},
        resource="acme/widget",
    )
    action = ApplyCiFixAction()
    result = action.execute(ctx)
    assert result.status is ActionResultStatus.FAILED
    assert "already proposed" in result.summary


def test_apply_ci_fix_applies_edits_against_the_real_fetched_file(tmp_path):
    """The mechanism that replaced whole-file regeneration (PRASH_V2.md §9,
    2026-08-17): a FileChange with `edits` must fetch the file's actual
    current content and patch only the matched span, leaving everything
    else in the file byte-for-byte untouched -- the property whole-file
    regeneration could never guarantee."""
    github = FakeGitHub()
    github.files["k8s/app.yaml"] = "spec:\n  replicas: 1\n  # a comment nothing should touch\n  image: myapp:v1\n"
    changes = [FileChange(
        path="k8s/app.yaml",
        edits=[FileEdit(old_content="image: myapp:v1", new_content="image: myapp:v2")],
        explanation="bump image tag",
    )]
    ctx = _ctx(
        tmp_path,
        extra={"connectors": {"github": github}, "file_changes": changes, "run_id": 1},
        resource="acme/widget",
    )
    action = ApplyCiFixAction()
    result = action.execute(ctx)
    assert result.status is ActionResultStatus.SUCCEEDED
    written = next(iter(github.blobs.values()))
    assert written == "spec:\n  replicas: 1\n  # a comment nothing should touch\n  image: myapp:v2\n"


def test_apply_ci_fix_fails_honestly_when_edit_does_not_match(tmp_path):
    """old_content that doesn't appear in the real file (a paraphrase, a
    stale read, a hallucination) must fail loudly and specifically -- never
    silently apply nothing, and never fall back to some other behavior."""
    github = FakeGitHub()
    github.files["k8s/app.yaml"] = "image: myapp:v1\n"
    changes = [FileChange(
        path="k8s/app.yaml",
        edits=[FileEdit(old_content="image: myapp:v9-does-not-exist", new_content="image: myapp:v2")],
        explanation="bump image tag",
    )]
    ctx = _ctx(
        tmp_path,
        extra={"connectors": {"github": github}, "file_changes": changes, "run_id": 1},
        resource="acme/widget",
    )
    action = ApplyCiFixAction()
    result = action.execute(ctx)
    assert result.status is ActionResultStatus.FAILED
    assert "did not apply" in result.summary


def test_apply_ci_fix_fails_honestly_when_edit_matches_more_than_once(tmp_path):
    """A non-unique old_content must be rejected rather than guessing which
    occurrence to patch -- the same contract Prash's own Edit tool uses."""
    github = FakeGitHub()
    github.files["config.py"] = "PORT = 8080\nOTHER = 1\nPORT = 8080\n"
    changes = [FileChange(
        path="config.py",
        edits=[FileEdit(old_content="PORT = 8080", new_content="PORT = 9090")],
        explanation="bump port",
    )]
    ctx = _ctx(
        tmp_path,
        extra={"connectors": {"github": github}, "file_changes": changes, "run_id": 1},
        resource="acme/widget",
    )
    action = ApplyCiFixAction()
    result = action.execute(ctx)
    assert result.status is ActionResultStatus.FAILED
    assert "matches 2 times" in result.summary


def test_restart_pod_reports_failure_honestly_when_pod_missing(tmp_path, monkeypatch):
    """Track B's connector is real now (2026-08-09) -- was previously a
    stub raising NotImplementedError, which this test used to assert on
    ("not implemented yet"). Updated to mock the real connector function
    instead of hitting whatever k8s cluster happens to be configured on
    whoever runs the suite (that was a real latent bug: it only ever
    'passed' by accident on a machine with a matching cluster). See
    PRASH_V2.md §10, 2026-08-09.
    """
    monkeypatch.setattr("prash.actions.restart_pod.k8s_restart_pod", lambda ns, name: False)
    ctx = _ctx(tmp_path, resource="default/api")
    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([RestartPodAction()])
    result = dispatcher.run("restart-pod", ctx)
    assert result.outcome.value == "executed"
    assert result.result.status is ActionResultStatus.FAILED
    assert "did not succeed" in result.result.summary


def test_restart_pod_verify_consumes_track_b_pod_status_schema(tmp_path, monkeypatch):
    """Cross-track seam test: Track C's verify() must read Track B's real
    PodStatus fields (phase / ready / problem). Uses the actual dataclass so
    this breaks loudly the day Aradhya renames a field.
    """
    from prash.connectors.kubernetes import PodStatus

    def healthy(ns, name):
        return [PodStatus(name=name, namespace=ns, phase="Running", problem=None, restart_count=1, ready=True)]

    def still_crash_looping(ns, name):
        return [PodStatus(name=name, namespace=ns, phase="Running", problem="CrashLoopBackOff", restart_count=9, ready=False)]

    monkeypatch.setattr("prash.actions.restart_pod.k8s_restart_pod", lambda ns, name: True)
    ctx = _ctx(tmp_path, resource="default/api")

    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([RestartPodAction()])
    monkeypatch.setattr("prash.actions.restart_pod.get_pod_status", healthy)
    result = dispatcher.run("restart-pod", ctx)
    assert result.ok and result.result.verification.ok

    monkeypatch.setattr("prash.actions.restart_pod.get_pod_status", still_crash_looping)
    result = dispatcher.run("restart-pod", ctx)
    assert result.ok and not result.result.verification.ok
    assert "CrashLoopBackOff" in result.result.verification.detail



def test_rollback_approval_prompts_even_in_bypass(tmp_path):
    ctx = _ctx(tmp_path, resource="acme/api", env="production")
    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([RollbackAction()])
    result = dispatcher.run("rollback", ctx, ask=FakeAsk(answer=False))
    assert result.decision is Decision.PROMPT
    assert result.result.status is ActionResultStatus.SKIPPED


def test_rollback_with_grant_fails_honestly_when_no_prior_revision(tmp_path, monkeypatch):
    """Same update as test_restart_pod_reports_failure_honestly_when_pod_missing
    above -- Track B's get_previous_revision() is real now, this asserted
    on the old stub's "not implemented yet" text. Mocked instead of
    hitting a real cluster. See PRASH_V2.md §10, 2026-08-09.
    """
    monkeypatch.setattr("prash.actions.rollback.get_previous_revision", lambda ns, deployment: None)
    ctx = _ctx(tmp_path, resource="acme/api", env="staging")
    ctx.grant = True
    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([RollbackAction()])
    result = dispatcher.run("rollback", ctx, ask=FakeAsk(answer=False))
    assert result.decision is Decision.ALLOW
    assert result.result.status is ActionResultStatus.FAILED
    assert "no prior revision recorded" in result.result.summary


def test_scale_approval_prompts_even_in_bypass(tmp_path):
    """Same contract as rollback -- RiskTier's own docstring names scale as
    an APPROVAL-tier example alongside rollback, for the same reason: it can
    take a service down (replicas=0) as surely as a bad rollback."""
    ctx = _ctx(tmp_path, resource="default/api", extra={"replicas": 3})
    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([ScaleAction()])
    result = dispatcher.run("scale", ctx, ask=FakeAsk(answer=False))
    assert result.decision is Decision.PROMPT
    assert result.result.status is ActionResultStatus.SKIPPED


def test_scale_fails_honestly_when_replicas_not_specified(tmp_path):
    ctx = _ctx(tmp_path, resource="default/api", extra={})
    ctx.grant = True
    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([ScaleAction()])
    result = dispatcher.run("scale", ctx, ask=FakeAsk(answer=False))
    assert result.result.status is ActionResultStatus.FAILED
    assert "not specified" in result.result.summary


def test_scale_fails_honestly_when_deployment_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("prash.actions.scale.scale_deployment", lambda ns, name, replicas: False)
    ctx = _ctx(tmp_path, resource="default/api", extra={"replicas": 3})
    ctx.grant = True
    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([ScaleAction()])
    result = dispatcher.run("scale", ctx, ask=FakeAsk(answer=False))
    assert result.result.status is ActionResultStatus.FAILED
    assert "not found" in result.result.summary


def test_scale_succeeds_and_verify_confirms_replica_count(tmp_path, monkeypatch):
    monkeypatch.setattr("prash.actions.scale.scale_deployment", lambda ns, name, replicas: True)
    ctx = _ctx(tmp_path, resource="default/api", extra={"replicas": 3})
    ctx.grant = True
    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([ScaleAction()])

    monkeypatch.setattr("prash.actions.scale.get_deployment_replicas", lambda ns, name: 3)
    result = dispatcher.run("scale", ctx, ask=FakeAsk(answer=False))
    assert result.ok
    assert "scaled to 3 replicas" in result.result.summary
    assert result.result.verification.ok

    monkeypatch.setattr("prash.actions.scale.get_deployment_replicas", lambda ns, name: 1)
    result = dispatcher.run("scale", ctx, ask=FakeAsk(answer=False))
    assert result.ok
    assert not result.result.verification.ok
    assert "replicas=1 (target=3)" in result.result.verification.detail


def test_audit_recorded_for_refused_read_only(tmp_path):
    ctx = _ctx(tmp_path, resource="acme/api")
    dispatcher = Dispatcher(mode=PermissionMode.READ_ONLY)
    dispatcher.register_all([OpenPrAction()])
    result = dispatcher.run("open-pr", ctx)
    assert result.outcome.value == "refused"
    assert dispatcher.audit.read()[-1]["decision"] == "refuse"


def _secret_dispatcher(tmp_path, breaker=None):
    dispatcher = Dispatcher(mode=PermissionMode.AUTO_SAFE, breaker=breaker)
    dispatcher.register_all([RequestSecretAction()])
    return dispatcher


def test_breaker_opens_after_cap_and_blocks_execution(tmp_path):
    breaker = CircuitBreaker(max_actions=2, window_seconds=60, path=tmp_path / "circuit.json")
    dispatcher = _secret_dispatcher(tmp_path, breaker)
    ctx = _ctx(tmp_path, resource="acme/api", secrets={"DEPLOY_KEY": "s3cr3t"})
    assert dispatcher.run("request-secret", ctx).outcome is ExecutionOutcome.EXECUTED
    assert dispatcher.run("request-secret", ctx).outcome is ExecutionOutcome.EXECUTED
    blocked = dispatcher.run("request-secret", ctx)
    assert blocked.outcome is ExecutionOutcome.CIRCUIT_OPEN
    assert blocked.result.status is ActionResultStatus.SKIPPED
    assert "circuit open" in blocked.result.summary
    assert dispatcher.audit.read()[-1]["extra"].get("reason") == "circuit_open"


def test_breaker_does_not_block_other_resources(tmp_path):
    breaker = CircuitBreaker(max_actions=1, window_seconds=60, path=tmp_path / "circuit.json")
    dispatcher = _secret_dispatcher(tmp_path, breaker)
    dispatcher.run("request-secret", _ctx(tmp_path, resource="acme/api", secrets={"DEPLOY_KEY": "x"}))
    other = dispatcher.run("request-secret", _ctx(tmp_path, resource="other/svc", secrets={"DEPLOY_KEY": "x"}))
    assert other.outcome is ExecutionOutcome.EXECUTED


def test_dry_run_does_not_count_toward_breaker(tmp_path):
    breaker = CircuitBreaker(max_actions=2, window_seconds=60, path=tmp_path / "circuit.json")
    dispatcher = _secret_dispatcher(tmp_path, breaker)
    ctx = _ctx(tmp_path, resource="acme/api", secrets={"DEPLOY_KEY": "s3cr3t"})
    ctx.dry_run = True
    for _ in range(5):
        dispatcher.run("request-secret", ctx)
    assert breaker.is_open("acme/api") is False


def test_breaker_reset_allows_execution_again(tmp_path):
    breaker = CircuitBreaker(max_actions=1, window_seconds=60, path=tmp_path / "circuit.json")
    dispatcher = _secret_dispatcher(tmp_path, breaker)
    ctx = _ctx(tmp_path, resource="acme/api", secrets={"DEPLOY_KEY": "s3cr3t"})
    dispatcher.run("request-secret", ctx)
    assert dispatcher.run("request-secret", ctx).outcome is ExecutionOutcome.CIRCUIT_OPEN
    breaker.reset("acme/api")
    assert dispatcher.run("request-secret", ctx).outcome is ExecutionOutcome.EXECUTED


class FakeRunner:
    def __init__(self, run_id=99, fail=False):
        self.run_id = run_id
        self.fail = fail
        self.calls = []

    def re_run(self, resource):
        self.calls.append(resource)
        if self.fail:
            raise RuntimeError("api refused")
        return self.run_id


def test_request_secret_triggers_job_rerun(tmp_path):
    ctx = _ctx(tmp_path, resource="acme/widget", secrets={"DEPLOY_KEY": "s3cr3t"})
    runner = FakeRunner()
    ctx.extra["runner"] = runner
    dispatcher = _secret_dispatcher(tmp_path)
    result = dispatcher.run("request-secret", ctx)
    assert result.ok
    assert runner.calls == ["acme/widget"]
    assert "triggered" in result.result.summary


def test_request_secret_reports_rerun_failure_but_keeps_secret(tmp_path):
    ctx = _ctx(tmp_path, resource="acme/widget", secrets={"DEPLOY_KEY": "s3cr3t"})
    ctx.extra["runner"] = FakeRunner(fail=True)
    dispatcher = _secret_dispatcher(tmp_path)
    result = dispatcher.run("request-secret", ctx)
    assert result.result.status is ActionResultStatus.FAILED
    assert "stored locally" in result.result.summary
    assert _store(tmp_path).secrets()["DEPLOY_KEY"] == "s3cr3t"
