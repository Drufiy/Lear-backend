"""Kubernetes connector — Track B, days 1-2 priority (PRASH_V2.md §6).

Highest-priority connector in the whole sprint: Track C's restart-pod
(Aryan) and Track E's watcher (Aradhya) are both blocked on this
existing.

Reads cluster config from the standard kubectl locations — KUBECONFIG /
current-context in ~/.kube/config, optionally overridden by KUBE_CONTEXT
and KUBE_NAMESPACE environment variables. See PRASH_V2.md §10, 2026-08-09
"Pending" entry: `.env`'s values don't currently reach os.environ
automatically (a cross-track gap, not yet resolved) -- for now this only
picks them up if they're actually exported in the shell, or falls back
to kubeconfig's own current-context (which `kind create cluster` already
sets correctly for local development).

The four `problem` states below are exactly what Track D is being taught
to diagnose (§8) and what Track E's watcher fires on. Keep this list and
the brain's prompt work in lockstep -- don't detect a state the brain
can't yet explain.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from kubernetes import client, config
from kubernetes.client.rest import ApiException


@dataclass
class PodStatus:
    name: str
    namespace: str
    phase: str  # Running, Pending, Failed, Succeeded, Unknown
    # One of the four states this connector watches for, or None if healthy.
    # CrashLoopBackOff | OOMKilled | ImagePullBackOff | StuckPending
    problem: str | None
    restart_count: int
    ready: bool


# How long a pod may sit Pending / not-Ready before we call it "stuck".
# Matches PRASH_V2.md §8's 2-minute starting default.
_STUCK_THRESHOLD_SECONDS = 120

_ERR_IMAGE_REASONS = {"ImagePullBackOff", "ErrImagePull"}

_core_api: client.CoreV1Api | None = None


def _client() -> client.CoreV1Api:
    """Lazy singleton so tests can monkeypatch this module's _core_api
    directly instead of every function reaching into the kubernetes lib.
    """
    global _core_api
    if _core_api is not None:
        return _core_api

    kubeconfig = os.environ.get("KUBECONFIG")
    context = os.environ.get("KUBE_CONTEXT") or None
    config.load_kube_config(config_file=kubeconfig, context=context)
    _core_api = client.CoreV1Api()
    return _core_api


def _default_namespace(namespace: str | None) -> str:
    return namespace or os.environ.get("KUBE_NAMESPACE", "default")


def _seconds_since(ts) -> float:
    if ts is None:
        return 0.0
    now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds()


def _classify(pod: client.V1Pod) -> tuple[str | None, int, bool]:
    """Derive (problem, restart_count, ready) from a pod's real status.

    Checks every container, not just the first -- a multi-container pod
    with one healthy sidecar and one crash-looping main container must
    still be flagged.
    """
    statuses = pod.status.container_statuses or []
    restart_count = sum(s.restart_count for s in statuses) if statuses else 0
    ready = bool(statuses) and all(s.ready for s in statuses)

    problem: str | None = None
    for s in statuses:
        waiting = s.state.waiting
        terminated = s.state.terminated
        last_terminated = s.last_state.terminated if s.last_state else None

        if waiting and waiting.reason == "CrashLoopBackOff":
            problem = "CrashLoopBackOff"
            break
        if waiting and waiting.reason in _ERR_IMAGE_REASONS:
            problem = "ImagePullBackOff"
            break
        if terminated and terminated.reason == "OOMKilled":
            problem = "OOMKilled"
            break
        if last_terminated and last_terminated.reason == "OOMKilled":
            problem = "OOMKilled"
            break

    # A pod that's already restarted at least once and currently isn't ready
    # is exhibiting crash-loop behavior NOW, independent of whether
    # container_statuses.waiting.reason happens to say "CrashLoopBackOff" at
    # this exact instant. It often doesn't: state.waiting briefly clears
    # during the split-second a container is actually mid-restart-attempt
    # between backoff waits, which a point-in-time snapshot can catch --
    # confirmed live (PRASH_V2.md §10, 2026-08-09) and then confirmed again
    # by real CI flakiness on exactly this race, same day: a genuinely
    # crash-looping pod (restart_count=3, not ready, phase=Running) polled
    # with problem=None, no CrashLoopBackOff and not even the StuckPending
    # fallback below (too young for the 120s threshold). Checked BEFORE the
    # StuckPending fallback and with no age requirement -- waiting for the
    # 120s threshold here would just reproduce the same bug for two minutes.
    if problem is None and not ready and pod.status.phase == "Running" and restart_count > 0:
        problem = "CrashLoopBackOff"

    if problem is None and pod.status.phase == "Pending":
        age = _seconds_since(pod.status.start_time or pod.metadata.creation_timestamp)
        if age > _STUCK_THRESHOLD_SECONDS:
            problem = "StuckPending"

    if problem is None and not ready and pod.status.phase == "Running":
        age = _seconds_since(pod.status.start_time)
        if age > _STUCK_THRESHOLD_SECONDS:
            problem = "StuckPending"

    return problem, restart_count, ready


def get_pod_status(namespace: str, pod_name: str | None = None) -> list[PodStatus]:
    """Read-only. All pods in `namespace`, or just `pod_name` if given.

    Returns an empty list if the pod/namespace doesn't exist -- never
    raises for "not found", since Track C's restart-pod verify() step
    already handles an empty list as its "pod missing" case.
    """
    namespace = _default_namespace(namespace)
    api = _client()
    try:
        if pod_name:
            pod = api.read_namespaced_pod(name=pod_name, namespace=namespace)
            pods = [pod]
        else:
            pods = api.list_namespaced_pod(namespace=namespace).items
    except ApiException as exc:
        if exc.status == 404:
            return []
        raise

    result = []
    for pod in pods:
        problem, restart_count, ready = _classify(pod)
        result.append(
            PodStatus(
                name=pod.metadata.name,
                namespace=pod.metadata.namespace,
                phase=pod.status.phase or "Unknown",
                problem=problem,
                restart_count=restart_count,
                ready=ready,
            )
        )
    return result


def _read_pod_log_raw(api, *, name: str, namespace: str, tail_lines: int, previous: bool) -> str:
    """Real bug found live 2026-08-17 building `prash logs`: calling
    read_namespaced_pod_log() WITHOUT `_preload_content=False` on this
    kubernetes client version (36.0.3) does not return decoded text the way
    its own type hint (-> str) promises -- it returns the raw response
    stringified, i.e. the literal characters "b'...actual log text...'"
    (a bytes repr, not bytes itself, so `.strip()`/`str` checks elsewhere
    never caught it -- it silently looked like a valid non-empty string).
    This had been feeding the diagnosis brain corrupted log text for every
    runtime diagnosis since the connector was built; never noticed because
    nothing printed raw log content to a human until this command existed.
    `_preload_content=False` + manual decode (the same pattern
    stream_pod_logs() already uses) is the actual fix -- confirmed live
    against a real pod, real log lines, no more `b'...'` wrapper.
    """
    resp = api.read_namespaced_pod_log(
        name=name, namespace=namespace, tail_lines=tail_lines, previous=previous, _preload_content=False
    )
    try:
        return resp.data.decode("utf-8", errors="replace")
    finally:
        resp.release_conn()


def get_pod_logs(namespace: str, pod_name: str, tail_lines: int = 500) -> str:
    """Read-only. Recent logs for a pod.

    Tries the current container attempt first. A crash-looping pod's
    *current* attempt often has zero logs (it just restarted and hasn't
    logged anything new yet) -- the real story is in the previous
    attempt, so this falls back to `previous=True` when the current
    attempt is empty. Verified against a real CrashLoopBackOff pod
    during development (see PRASH_V2.md §10) -- this fallback is not
    theoretical, the first attempt genuinely came back empty.
    """
    namespace = _default_namespace(namespace)
    api = _client()
    try:
        logs = _read_pod_log_raw(api, name=pod_name, namespace=namespace, tail_lines=tail_lines, previous=False)
    except ApiException as exc:
        if exc.status == 404:
            return ""
        logs = ""

    if logs.strip():
        return logs

    try:
        return _read_pod_log_raw(api, name=pod_name, namespace=namespace, tail_lines=tail_lines, previous=True)
    except ApiException:
        return logs  # whatever we had, even if empty -- never raise for "no logs yet"


def stream_pod_logs(namespace: str, pod_name: str, tail_lines: int = 10):
    """Read-only. Live-follows a pod's logs (like `kubectl logs -f`), yielding
    one decoded line at a time as they arrive. Sprint-2 Kubernetes Depth
    (PRASH_V2.md §7b).

    A generator, not a one-shot read like get_pod_logs() above -- the
    caller drives how long to keep iterating (the CLI breaks on Ctrl+C).
    Uses `_preload_content=False` so the underlying urllib3 response is
    streamed rather than buffered whole, which is the whole point of
    "live" here. `resp.release_conn()` in `finally` matters: without it,
    breaking out of iteration early (e.g. Ctrl+C) leaks the connection.
    """
    namespace = _default_namespace(namespace)
    api = _client()
    resp = api.read_namespaced_pod_log(
        name=pod_name, namespace=namespace, follow=True, tail_lines=tail_lines, _preload_content=False
    )
    try:
        for raw_line in resp:
            yield raw_line.decode("utf-8", errors="replace").rstrip("\n")
    finally:
        resp.release_conn()


def get_pod_events(namespace: str, pod_name: str) -> list[dict]:
    """Read-only. Kubernetes Events involving this pod, most recent first.

    Events are where the real story usually is for ImagePullBackOff /
    scheduling failures -- logs alone often won't show why a pod never
    started.
    """
    namespace = _default_namespace(namespace)
    api = _client()
    try:
        events = api.list_namespaced_event(
            namespace=namespace,
            field_selector=f"involvedObject.name={pod_name}",
        ).items
    except ApiException as exc:
        if exc.status == 404:
            return []
        raise

    events.sort(key=lambda e: e.last_timestamp or e.event_time or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return [
        {
            "type": e.type,
            "reason": e.reason,
            "message": e.message,
            "count": e.count,
            "last_timestamp": (e.last_timestamp or e.event_time).isoformat() if (e.last_timestamp or e.event_time) else None,
        }
        for e in events
    ]


def restart_pod(namespace: str, pod_name: str) -> bool:
    """WRITE. Safe-tier action per PRASH_V2.md §5 -- Track C's
    RestartPodAction wires the permission check; this function assumes
    it has already been granted and just does the deletion (the
    Deployment/ReplicaSet recreates it).

    Returns True if the delete succeeded. Track C is responsible for
    the post-action verification step (§3) -- re-checking the pod here
    is NOT this function's job, keep it a single clear action.

    Honest caveat, worth stating plainly: deleting a pod whose
    *application* is broken will just recreate the same broken pod
    under a new name. Restart fixes stuck/wedged processes; it cannot
    fix a genuinely broken container image or command. Track D's
    diagnosis is what tells a user which case they're in.
    """
    namespace = _default_namespace(namespace)
    api = _client()
    try:
        api.delete_namespaced_pod(name=pod_name, namespace=namespace)
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        raise


def get_previous_revision(namespace: str, deployment_name: str) -> dict | None:
    """Read-only. The last known-good revision for a Deployment, from the
    ReplicaSet revision history Kubernetes already keeps -- no separate
    state store. See PRASH_V2.md §6, cross-track dependency #2.

    Returns {"revision": <int>} matching what Track C's rollback action
    expects (`previous.get("revision")`), or None if there's no prior
    revision to roll back to.

    Real mechanics: a Deployment's revision history is tracked via each
    ReplicaSet's `deployment.kubernetes.io/revision` annotation, not on
    the Deployment object itself. This lists the Deployment's owned
    ReplicaSets and returns the second-highest revision number (the
    highest is the current one).
    """
    namespace = _default_namespace(namespace)
    api = _client()
    apps_api = client.AppsV1Api(api.api_client)
    try:
        rs_list = apps_api.list_namespaced_replica_set(namespace=namespace).items
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise

    revisions = []
    for rs in rs_list:
        owners = rs.metadata.owner_references or []
        if not any(o.kind == "Deployment" and o.name == deployment_name for o in owners):
            continue
        rev_str = (rs.metadata.annotations or {}).get("deployment.kubernetes.io/revision")
        if rev_str is not None:
            revisions.append(int(rev_str))

    if len(revisions) < 2:
        return None

    revisions.sort(reverse=True)
    return {"revision": revisions[1]}


def scale_deployment(namespace: str, deployment_name: str, replicas: int) -> bool:
    """WRITE. Sprint-2 Kubernetes Depth (PRASH_V2.md §7b) -- Track C's
    ScaleAction wires the permission check; this function assumes it has
    already been granted and just patches the replica count.

    Returns True if the patch succeeded, False if the Deployment doesn't
    exist. Track C is responsible for post-action verification (§3), same
    split as restart_pod() above -- keep this a single clear write.
    """
    namespace = _default_namespace(namespace)
    api = _client()
    apps_api = client.AppsV1Api(api.api_client)
    try:
        apps_api.patch_namespaced_deployment_scale(
            name=deployment_name, namespace=namespace, body={"spec": {"replicas": replicas}}
        )
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        raise


def get_deployment_replicas(namespace: str, deployment_name: str) -> int | None:
    """Read-only. Current replica count for verify() after a scale action.
    Returns None if the Deployment doesn't exist."""
    namespace = _default_namespace(namespace)
    api = _client()
    apps_api = client.AppsV1Api(api.api_client)
    try:
        deployment = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise
    return deployment.spec.replicas
