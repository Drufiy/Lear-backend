"""Kubernetes connector — Track B, days 1-2 priority (PRASH_V2.md §6).

Highest-priority connector in the whole sprint: Track C's restart-pod
(Aryan, days 5-6) and Track E's watcher (Aradhya, days 9-11) are both
blocked on this existing. Ship it rough by day 2; refine after.

Reads local credentials only, per §4 — KUBECONFIG / KUBE_CONTEXT /
KUBE_NAMESPACE from .env (see .env.example). Never anything hosted.

Needs the `kubernetes` PyPI package (the official Python client).
Not yet added to a requirements file — no requirements/pyproject.toml
exists in this repo yet (see PRASH_V2.md §10, 2026-08-09 entry on the
package skeleton). Whoever adds one first, log it in §10.

The four states below are exactly what Track D is being taught to
diagnose (§8) and what Track E's watcher fires on. Keep this list and
the brain's prompt work in lockstep — don't detect a state the brain
can't yet explain.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PodStatus:
    name: str
    namespace: str
    phase: str  # Running, Pending, Failed, ...
    # One of the four states this connector watches for, or None if healthy.
    # CrashLoopBackOff | OOMKilled | ImagePullBackOff | StuckPending
    problem: str | None
    restart_count: int
    ready: bool


def get_pod_status(namespace: str, pod_name: str | None = None) -> list[PodStatus]:
    """Read-only. All pods in `namespace`, or just `pod_name` if given.

    TODO(Track B): implement against the `kubernetes` client's
    CoreV1Api.list_namespaced_pod / read_namespaced_pod. Derive
    `problem` from container statuses' waiting/terminated reasons.
    """
    raise NotImplementedError


def get_pod_logs(namespace: str, pod_name: str, tail_lines: int = 500) -> str:
    """Read-only. Recent logs for a pod (its most recent container/restart)."""
    raise NotImplementedError


def get_pod_events(namespace: str, pod_name: str) -> list[dict]:
    """Read-only. Kubernetes Events involving this pod, most recent first.

    Events are where the real story usually is for ImagePullBackOff /
    scheduling failures — logs alone often won't show why a pod never
    started.
    """
    raise NotImplementedError


def restart_pod(namespace: str, pod_name: str) -> bool:
    """WRITE. Safe-tier action per PRASH_V2.md §5 — Track C wires the
    permission check; this function assumes it has already been
    granted and just does the deletion (the Deployment/ReplicaSet
    recreates it).

    Returns True if the delete succeeded. Track C is responsible for
    the post-action verification step (§3) — re-check the pod here is
    NOT this function's job, keep it a single clear action.
    """
    raise NotImplementedError


def get_previous_revision(namespace: str, deployment_name: str) -> dict | None:
    """Read-only. The last known-good revision for a Deployment, from
    the ReplicaSet revision history Kubernetes already keeps — no
    separate state store. See PRASH_V2.md §6, cross-track dependency #2.

    Returns something Track C's rollback action can act on directly
    (e.g. a revision number `kubectl rollout undo` can target), or
    None if there's no prior revision to roll back to.
    """
    raise NotImplementedError
