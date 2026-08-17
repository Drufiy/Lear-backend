"""Action: scale (Track C, sprint-2 Kubernetes Depth, PRASH_V2.md §7b).

Approval tier: scaling to 0 (or far below current load) takes a service
down as surely as a bad rollback, so it gets the same "always requires an
explicit per-action grant, even in bypass mode" treatment as rollback --
see RiskTier's own docstring, which already names scale as an APPROVAL-tier
example.

Wired to Track B's Kubernetes connector (prash/connectors/kubernetes.py,
owned by Aradhya) -- same split as restart-pod and rollback: the connector
does the single clear write, this action owns planning, permission gating,
and verification.
"""

from __future__ import annotations

from ..connectors.kubernetes import get_deployment_replicas, scale_deployment
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


class ScaleAction(Action):
    spec = ActionSpec(
        id="scale",
        summary="Scale a Deployment's replica count",
        risk_tier=RiskTier.APPROVAL,
        reversible=True,
        capabilities=("get_deployment_replicas", "scale_deployment"),
        approval_hint="Always prompts, even in bypass mode -- scaling to 0 takes a service down as surely as a bad rollback.",
    )

    def _split(self, ctx: ActionContext) -> tuple[str, str]:
        namespace, _, deployment = ctx.target.resource.partition("/")
        return (namespace or "default", deployment)

    def plan(self, ctx: ActionContext) -> Plan:
        namespace, deployment = self._split(ctx)
        replicas = ctx.extra.get("replicas")
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Read current replica count for {deployment} in {namespace}", impact="read-only"),
                PlanStep(description=f"Set {deployment} to {replicas} replicas"),
                PlanStep(description=f"Confirm {deployment} reports {replicas} replicas"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        namespace, deployment = self._split(ctx)
        replicas = ctx.extra.get("replicas")
        if replicas is None:
            return ActionResult(status=ActionResultStatus.FAILED, summary="--replicas not specified")
        if replicas < 0:
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"replicas must be >= 0, got {replicas}")
        try:
            ok = scale_deployment(namespace, deployment, replicas)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"scale failed: {exc}")
        if not ok:
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"deployment {namespace}/{deployment} not found")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"{namespace}/{deployment} scaled to {replicas} replicas",
            detail={"namespace": namespace, "deployment": deployment, "replicas": str(replicas)},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        namespace, deployment = self._split(ctx)
        target = ctx.extra.get("replicas")
        try:
            actual = get_deployment_replicas(namespace, deployment)
        except Exception as exc:  # noqa: BLE001
            return VerificationResult(ok=False, detail=f"could not verify: {exc}")
        if actual is None:
            return VerificationResult(ok=False, detail=f"deployment {namespace}/{deployment} not found after scale")
        ok = actual == target
        return VerificationResult(ok=ok, detail=f"replicas={actual} (target={target})")
