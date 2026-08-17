"""Action: apply-gitlab-ci-fix (Sprint 2 Tier 2, PRASH_V2.md §7b).

GitLab counterpart to apply_ci_fix.py's ApplyCiFixAction -- same job (turn a
diagnosis's proposed file changes into a real branch + commit + a request
for human review), different write path underneath. GitHub needs a
blob/tree/commit/ref sequence because its Git Data API has no one-call
primitive for "create a branch and commit N files to it." GitLab's Commits
API does have one (``start_branch`` + ``actions``), so this is genuinely
simpler, not just a renamed copy -- see GitLabConnector.create_commit.
"""

from __future__ import annotations

from typing import Any

from ..connectors.gitlab import GitLabConnector, GitLabError
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


class ApplyGitlabCiFixAction(Action):
    spec = ActionSpec(
        id="apply-gitlab-ci-fix",
        summary="Apply a diagnosed GitLab CI fix as a real branch + commit, then open a merge request",
        risk_tier=RiskTier.SAFE,
        reversible=True,
        capabilities=("repo", "apply_fix", "open_mr"),
        approval_hint="Writes a new branch and commit under the GITLAB_TOKEN in your local credentials file, then opens a merge request. Nothing merges without a separate human review on GitLab.",
    )

    def _gitlab(self, ctx: ActionContext) -> GitLabConnector:
        return ctx.extra["connectors"]["gitlab"]

    def _branch_name(self, ctx: ActionContext) -> str:
        pipeline_id = ctx.extra.get("pipeline_id")
        return f"prash/fix-pipeline-{pipeline_id}" if pipeline_id else "prash/fix"

    def _file_changes(self, ctx: ActionContext) -> list[Any]:
        return ctx.extra.get("file_changes", [])

    def plan(self, ctx: ActionContext) -> Plan:
        project = ctx.target.resource
        branch = self._branch_name(ctx)
        changes = self._file_changes(ctx)
        steps = [
            PlanStep(description=f"Resolve project {project} and its default branch", impact="read-only"),
            PlanStep(description=f"Commit {len(changes)} file(s) to new branch '{branch}'"),
        ]
        for fc in changes:
            steps.append(PlanStep(description=f"Write {fc.path}", impact=fc.explanation))
        steps.append(PlanStep(description=f"Open merge request '{branch}' -> default branch"))
        return Plan(action_id=self.spec.id, reversible=True, risk_tier=self.spec.risk_tier, steps=steps)

    def execute(self, ctx: ActionContext) -> ActionResult:
        gl = self._gitlab(ctx)
        if not gl.authenticate():
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary="GitLab authentication failed (GITLAB_TOKEN missing or invalid)",
            )

        changes = self._file_changes(ctx)
        if not changes:
            return ActionResult(status=ActionResultStatus.FAILED, summary="no file changes with content to apply")

        project = ctx.target.resource
        branch = self._branch_name(ctx)

        try:
            base_branch = gl.get_repo(project)["default_branch"]

            actions = []
            for fc in changes:
                # Same fidelity guarantee as ApplyCiFixAction: edits apply
                # against the file's real current content on the default
                # branch, not a regenerated whole file, so anything the
                # model didn't explicitly edit survives untouched.
                file_exists = True
                original = None
                if fc.edits:
                    original = gl.get_file_content(project, fc.path, base_branch)
                else:
                    try:
                        gl.get_file_content(project, fc.path, base_branch)
                    except GitLabError as exc:
                        if "404" not in str(exc):
                            raise
                        file_exists = False
                content = fc.apply(original)
                actions.append(
                    {
                        "action": "update" if file_exists else "create",
                        "file_path": fc.path,
                        "content": content,
                    }
                )

            message = ctx.extra.get("commit_message") or f"Prash: fix {len(changes)} file(s) from GitLab CI diagnosis"
            commit = gl.create_commit(project, branch, message, actions, start_branch=base_branch)
            commit_sha = commit["id"]
        except Exception as exc:  # noqa: BLE001 — report honestly, never fake a fix
            detail = str(exc)
            if "Branch already exists" in detail:
                return ActionResult(
                    status=ActionResultStatus.FAILED,
                    summary=f"a fix was already proposed on branch '{branch}' — check for an existing MR before retrying",
                )
            return ActionResult(status=ActionResultStatus.FAILED, summary=f"could not write the fix commit: {exc}")

        title = ctx.extra.get("title") or f"Prash: fix {len(changes)} file(s) from GitLab CI diagnosis"
        body = ctx.extra.get("body") or (
            "Automated fix by Prash, from a GitLab CI diagnosis.\n\n"
            + "\n".join(f"- `{fc.path}`: {fc.explanation}" for fc in changes)
        )
        try:
            mr = gl.create_mr(project, title=title, source_branch=branch, target_branch=base_branch, body=body)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(
                status=ActionResultStatus.FAILED,
                summary=f"commit '{commit_sha[:7]}' pushed to '{branch}', but opening the MR failed: {exc}",
                detail={"branch": branch, "commit_sha": commit_sha},
            )

        return ActionResult(
            status=ActionResultStatus.SUCCEEDED,
            summary=f"opened MR !{mr['iid']} with {len(changes)} file(s): {mr['web_url']}",
            detail={"mr_iid": mr["iid"], "web_url": mr["web_url"], "branch": branch},
        )

    def verify(self, ctx: ActionContext, result: ActionResult) -> VerificationResult:
        if "mr_iid" not in result.detail:
            return VerificationResult(ok=False, detail="no MR was opened to verify")
        try:
            mr = self._gitlab(ctx).get_mr(ctx.target.resource, result.detail["mr_iid"])
        except Exception:  # noqa: BLE001
            return VerificationResult(ok=False, detail="could not confirm MR exists")
        ok = mr.get("state") == "opened"
        return VerificationResult(ok=ok, detail=f"MR !{mr.get('iid')} state={mr.get('state')}")
