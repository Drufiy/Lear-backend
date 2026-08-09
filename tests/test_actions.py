from prash.actions.contract import ActionContext, ActionResultStatus, Decision, Target
from prash.actions.missing_secret import RequestSecretAction
from prash.actions.open_pr import OpenPrAction
from prash.actions.restart_pod import RestartPodAction
from prash.actions.rollback import RollbackAction
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

    def authenticate(self):
        return True

    def create_pr(self, repo, title, head, base, body=""):
        number = len(self.pulls) + 1
        self.pulls[number] = {"number": number, "html_url": f"https://github.com/{repo}/pull/{number}", "state": "open"}
        return self.pulls[number]

    def get_pr(self, repo, number):
        return self.pulls.get(number, {})


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
