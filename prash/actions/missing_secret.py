"""Action: request-secret (Track C #1).

Closes the single most common dead end seen in v1 testing (``needs_secret``).
Instead of reporting "manual_required", Prash asks the user for the value,
stores it locally (never on Drufiy's servers), and re-triggers the blocked job.

Precedence for the secret value:
    1. ctx.secrets[name]        (already supplied on the command line / env)
    2. credential store         (PRASH_SECRET_<name> in the local .env)
    3. interactive prompt       (via the interface's secret_input callable)
If none of those yield a value, the action returns NEEDS_INPUT and the
dispatcher records it honestly in the audit log.
"""

from __future__ import annotations

from typing import Callable, Optional

from ..credentials import CredentialStore
from .contract import (
    Action,
    ActionContext,
    ActionResult,
    ActionResultStatus,
    ActionSpec,
    Plan,
    PlanStep,
    RiskTier,
    VerificationResult,
)


class RequestSecretAction(Action):
    spec = ActionSpec(
        id="request-secret",
        summary="Request a missing secret, store it locally, then re-trigger the blocked job",
        risk_tier=RiskTier.SAFE,
        reversible=True,
        capabilities=("secret_store", "re_run_job"),
        approval_hint="The value is written to your local credentials file only.",
    )

    def _name(self, ctx: ActionContext) -> str:
        return str(ctx.extra.get("secret_name", ""))

    def plan(self, ctx: ActionContext) -> Plan:
        name = self._name(ctx)
        job = ctx.extra.get("job", ctx.target.resource)
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Request value for secret '{name}'"),
                PlanStep(description=f"Store '{name}' in local credentials file", impact="local only"),
                PlanStep(description=f"Re-trigger blocked job '{job}'"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        name = self._name(ctx)
        if not name:
            return ActionResult(status=ActionResultStatus.FAILED, summary="no secret_name supplied")

        value = ctx.secrets.get(name) or ctx.extra.get("secret_value")
        if not value:
            store = ctx.extra.get("store", CredentialStore.from_env())
            value = store.secrets().get(name)
        if not value:
            secret_input: Optional[Callable[[str, str], str]] = ctx.extra.get("secret_input")
            if secret_input is None:
                return ActionResult(
                    status=ActionResultStatus.NEEDS_INPUT,
                    summary=f"secret '{name}' required; nothing to run until a value is provided",
                )
            value = secret_input(name, ctx.extra.get("secret_hint", ""))
            if not value:
                return ActionResult(
                    status=ActionResultStatus.NEEDS_INPUT,
                    summary=f"no value given for '{name}'",
                )

        store = ctx.extra.get("store", CredentialStore.from_env())
        store.set_secret(name, value)

        runner = ctx.extra.get("runner")
        re_run = "not triggered"
        if runner is not None:
            try:
                runner.re_run(ctx.target.resource)
                re_run = "triggered"
            except NotImplementedError:
                re_run = "queued (runner connector not wired)"

        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"secret '{name}' stored locally; job re-run {re_run}",
            detail={"secret_name": name, "re_run": re_run},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        store = ctx.extra.get("store", CredentialStore.from_env())
        name = result.detail.get("secret_name")
        stored = name in store.secrets()
        return VerificationResult(ok=stored, detail=f"secret '{name}' present in local store: {stored}")
