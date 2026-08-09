"""Action: open-pr (Track A done-when).

Ports Prash v1's "open a fix PR" capability into the new local-agent pipeline
end to end: plan -> permission prompt -> execute through the GitHub connector
-> verify the PR exists.
"""

from __future__ import annotations

from typing import Any

from ..connectors.github import GitHubConnector
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


class OpenPrAction(Action):
    spec = ActionSpec(
        id="open-pr",
        summary="Open a fix pull request against a GitHub repository",
        risk_tier=RiskTier.SAFE,
        reversible=True,
        capabilities=("repo", "open_pr"),
        approval_hint="The PR is created under the GITHUB_TOKEN in your local credentials file.",
    )

    def _github(self, ctx: ActionContext) -> GitHubConnector:
        return ctx.extra["connectors"]["github"]

    def plan(self, ctx: ActionContext) -> Plan:
        repo = ctx.target.resource
        head = ctx.extra.get("head") or "prash/fix"
        base = ctx.extra.get("base") or "main"
        title = ctx.extra.get("title") or "Prash: fix failed CI"
        return Plan(
            action_id=self.spec.id,
            reversible=True,
            risk_tier=self.spec.risk_tier,
            steps=[
                PlanStep(description=f"Resolve repository {repo}", impact="read-only"),
                PlanStep(description=f"Open pull request {head} -> {base} titled '{title}'"),
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        gh = self._github(ctx)
        if not gh.authenticate():
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="GitHub authentication failed (GITHUB_TOKEN missing or invalid)",
            )
        repo = ctx.target.resource
        try:
            pr = gh.create_pr(
                repo,
                title=ctx.extra.get("title", "Prash: fix failed CI"),
                head=ctx.extra.get("head", "prash/fix"),
                base=ctx.extra.get("base", "main"),
                body=ctx.extra.get("body", "Automated fix by Prash."),
            )
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"could not open PR: {exc}")
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"opened PR #{pr['number']}: {pr['html_url']}",
            detail={"pr_number": pr["number"], "html_url": pr["html_url"]},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        try:
            pr = self._github(ctx).get_pr(ctx.target.resource, result.detail["pr_number"])
        except Exception:  # noqa: BLE001
            return VerificationResult(ok=False, detail="could not confirm PR exists")
        ok = pr.get("state") == "open"
        return VerificationResult(ok=ok, detail=f"PR #{pr['number']} state={pr.get('state')}")
