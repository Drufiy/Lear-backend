"""Actions: vercel-redeploy, vercel-rollback (Sprint 2 Tier 3, PRASH_V2.md
§7b).

Different risk tiers, not copy-pasted: **redeploy is SAFE** -- it's a retry
of what's already deployed, same reasoning as restart-pod (routine,
low-risk, the thing you'd try first). **rollback is APPROVAL** -- it
changes what's actually live in production to a different build, the same
consequential-claim reasoning RiskTier's own docstring already applies to
Kubernetes' rollback action.

redeploy is marked reversible (it's just "try again," nothing to undo).
rollback is marked reversible too -- rolling back TO a deployment can
itself be rolled back FROM by rolling forward to a later one, same
"the same action run again undoes it" logic this repo's edit-configmap/
scale actions already use for their own reversible=True.
"""

from __future__ import annotations

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


class VercelRedeployAction(Action):
    spec = ActionSpec(
        id="vercel-redeploy",
        summary="Redeploy the latest (or a specific) Vercel deployment",
        risk_tier=RiskTier.SAFE,
        reversible=True,
        capabilities=("redeploy",),
    )

    def plan(self, ctx: ActionContext) -> Plan:
        deployment_id = ctx.extra.get("deployment_id")
        target = f"deployment {deployment_id}" if deployment_id else "the latest deployment"
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[PlanStep(description=f"Redeploy {target} for project {ctx.target.resource}")],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        vercel = ctx.extra.get("connectors", {}).get("vercel")
        if not vercel:
            return ActionResult(status=ActionResultStatus.FAILED, summary="Vercel connector is missing or not configured.")
        try:
            deployment = vercel.redeploy(ctx.target.resource, deployment_id=ctx.extra.get("deployment_id"))
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"redeploy failed: {exc}")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"redeployed {ctx.target.resource}: new deployment {deployment.get('id', deployment.get('uid', '?'))}",
            detail={"deployment": deployment},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        deployment = result.detail.get("deployment", {})
        ready_state = deployment.get("readyState", "")
        if ready_state in ("READY",):
            return VerificationResult(ok=True, detail="new deployment is READY")
        if ready_state in ("ERROR", "CANCELED"):
            return VerificationResult(ok=False, detail=f"new deployment ended in {ready_state}")
        # BUILDING/QUEUED/INITIALIZING -- genuinely still in progress at the
        # moment of the API response, not a failure to report as ok=False.
        return VerificationResult(ok=True, detail=f"new deployment triggered, state={ready_state or 'unknown'} (still in progress)")


class VercelRollbackAction(Action):
    spec = ActionSpec(
        id="vercel-rollback",
        summary="Roll production back to a specific earlier Vercel deployment",
        risk_tier=RiskTier.APPROVAL,
        reversible=True,
        capabilities=("rollback",),
        approval_hint="Always prompts, even in bypass mode -- changes what's actually live in production.",
    )

    def plan(self, ctx: ActionContext) -> Plan:
        deployment_id = ctx.extra.get("deployment_id")
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[PlanStep(description=f"Roll {ctx.target.resource} back to deployment {deployment_id or '<missing>'}", impact="changes what's live in production")],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        vercel = ctx.extra.get("connectors", {}).get("vercel")
        if not vercel:
            return ActionResult(status=ActionResultStatus.FAILED, summary="Vercel connector is missing or not configured.")
        deployment_id = ctx.extra.get("deployment_id")
        if not deployment_id:
            return ActionResult(status=ActionResultStatus.FAILED, summary="no --deployment-id given -- rollback needs a specific target, not 'whatever's latest'")
        try:
            result = vercel.rollback(ctx.target.resource, deployment_id)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"rollback failed: {exc}")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"{ctx.target.resource} rolled back to {deployment_id}",
            detail={"deployment_id": deployment_id, "result": result},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        vercel = ctx.extra.get("connectors", {}).get("vercel")
        if not vercel:
            return VerificationResult(ok=False, detail="could not verify: Vercel connector missing")
        state = vercel.poll_state(ctx.target.resource)
        current_id = state.detail.get("latest_deployment", {}).get("uid", "")
        expected_id = result.detail.get("deployment_id", "")
        ok = current_id == expected_id
        return VerificationResult(ok=ok, detail=f"current deployment now={current_id or 'unknown'}")
