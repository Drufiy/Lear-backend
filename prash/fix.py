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

from rich.panel import Panel
from rich.table import Table

from .brain.diagnosis_agent import diagnose_failure, format_k8s_context
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


async def diagnose_k8s_pod(namespace: str, pod: str) -> Diagnosis:
    """Gather Track B's status/logs/events for a pod, feed them to Track D's
    brain, and return the Diagnosis. Raises FixTargetError if the pod isn't
    there — get_pod_status() is 404-as-empty-list by contract, so an empty
    list is the not-found signal, not an exception."""
    pods = get_pod_status(namespace, pod)
    if not pods:
        raise FixTargetError(f"pod {namespace}/{pod} not found")
    pod_status = pods[0]
    logs = get_pod_logs(namespace, pod)
    events = get_pod_events(namespace, pod)
    context = format_k8s_context(pod_status, logs, events)
    return await diagnose_failure(
        logs=context,
        repo_full_name=f"{namespace}/{pod}",
        commit_message="(no commit — Kubernetes pod diagnosis)",
        workflow_name="kubernetes",
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


def render_diagnosis(diagnosis: Diagnosis, console) -> None:
    console.print(
        Panel(
            f"[bold]{diagnosis.problem_summary}[/bold]\n\n"
            f"[dim]category:[/dim] {diagnosis.category}   "
            f"[dim]fix type:[/dim] {diagnosis.fix_type}   "
            f"[dim]confidence:[/dim] {diagnosis.confidence:.0%}   "
            f"[dim]recommended action:[/dim] {diagnosis.recommended_action or 'none'}\n\n"
            f"[bold]root cause[/bold]\n{diagnosis.root_cause}\n\n"
            f"[bold]proposed fix[/bold]\n{diagnosis.fix_description}",
            title="diagnosis",
            border_style="cyan",
        )
    )
    if diagnosis.files_changed:
        table = Table(title="proposed file changes")
        table.add_column("path")
        table.add_column("explanation")
        for fc in diagnosis.files_changed:
            table.add_row(fc.path, fc.explanation)
        console.print(table)


def render_multi_failure(result: MultiFailureResult, console) -> None:
    console.print(
        Panel(
            f"[bold]{result.summary()}[/bold]"
            + (
                "\n\n[red]still broken:[/red]\n" + "\n".join(f"- {s}" for s in result.unresolved_summaries())
                if result.unresolved_summaries()
                else ""
            ),
            title="multi-failure diagnosis",
            border_style="cyan",
        )
    )
    for job, diagnosis in zip(result.job_names, result.diagnoses, strict=False):
        verdict = "[red]no fix proposed[/red]" if not diagnosis.files_changed else "[green]fix proposed[/green]"
        console.print(f"  {verdict}  [bold]{job}[/bold] — {diagnosis.problem_summary}")
