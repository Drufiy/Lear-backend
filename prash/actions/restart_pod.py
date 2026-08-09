"""Action: restart-pod (Track C #2).

Safe tier: restarting a crash-looping pod is low-risk and explicitly in the v1
safe list.

Wired to Track B's Kubernetes connector (prash/connectors/kubernetes.py, owned
by Aradhya) per PRASH_V2.md §6 cross-track dependency #1. Until that connector
lands a real driver, execute reports honestly that nothing was restarted —
never a fake success.
"""

from __future__ import annotations

from ..connectors.kubernetes import get_pod_status, restart_pod as k8s_restart_pod
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

    def _split(self, ctx: ActionContext) -> tuple[str, str]:
        namespace, _, name = ctx.target.resource.partition("/")
        return (namespace or "default", name)

    def plan(self, ctx: ActionContext) -> Plan:
        namespace, name = self._split(ctx)
        return Plan(
            action_id=self.spec.id,
            reversible=False,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Check pod state for {name} in {namespace}", impact="read-only"),
                PlanStep(description=f"Restart pod {name} in {namespace}"),
                PlanStep(description=f"Confirm pod {name} returns to Running"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        namespace, name = self._split(ctx)
        try:
            ok = k8s_restart_pod(namespace, name)
        except NotImplementedError:
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"kubernetes connector not implemented yet (Track B): restart-pod for {namespace}/{name} not executed",
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"restart failed: {exc}")
        if not ok:
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"restart of {namespace}/{name} did not succeed")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"pod {namespace}/{name} restart issued",
            detail={"namespace": namespace, "name": name},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        namespace, name = self._split(ctx)
        try:
            pods = get_pod_status(namespace, name)
        except NotImplementedError as exc:
            return VerificationResult(ok=False, detail=f"cannot verify yet: {exc}")
        if not pods:
            return VerificationResult(ok=False, detail=f"pod {namespace}/{name} not found after restart")
        pod = pods[0]
        ok = pod.phase == "Running" and pod.ready and pod.problem is None
        return VerificationResult(ok=ok, detail=f"pod phase={pod.phase} ready={pod.ready} problem={pod.problem}")
