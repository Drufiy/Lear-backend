"""Action: gitlab-open-issue (CONNECTOR_REWRITE_SPEC §4b, G3 — GitLab mirror
of github-open-issue).

Same reasoning as github-open-issue: the CI surface's "alert" is an escalation,
not a fix. Lear's primary CI value is the open-mr / apply-gitlab-ci-fix flow;
this action is what it reaches for when it has a diagnosis but no safe
auto-fix -- file a GitLab issue carrying that diagnosis as a durable,
team-visible record.

APPROVAL tier, reversible=True: outbound + team-visible, so the same approval
gate as the other alert actions; reversible because a GitLab issue can be
closed.
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


class GitLabOpenIssueAction(Action):
    spec = ActionSpec(
        id="gitlab-open-issue",
        summary="Open a GitLab issue escalating a CI failure Lear can't safely auto-fix",
        risk_tier=RiskTier.APPROVAL,
        reversible=True,
        capabilities=("alert",),
        approval_hint="This will open a visible issue in the project's tracker",
    )

    @staticmethod
    def _title(ctx: ActionContext) -> str:
        return ctx.extra.get("title") or f"Lear: CI failure on {ctx.target.resource}"

    @staticmethod
    def _body(ctx: ActionContext) -> str:
        return ctx.extra.get("body") or (
            f"Lear detected a CI failure on `{ctx.target.resource}` and is escalating it "
            f"because no safe automated fix was available.\n\n"
            f"(Opened by Lear. Close this issue once it's handled.)"
        )

    def plan(self, ctx: ActionContext) -> Plan:
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(
                    description=f"Open issue '{self._title(ctx)}' on {ctx.target.resource}",
                    impact="Visible in the project's issue tracker and may notify members; reversible by closing the issue",
                )
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        gl = ctx.extra.get("connectors", {}).get("gitlab")
        if not gl:
            return ActionResult(status=ActionResultStatus.FAILED, summary="GitLab connector is missing or not configured.")
        project = ctx.target.resource
        title = self._title(ctx)
        try:
            resp = gl.create_issue(project, title, self._body(ctx))
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"open-issue failed: {exc}")
        iid = resp.get("iid") if isinstance(resp, dict) else None
        url = resp.get("web_url", "") if isinstance(resp, dict) else ""
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"opened issue !{iid} on {project}" + (f" ({url})" if url else ""),
            detail={"project": project, "iid": iid, "url": url, "title": title},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        gl = ctx.extra.get("connectors", {}).get("gitlab")
        if not gl:
            return VerificationResult(ok=False, detail="could not verify: GitLab connector missing")
        iid = result.detail.get("iid")
        if not iid:
            return VerificationResult(ok=False, detail="could not verify: no issue iid was returned")
        project = result.detail.get("project") or ctx.target.resource
        try:
            issue = gl.get_issue(project, iid)
        except Exception as exc:  # noqa: BLE001
            return VerificationResult(ok=False, detail=f"issue !{iid} not found: {exc}")
        confirmed = isinstance(issue, dict) and issue.get("iid") == iid and issue.get("state") == "opened"
        if confirmed:
            return VerificationResult(ok=True, detail=f"issue !{iid} is open on {project}")
        return VerificationResult(ok=False, detail=f"issue !{iid} not found or not open on {project}")
