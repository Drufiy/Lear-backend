"""Action: apply-ci-fix.

Closes the gap found live-testing `prash fix --ci` (PRASH_V2.md §9,
2026-08-15, CROSS-TRACK entry): the CI multi-failure path diagnosed real
problems and proposed real file changes, but never actually did anything
with them -- the "Fixed X of N" headline was true only in the sense that
the model had *proposed* a fix, not that one existed anywhere.

This is the first action where Prash writes AI-generated code into a real
repository, rather than reading state or acting on infrastructure that
already exists (restart-pod, rollback) or opening a PR between two branches
that already exist (open-pr). No local git clone: everything goes through
GitHub's Git Data API, which `GitHubConnector` already has the plumbing for.
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


class ApplyCiFixAction(Action):
    spec = ActionSpec(
        id="apply-ci-fix",
        summary="Apply a diagnosed CI fix as a real branch + commit, then open a pull request",
        risk_tier=RiskTier.SAFE,
        reversible=True,
        capabilities=("repo", "apply_fix", "open_pr"),
        approval_hint="Writes a new branch and commit under the GITHUB_TOKEN in your local credentials file, then opens a PR. Nothing merges without a separate human review on GitHub.",
    )

    def _github(self, ctx: ActionContext) -> GitHubConnector:
        return ctx.extra["connectors"]["github"]

    def _branch_name(self, ctx: ActionContext) -> str:
        run_id = ctx.extra.get("run_id")
        return f"prash/fix-run-{run_id}" if run_id else "prash/fix"

    def _file_changes(self, ctx: ActionContext) -> list[Any]:
        # FileChange.new_content is guaranteed non-empty by its own model
        # validator (prash/brain/schemas.py) -- every entry here is real.
        return ctx.extra.get("file_changes", [])

    def plan(self, ctx: ActionContext) -> Plan:
        repo = ctx.target.resource
        branch = self._branch_name(ctx)
        changes = self._file_changes(ctx)
        steps = [
            PlanStep(description=f"Resolve repository {repo} and its default branch", impact="read-only"),
            PlanStep(description=f"Create branch '{branch}' from the default branch"),
        ]
        for fc in changes:
            steps.append(PlanStep(description=f"Write {fc.path}", impact=fc.explanation))
        steps.append(PlanStep(description=f"Open pull request '{branch}' -> default branch"))
        return Plan(action_id=self.spec.id, reversible=True, risk_tier=self.spec.risk_tier, steps=steps)

    def execute(self, ctx: ActionContext) -> ActionResult:
        gh = self._github(ctx)
        if not gh.authenticate():
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="GitHub authentication failed (GITHUB_TOKEN missing or invalid)",
            )

        changes = self._file_changes(ctx)
        if not changes:
            return ActionResult(status=ActionResultStatus.FAILED, summary="no file changes with content to apply")

        repo = ctx.target.resource
        branch = self._branch_name(ctx)

        try:
            base_branch = gh.get_repo(repo)["default_branch"]
            base_sha = gh.get_branch_head_sha(repo, base_branch)
            base_tree_sha = gh.get_commit_tree_sha(repo, base_sha)

            entries = []
            for fc in changes:
                blob_sha = gh.create_blob(repo, fc.new_content)
                entries.append({"path": fc.path, "mode": "100644", "type": "blob", "sha": blob_sha})
            new_tree_sha = gh.create_tree(repo, base_tree_sha, entries)

            message = ctx.extra.get("commit_message") or f"Prash: fix {len(changes)} file(s) from CI diagnosis"
            commit_sha = gh.create_commit(repo, message, new_tree_sha, base_sha)

            gh.create_ref(repo, branch, commit_sha)
        except Exception as exc:  # noqa: BLE001 — report honestly, never fake a fix
            detail = str(exc)
            if "Reference already exists" in detail:
                return ActionResult(
                    status=ActionResultStatus.FAILED,
                    summary=f"a fix was already proposed on branch '{branch}' — check for an existing PR before retrying",
                )
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"could not write the fix commit: {exc}")

        title = ctx.extra.get("title") or f"Prash: fix {len(changes)} file(s) from CI diagnosis"
        body = ctx.extra.get("body") or (
            "Automated fix by Prash, from a CI diagnosis.\n\n"
            + "\n".join(f"- `{fc.path}`: {fc.explanation}" for fc in changes)
        )
        try:
            pr = gh.create_pr(repo, title=title, head=branch, base=base_branch, body=body)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"commit '{commit_sha[:7]}' pushed to '{branch}', but opening the PR failed: {exc}",
                detail={"branch": branch, "commit_sha": commit_sha},
            )

        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"opened PR #{pr['number']} with {len(changes)} file(s): {pr['html_url']}",
            detail={"pr_number": pr["number"], "html_url": pr["html_url"], "branch": branch},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        if "pr_number" not in result.detail:
            return VerificationResult(ok=False, detail="no PR was opened to verify")
        try:
            pr = self._github(ctx).get_pr(ctx.target.resource, result.detail["pr_number"])
        except Exception:  # noqa: BLE001
            return VerificationResult(ok=False, detail="could not confirm PR exists")
        ok = pr.get("state") == "open"
        return VerificationResult(ok=ok, detail=f"PR #{pr['number']} state={pr.get('state')}")
