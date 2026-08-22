"""Action: snyk-ignore-issue (Sprint 2 Tier 3, PRASH_V2.md §7b).

APPROVAL tier, not SAFE: unlike muting a monitor or silencing an alert
(which just quiet noise around a problem someone else will still fix),
ignoring a vulnerability is Prash asserting "we're accepting this risk" --
a real security judgment call that should never happen without an explicit
human yes, even in bypass mode.

ctx.target.resource is "project_id/issue_id" (same slash-split convention
edit-configmap/edit-secret already use for namespace/name) -- a Snyk
ignore always targets one specific issue on one specific project, not a
project-wide operation.
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


class SnykIgnoreIssueAction(Action):
    spec = ActionSpec(
        id="snyk-ignore-issue",
        summary="Ignore a specific Snyk vulnerability for a bounded time",
        risk_tier=RiskTier.APPROVAL,
        reversible=True,
        capabilities=("ignore_issue",),
        approval_hint="Always prompts, even in bypass mode -- accepting a known vulnerability is a real security judgment call.",
    )

    def _split(self, ctx: ActionContext) -> tuple[str, str]:
        project_id, _, issue_id = ctx.target.resource.partition("/")
        return project_id, issue_id

    def plan(self, ctx: ActionContext) -> Plan:
        project_id, issue_id = self._split(ctx)
        reason = ctx.extra.get("reason", "(no reason given)")
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[PlanStep(description=f"Ignore issue {issue_id} on project {project_id}: {reason}", impact="accepts a known vulnerability")],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        snyk = ctx.extra.get("connectors", {}).get("snyk")
        if not snyk:
            return ActionResult(status=ActionResultStatus.FAILED, summary="Snyk connector is missing or not configured.")
        project_id, issue_id = self._split(ctx)
        if not issue_id:
            return ActionResult(status=ActionResultStatus.FAILED, summary="resource must be 'project_id/issue_id' -- no issue_id given")
        reason = ctx.extra.get("reason")
        if not reason:
            return ActionResult(status=ActionResultStatus.FAILED, summary="no --reason given -- an ignore without a stated reason is exactly the audit gap this action must not create")
        try:
            snyk.ignore_issue(project_id, issue_id, reason)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"ignore failed: {exc}")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"issue {issue_id} on {project_id} ignored: {reason}",
            detail={"project_id": project_id, "issue_id": issue_id, "reason": reason},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        # Snyk's ignore endpoint returns the updated ignore list on success;
        # a 200 response from execute() is already the strongest signal
        # available without a second dedicated "is this issue ignored" read
        # endpoint this session hasn't verified. Report what's known.
        return VerificationResult(ok=result.status == ActionResultStatus.SUCCEEDED, detail=f"reason recorded: {result.detail.get('reason', '')}")
