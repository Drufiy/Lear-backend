"""Track A day 13 — the integration seam that turns a diagnosis into a
dispatched action (PRASH_V2.md §6 day 13: "Integration + fix whatever the
skeleton's stubs were hiding").

    prash fix <namespace>/<pod>          k8s runtime diagnosis -> recommended_action -> permission pipeline
    prash fix <owner>/<repo> --ci --run-id <n>   multi-failure CI diagnosis (Track D tier 2)

Owned by Track A. Consumes Track B's kubernetes connector and Track D's
brain (format_k8s_context / diagnose_failure / diagnose_multi_failure). This
is the only place the dispatcher reads Diagnosis.recommended_action — the
seam Aradhya's schema built for us (§6 cross-track, schemas.py docstring).
"""

from __future__ import annotations

from typing import Optional

from rich.panel import Panel

from . import ui
from .brain.diagnosis_agent import (
    deployment_name_from_pod,
    diagnose_failure,
    find_deployment_manifest,
    format_k8s_context,
)
from .brain.gitlab_log_fetcher import fetch_pipeline_logs
from .brain.log_fetcher import fetch_workflow_logs
from .brain.multi_diagnosis import MultiFailureResult, diagnose_multi_failure
from .brain.schemas import Diagnosis
from .connectors.kubernetes import get_pod_events, get_pod_logs, get_pod_status

# Actions Prash can dispatch on its own once the brain says so. rollback is
# deliberately absent: it needs the owning Deployment's name, which Track B
# doesn't derive from a pod (no pod->deployment lookup), so it surfaces as a
# manual next-step instead of us guessing. scale has no action this sprint
# (§7 out of scope) — same honest surface, no fabricated capability.
_AUTO_ACTIONS = {"restart_pod": "restart-pod"}


class FixTargetError(Exception):
    """The requested target could not be diagnosed (bad shape or not found)."""


def split_k8s_target(target: str) -> tuple[str, str]:
    parts = target.split("/")
    if len(parts) != 2 or not all(parts):
        raise FixTargetError(f"expected <namespace>/<pod> target, got {target!r}")
    return parts[0], parts[1]


def recommended_action_id(recommended_action: str | None) -> str | None:
    """Map the brain's recommended_action to a registered action id, or None
    when there is nothing safe for Prash to run on its own."""
    if not recommended_action:
        return None
    return _AUTO_ACTIONS.get(recommended_action)


async def diagnose_k8s_pod(
    namespace: str,
    pod: str,
    repo: Optional[str] = None,
    access_token: Optional[str] = None,
    default_branch: str = "main",
) -> Diagnosis:
    """Gather Track B's status/logs/events for a pod, feed them to Track D's
    brain, and return the Diagnosis. Raises FixTargetError if the pod isn't
    there — get_pod_status() is 404-as-empty-list by contract, so an empty
    list is the not-found signal, not an exception.

    When ``repo`` + ``access_token`` are supplied, the brain additionally gets
    the investigation tools (fetch_file / list_directory / search_code) pointed
    at the repository holding the Deployment manifest, so it can read the
    manifest and propose a corrected one.

    Why this exists (root cause found 2026-08-16, PRASH_V2.md §9): without a
    repo, a runtime diagnosis can only ever answer restart_pod / rollback /
    scale -- and since most real Kubernetes failures (missing config, bad image
    tag, OOM limits, unmounted ConfigMap) are fixed by editing a manifest, not
    by restarting, Prash correctly declined essentially every real case. Six
    live diagnoses, six honest "no action can help" verdicts. Correct every
    time, and useless every time. Reading the manifest is what turns that into
    a fix.
    """
    pods = get_pod_status(namespace, pod)
    if not pods:
        raise FixTargetError(f"pod {namespace}/{pod} not found")
    pod_status = pods[0]
    logs = get_pod_logs(namespace, pod)
    events = get_pod_events(namespace, pod)
    context = format_k8s_context(pod_status, logs, events)

    investigation_context = None
    if repo and access_token:
        investigation_context = {
            "repo_full_name": repo,
            "access_token": access_token,
            "default_branch": default_branch,
        }
        # Resolve the Deployment manifest deterministically and hand the model
        # its real content, rather than leaving discovery to search_code --
        # which returned zero results for a file that provably exists when this
        # was first run live (2026-08-16). See find_deployment_manifest().
        deployment = deployment_name_from_pod(pod)
        manifest_path, manifest_content = await find_deployment_manifest(
            repo, access_token, deployment, default_branch
        )
        if manifest_path:
            context += (
                f"\n\n=== DEPLOYMENT MANIFEST ({manifest_path}) ===\n"
                f"{manifest_content}\n"
                f"(This is the live content of the manifest defining Deployment "
                f"'{deployment}', already fetched for you from {repo}. If the fix is a "
                f"manifest change, return an edits entry in files_changed with path "
                f"exactly '{manifest_path}' — old_content copied verbatim from this "
                f"content, not a regenerated new_content.)"
            )

    return await diagnose_failure(
        logs=context,
        # With a manifest repo wired up, the brain's investigation tools read
        # from it, so repo_full_name must name that repo -- otherwise the
        # prompt would claim one identity while fetch_file used another. The
        # pod's own identity is already carried in the POD STATUS block.
        repo_full_name=repo or f"{namespace}/{pod}",
        commit_message="(no commit — Kubernetes pod diagnosis)",
        workflow_name="kubernetes",
        investigation_context=investigation_context,
        # CI diagnosis arrives with the failing logs already in the prompt, so
        # investigation there is a bonus lookup or two and 2 steps is plenty.
        # Finding a Deployment manifest is the opposite: the model starts with
        # no idea where it lives, so it needs search_code -> (list_directory)
        # -> fetch_file BEFORE it can write anything. Caught live on the first
        # real run (2026-08-16): at max_steps=2 the model was cut off
        # mid-investigation and the forced final call came back still asking
        # for a file (a fetch_file tool call where submit_diagnosis was
        # required), which then burned the whole diagnosis.
        investigation_max_steps=5 if investigation_context else 2,
    )


async def diagnose_ci_run(run_id: int, repo_full_name: str, access_token: str) -> MultiFailureResult:
    """Fetch a GitHub run's logs and split per-job with Track D's multi-failure
    diagnosis. commit_message is best-effort here (fetch_workflow_logs takes
    run_id + repo only) — the brain still gets run context via workflow_name."""
    logs = await fetch_workflow_logs(run_id, repo_full_name, access_token)
    return await diagnose_multi_failure(
        logs=logs,
        repo_full_name=repo_full_name,
        commit_message="(unknown — multi-failure diagnosis from run logs)",
        workflow_name=f"github run {run_id}",
    )


async def diagnose_gitlab_ci_run(pipeline_id: int, project: str, access_token: str) -> MultiFailureResult:
    """GitLab counterpart to diagnose_ci_run (Sprint 2 Tier 2, PRASH_V2.md
    §7b) -- same multi-failure diagnosis brain, fed from a pipeline's job
    traces instead of a workflow run's log ZIP. The brain itself is already
    provider-agnostic (it only ever sees preprocessed log text + a
    workflow_name label), so nothing downstream of fetch_pipeline_logs needs
    to know this came from GitLab rather than GitHub."""
    logs = await fetch_pipeline_logs(pipeline_id, project, access_token)
    return await diagnose_multi_failure(
        logs=logs,
        repo_full_name=project,
        commit_message="(unknown — multi-failure diagnosis from pipeline logs)",
        workflow_name=f"gitlab pipeline {pipeline_id}",
    )


def render_diagnosis(diagnosis: Diagnosis, console) -> None:
    console.print(
        Panel(
            f"[bold yellow]{diagnosis.problem_summary}[/bold yellow]\n\n"
            f"[dim]category[/dim] {diagnosis.category}   "
            f"[dim]fix type[/dim] {diagnosis.fix_type}   "
            f"[dim]confidence[/dim] {diagnosis.confidence:.0%}   "
            f"[dim]recommended action[/dim] {diagnosis.recommended_action or 'none'}\n\n"
            f"[bold]root cause[/bold]\n{diagnosis.root_cause}\n\n"
            f"[bold]proposed fix[/bold]\n{diagnosis.fix_description}",
            title="diagnosis",
            border_style=ui.ACCENT,
        )
    )
    if diagnosis.files_changed:
        table = ui.make_table("proposed file changes")
        table.add_column("path", style="bold")
        table.add_column("explanation", style=ui.META)
        for fc in diagnosis.files_changed:
            table.add_row(fc.path, fc.explanation)
        console.print(table)
    render_options(diagnosis, console)


def render_options(diagnosis: Diagnosis, console) -> None:
    """Render the ranked options menu — the Track A half of the "ask, don't
    quit" flow (PRASH_V2.md §9, 2026-08-15). Purely presentational: every
    option carries its own rationale and exactly one is marked the default
    (what Prash would pick if forced). The actual pick happens in cli.py and
    whatever gets picked still runs through the normal permission pipeline.
    """
    if not diagnosis.options:
        return
    lines = []
    for i, opt in enumerate(diagnosis.options, start=1):
        default = "  [green](default — what Prash would pick)[/green]" if opt.is_default else ""
        action = opt.action or "escalate to a human (no automated action)"
        lines.append(f"[bold]{i}.[/bold] {action}{default}\n    [dim]{opt.rationale}[/dim]")
    console.print(
        Panel(
            "\n\n".join(lines),
            title="[bold yellow]Prash is unsure — choose how to proceed[/bold yellow]",
            border_style=ui.WARN,
        )
    )


def render_multi_failure(result: MultiFailureResult, console) -> None:
    console.print(
        Panel(
            f"[bold yellow]{result.summary()}[/bold yellow]"
            + (
                "\n\n[bold red]still broken:[/bold red]\n" + "\n".join(f"- {s}" for s in result.unresolved_summaries())
                if result.unresolved_summaries()
                else ""
            ),
            title="multi-failure diagnosis",
            border_style=ui.ACCENT,
        )
    )
    for job, diagnosis in zip(result.job_names, result.diagnoses, strict=False):
        verdict = "[red]no fix proposed[/red]" if not diagnosis.files_changed else "[green]fix proposed[/green]"
        console.print(f"  {verdict}  [bold]{job}[/bold] — {diagnosis.problem_summary}")
