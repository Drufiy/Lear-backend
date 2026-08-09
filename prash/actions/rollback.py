"""Action: rollback (Track C #3).

Approval tier: always requires an explicit per-action grant, even in bypass
mode.

Per PRASH_V2.md §6 cross-track dependency #2, "last known good" is answered by
a ``get_previous_revision()``-shaped read on the Track B connector — there is
deliberately no separate release-history store. Until Track B implements that
read (and a rollout driver exists), execute reports honestly rather than
claiming a rollback it cannot perform.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..connectors.kubernetes import get_previous_revision
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


class RollbackAction(Action):
    spec = ActionSpec(
        id="rollback",
        summary="Roll back a deployment to the last known good revision",
        risk_tier=RiskTier.APPROVAL,
        reversible=True,
        capabilities=("get_previous_revision", "rollback"),
        approval_hint="Production rollbacks always prompt, even in bypass mode.",
    )

    def _split(self, ctx: ActionContext) -> tuple[str, str]:
        namespace, _, deployment = ctx.target.resource.partition("/")
        return (namespace or "default", deployment)

    def plan(self, ctx: ActionContext) -> Plan:
        namespace, deployment = self._split(ctx)
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Read last known good revision for deployment {deployment} in {namespace}", impact="read-only"),
                PlanStep(description=f"Set {deployment} to the identified revision"),
                PlanStep(description="Confirm rollout completes and health checks pass"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        namespace, deployment = self._split(ctx)
        try:
            previous = get_previous_revision(namespace, deployment)
        except NotImplementedError:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="release-tracking read not implemented yet (Track B): cannot identify last known good for rollback",
            )
        if not previous:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"no prior revision recorded for {namespace}/{deployment}",
            )
        revision = previous.get("revision") if isinstance(previous, dict) else previous
        driver: Optional[Callable[[str, str, Any], None]] = ctx.extra.get("rollout_driver")
        if driver is None:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"previous revision {revision} identified; no rollout driver wired to act on it",
                detail={"revision": str(revision)},
            )
        driver(namespace, deployment, revision)
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"rolled back {namespace}/{deployment} to {revision}",
            detail={"revision": str(revision)},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        checker: Optional[Callable[[str, str], bool]] = ctx.extra.get("rollout_healthy")
        if checker is None:
            return VerificationResult(ok=False, detail="no rollout health checker wired")
        namespace, deployment = self._split(ctx)
        ok = checker(namespace, deployment)
        return VerificationResult(ok=ok, detail=f"rollout healthy={ok}")
