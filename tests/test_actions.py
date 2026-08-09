from prash.actions.contract import ActionContext, ActionResultStatus, Decision, Target
from prash.actions.missing_secret import RequestSecretAction
from prash.actions.open_pr import OpenPrAction
from prash.actions.restart_pod import RestartPodAction
from prash.actions.rollback import RollbackAction
from prash.credentials import CredentialStore
from prash.dispatch import AskFn, Dispatcher
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


def test_restart_pod_reports_honestly_without_driver(tmp_path):
    from prash.connectors.k8s import K8sConnector

    ctx = _ctx(tmp_path, resource="default/api", extra={"connectors": {"github": FakeGitHub(), "k8s": K8sConnector({})}})
    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([RestartPodAction()])
    result = dispatcher.run("restart-pod", ctx)
    assert result.outcome.value == "executed"
    assert result.result.status is ActionResultStatus.FAILED
    assert "not built yet" in result.result.summary


def test_rollback_approval_prompts_even_in_bypass(tmp_path):
    ctx = _ctx(tmp_path, resource="acme/api", env="production")
    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([RollbackAction()])
    result = dispatcher.run("rollback", ctx, ask=FakeAsk(answer=False))
    assert result.decision is Decision.PROMPT
    assert result.result.status is ActionResultStatus.SKIPPED


def test_rollback_with_grant_attempts_but_fails_without_tracking(tmp_path):
    ctx = _ctx(tmp_path, resource="acme/api", env="staging")
    ctx.grant = True
    dispatcher = Dispatcher(mode=PermissionMode.BYPASS)
    dispatcher.register_all([RollbackAction()])
    result = dispatcher.run("rollback", ctx, ask=FakeAsk(answer=False))
    assert result.decision is Decision.ALLOW
    assert result.result.status is ActionResultStatus.FAILED
    assert "not wired yet" in result.result.summary


def test_audit_recorded_for_refused_read_only(tmp_path):
    ctx = _ctx(tmp_path, resource="acme/api")
    dispatcher = Dispatcher(mode=PermissionMode.READ_ONLY)
    dispatcher.register_all([OpenPrAction()])
    result = dispatcher.run("open-pr", ctx)
    assert result.outcome.value == "refused"
    assert dispatcher.audit.read()[-1]["decision"] == "refuse"
