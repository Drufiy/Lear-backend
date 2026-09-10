"""Action: github-open-issue (CONNECTOR_REWRITE_SPEC §4b, G0 decision).

The CI surface's "alert" is an escalation, not a fix. Lear's primary CI value
is the open-pr / apply-ci-fix flow -- it fixes the failure. This action is what
it reaches for when it has a diagnosis but *no safe auto-fix*: file a GitHub
issue carrying that diagnosis as a durable, team-visible record.

APPROVAL tier, reversible=True: outbound and team-visible (an issue shows up in
the repo's tracker and can notify watchers), so it gets the same approval gate
as datadog-alert / pagerduty-page -- but unlike a page or a Datadog event, a
GitHub issue can simply be closed, so it is genuinely reversible.
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


class GitHubOpenIssueAction(Action):
    spec = ActionSpec(
        id="github-open-issue",
        summary="Open a GitHub issue escalating a CI failure Lear can't safely auto-fix",
        risk_tier=RiskTier.APPROVAL,
        reversible=True,
        capabilities=("alert",),
        approval_hint="This will open a visible issue in the repo's tracker",
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
                    impact="Visible in the repo's issue tracker and may notify watchers; reversible by closing the issue",
                )
            ],
        )

    def execute(self, ctx: ActionContext) -> ActionResult:
        gh = ctx.extra.get("connectors", {}).get("github")
        if not gh:
            return ActionResult(status=ActionResultStatus.FAILED, summary="GitHub connector is missing or not configured.")
        repo = ctx.target.resource
        title = self._title(ctx)
        try:
            resp = gh.create_issue(repo, title, self._body(ctx))
        except Exception as exc:  # noqa: BLE001
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"open-issue failed: {exc}")
        number = resp.get("number") if isinstance(resp, dict) else None
        url = resp.get("html_url", "") if isinstance(resp, dict) else ""
        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"opened issue #{number} on {repo}" + (f" ({url})" if url else ""),
            detail={"repo": repo, "number": number, "url": url, "title": title},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        gh = ctx.extra.get("connectors", {}).get("github")
        if not gh:
            return VerificationResult(ok=False, detail="could not verify: GitHub connector missing")
        number = result.detail.get("number")
        if not number:
            return VerificationResult(ok=False, detail="could not verify: no issue number was returned")
        repo = result.detail.get("repo") or ctx.target.resource
        try:
            issue = gh.get_issue(repo, number)
        except Exception as exc:  # noqa: BLE001
            return VerificationResult(ok=False, detail=f"issue #{number} not found: {exc}")
        confirmed = isinstance(issue, dict) and issue.get("number") == number and issue.get("state") == "open"
        if confirmed:
            return VerificationResult(ok=True, detail=f"issue #{number} is open on {repo}")
        return VerificationResult(ok=False, detail=f"issue #{number} not found or not open on {repo}")
