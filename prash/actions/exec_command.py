"""Action: exec (Track C, sprint-2 Kubernetes Depth, PRASH_V2.md §7b).

Last piece of "Kubernetes Actions." Deliberately different in kind from
restart-pod/rollback/scale/edit-configmap/edit-secret, not just in degree:
every other action here does one well-defined Kubernetes API mutation.
This runs an arbitrary command inside a live container -- unbounded blast
radius, bounded only by what the container's own user and filesystem
permit. Discussed explicitly with Aradhya before building (2026-08-17,
PRASH_V2.md §9): scoped to RiskTier.APPROVAL, same permission pattern as
every other action here, no command allowlist and no automated-brain
carve-out -- the permission system is the safety net, consistent with how
this whole action model already works. A stricter posture (restricted
command set, keeping it out of brain-automated paths) was considered and
explicitly not chosen for this first version.

Wired to Track B's Kubernetes connector (prash/connectors/kubernetes.py,
owned by Aradhya) -- same split as every other action: the connector runs
the single operation, this action owns planning, permission gating, and
verification.
"""

from __future__ import annotations

from ..connectors.kubernetes import exec_in_pod, get_pod_status
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

# Same cap as the connector's own truncation -- keeps the summary/detail
# shown to the user (and written to the audit log) bounded even if the
# connector layer's cap is ever changed independently.
_SUMMARY_OUTPUT_PREVIEW = 500


class ExecAction(Action):
    spec = ActionSpec(
        id="exec",
        summary="Run a command inside a pod and capture its output",
        risk_tier=RiskTier.APPROVAL,
        reversible=False,
        capabilities=("exec_in_pod",),
        approval_hint="Always prompts, even in bypass mode -- this runs anything the container's own permissions allow, the highest blast-radius action Prash has.",
    )

    def _split(self, ctx: ActionContext) -> tuple[str, str]:
        namespace, _, pod = ctx.target.resource.partition("/")
        return (namespace or "default", pod)

    def _command(self, ctx: ActionContext) -> str | None:
        return ctx.extra.get("exec_command")

    def plan(self, ctx: ActionContext) -> Plan:
        namespace, pod = self._split(ctx)
        command = self._command(ctx) or "(no command given)"
        container = ctx.extra.get("container")
        target = f"{pod} in {namespace}" + (f", container {container}" if container else "")
        return Plan(
            action_id=self.spec.id,
            reversible=False,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Check pod {pod} exists in {namespace}", impact="read-only"),
                PlanStep(description=f"Exec into {target}: `{command}`"),
                PlanStep(description="Capture stdout/stderr and exit code"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        namespace, pod = self._split(ctx)
        command = self._command(ctx)
        if not command:
            return ActionResult(status=ActionResultStatus.FAILED, summary="no --exec-command given")

        # Checked explicitly before attempting the WebSocket exec: a
        # nonexistent pod doesn't fail with a clean, single exception shape
        # the way a plain REST call does (get_configmap()/scale_deployment()
        # can just catch ApiException(404) and return None/False) -- found
        # live 2026-08-17, a missing pod surfaced as a raw
        # AttributeError('NoneType' object has no attribute 'decode') deep
        # inside the WebSocket client, not a clean "not found." Checking
        # first with the same get_pod_status() every other pod-targeting
        # action already uses avoids depending on that internal shape.
        if not get_pod_status(namespace, pod):
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"pod {namespace}/{pod} not found")

        container = ctx.extra.get("container")
        try:
            result = exec_in_pod(namespace, pod, ["sh", "-c", command], container=container)
        except Exception as exc:  # noqa: BLE001 — report honestly, never fake a result
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"exec failed: {exc}")

        # SUCCEEDED means "Prash ran the command and captured a real
        # result," not "the command exited 0" -- those are different
        # things. A diagnostic command that legitimately exits non-zero
        # (grep finding nothing, a health check reporting unhealthy) is
        # still a successful exec, and the exit code is right there in the
        # summary/detail for the user to read, not silently collapsed into
        # a single success/fail bit.
        stdout_preview = result["stdout"][:_SUMMARY_OUTPUT_PREVIEW]
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"{namespace}/{pod}: `{command}` exited {result['exit_code']}" + (f" — {stdout_preview}" if stdout_preview.strip() else ""),
            detail={
                "namespace": namespace,
                "pod": pod,
                "command": command,
                "exit_code": str(result["exit_code"]),
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            },
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        # There is no independent way to verify an arbitrary command's
        # *effect* was correct -- "correct" isn't a thing this action can
        # know. verify() here only confirms the exec genuinely ran and
        # returned a real exit code, not that a bug slipped past silently.
        if result.status is not ActionResultStatus.SUCCEEDED:
            return VerificationResult(ok=False, detail="exec did not complete")
        exit_code = result.detail.get("exit_code")
        return VerificationResult(ok=exit_code is not None, detail=f"exit_code={exit_code}")
