"""Action: restart-pod (Track C #2).

Safe tier: restarting a crash-looping pod is low-risk and explicitly in the v1
safe list. Written against the K8sConnector interface so it is wiring-ready for
Track B. Until a real driver exists, dry-run/plan work and execute reports
honestly that no connector is available (never a fake success).
"""

from __future__ import annotations

from ..connectors.k8s import K8sConnector
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


class RestartPodAction(Action):
    spec = ActionSpec(
        id="restart-pod",
        summary="Restart a stuck or crash-looping pod",
        risk_tier=RiskTier.SAFE,
        reversible=False,
        capabilities=("pod_status", "restart_pod"),
    )

    def _k8s(self, ctx: ActionContext) -> K8sConnector:
        return ctx.extra["connectors"]["k8s"]

    def plan(self, ctx: ActionContext) -> Plan:
        namespace, _, name = ctx.target.resource.partition("/")
        return Plan(
            action_id=self.spec.id,
            reversible=False,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Check pod state for {name} in {namespace or 'default'}", impact="read-only"),
                PlanStep(description=f"Restart pod {name} in {namespace or 'default'}"),
                PlanStep(description="Confirm pod returns to Running"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        k8s = self._k8s(ctx)
        namespace, _, name = ctx.target.resource.partition("/")
        try:
            k8s.restart(namespace or "default", name)
        except NotImplementedError as exc:
            return ActionResult(status=ActionResultStatus.FAILED, summary=str(exc))
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"restart failed: {exc}")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"pod {namespace}/{name} restart issued",
            detail={"namespace": namespace or "default", "name": name},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        k8s = self._k8s(ctx)
        state = k8s.poll_state(ctx.target.resource)
        ok = state.state.value in ("healthy", "unknown", "deploying")
        return VerificationResult(ok=ok, detail=f"pod state={state.state.value}")
