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
from typing import Iterator

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

# Import the base interfaces for the new Connector pattern
from prash.connectors.base import Connector, ResourceState, ConnectorState, ConnectorEvent


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
    """Derive (problem, restart_count, ready) from a pod's real status."""
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


# --- PHASE A & B & C: THE NEW CONNECTOR CLASS ---

class KubernetesConnector(Connector):
    def __init__(self, credentials: dict | None = None):
        self.read_capabilities = ("pod_status", "logs", "events", "watch", "stats")
        self.write_capabilities = ("restart", "rollback", "scale")
        self.api_client = None
        self.core_v1 = None
        self.apps_v1 = None
        self.credentials = credentials or {}

    def authenticate(self, credentials=None):
        if credentials:
            self.credentials.update(credentials)
            
        kubeconfig = self.credentials.get("KUBECONFIG") or os.environ.get("KUBECONFIG")
        context = self.credentials.get("KUBE_CONTEXT") or os.environ.get("KUBE_CONTEXT") or None
        
        config.load_kube_config(config_file=kubeconfig, context=context)
        self.api_client = client.ApiClient()
        self.core_v1 = client.CoreV1Api(self.api_client)
        self.apps_v1 = client.AppsV1Api(self.api_client)

    def locate(self, resource: str) -> dict:
        env_namespace = self.credentials.get("KUBE_NAMESPACE") or _default_namespace(None)
        if "/" in resource:
            ns, name = resource.split("/", 1)
            return {"namespace": ns or env_namespace, "name": name}
        return {"namespace": env_namespace, "name": resource}

    def poll_state(self, resource: str) -> ResourceState:
        # Reuses the legacy wrapper to ensure perfect behavior matching
        target = self.locate(resource)
        pods = get_pod_status(target["namespace"], target["name"])
        
        if not pods:
            return ResourceState(status=ConnectorState.UNKNOWN, raw_data=None)
            
        p = pods[0]
        
        mapping = {
            "CrashLoopBackOff": ConnectorState.CRASH_LOOPING,
            "OOMKilled": ConnectorState.FAILED,
            "ImagePullBackOff": ConnectorState.FAILED,
            "StuckPending": ConnectorState.DEGRADED,
        }
        
        status = mapping.get(p.problem, ConnectorState.UNKNOWN)
        if p.problem is None and p.phase == "Running" and p.ready:
            status = ConnectorState.HEALTHY
            
        return ResourceState(status=status, raw_data=p.__dict__)

    def fetch_logs(self, resource: str) -> list[str]:
        target = self.locate(resource)
        logs = get_pod_logs(target["namespace"], target["name"])
        return logs.splitlines()

    def watch(self, target: str) -> Iterator[ConnectorEvent]:
        if not self.core_v1:
            self.authenticate()
            
        target_info = self.locate(target)
        w = watch.Watch()
        
        kwargs = {"namespace": target_info["namespace"]}
        name = target_info["name"]
        
        # Support namespace-wide if name is empty or wildcard
        if name and name != "*":
            kwargs["field_selector"] = f"metadata.name={name}"
            
        stream = w.stream(self.core_v1.list_namespaced_pod, **kwargs)
        
        for event in stream:
            pod = event['object']
            problem, restart_count, ready = _classify(pod)
            
            if problem in ["CrashLoopBackOff", "OOMKilled", "ImagePullBackOff", "StuckPending"]:
                yield ConnectorEvent(
                    timestamp=datetime.now(timezone.utc),
                    connector="kubernetes",
                    event_type=problem.lower(),
                    summary=f"Pod '{pod.metadata.name}' {problem} (restart_count={restart_count}) in namespace '{pod.metadata.namespace}'",
                    raw=pod.to_dict()
                )

    def get_stats(self, target: str, since: datetime) -> list[ConnectorEvent]:
        if not self.core_v1:
            self.authenticate()
            
        target_info = self.locate(target)
        
        kwargs = {"namespace": target_info["namespace"]}
        name = target_info["name"]
        if name and name != "*":
            kwargs["field_selector"] = f"involvedObject.name={name}"
            
        try:
            events = self.core_v1.list_namespaced_event(**kwargs).items
        except ApiException as exc:
            if exc.status == 404:
                return []
            raise
            
        normalized = []
        for e in events:
            ts = e.last_timestamp or e.event_time
            if not ts:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
                
            if ts >= since:
                normalized.append(
                    ConnectorEvent(
                        timestamp=ts,
                        connector="kubernetes",
                        event_type=e.reason or "unknown",
                        summary=f"{e.reason}: {e.message}",
                        raw=e.to_dict()
                    )
                )
        return sorted(normalized, key=lambda x: x.timestamp)


# --- BACKWARD COMPATIBILITY WRAPPERS ---

_global_k8s_connector = KubernetesConnector()

def _client() -> client.CoreV1Api:
    """Lazy singleton so tests can monkeypatch this module's _core_api
    directly instead of every function reaching into the kubernetes lib.
    """
    global _core_api
    if _core_api is not None:
        return _core_api

    _global_k8s_connector.authenticate()
    _core_api = _global_k8s_connector.core_v1
    return _core_api


def get_pod_status(namespace: str, pod_name: str | None = None) -> list[PodStatus]:
    """Read-only. All pods in `namespace`, or just `pod_name` if given."""
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
    resp = api.read_namespaced_pod_log(
        name=name, namespace=namespace, tail_lines=tail_lines, previous=previous, _preload_content=False
    )
    try:
        return resp.data.decode("utf-8", errors="replace")
    finally:
        resp.release_conn()


def get_pod_logs(namespace: str, pod_name: str, tail_lines: int = 500) -> str:
    """Read-only. Recent logs for a pod."""
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
    """Read-only. Live-follows a pod's logs."""
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
    """Read-only. Kubernetes Events involving this pod, most recent first."""
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
    """WRITE. Safe-tier action per PRASH_V2.md §5"""
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
    """Read-only. The last known-good revision for a Deployment."""
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
    """WRITE. Sprint-2 Kubernetes Depth (PRASH_V2.md §7b)."""
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
    """Read-only. Current replica count for verify() after a scale action."""
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


def get_configmap(namespace: str, name: str) -> dict[str, str] | None:
    """Read-only. Sprint-2 Kubernetes Depth (PRASH_V2.md §7b)."""
    namespace = _default_namespace(namespace)
    api = _client()
    try:
        cm = api.read_namespaced_config_map(name=name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise
    return dict(cm.data or {})


def update_configmap(namespace: str, name: str, data: dict[str, str]) -> bool:
    """WRITE. Merge-patches the given keys into an existing ConfigMap."""
    namespace = _default_namespace(namespace)
    api = _client()
    try:
        api.patch_namespaced_config_map(name=name, namespace=namespace, body={"data": data})
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        raise


def get_secret_keys(namespace: str, name: str) -> list[str] | None:
    """Read-only. Sprint-2 Kubernetes Depth (PRASH_V2.md §7b)."""
    namespace = _default_namespace(namespace)
    api = _client()
    try:
        secret = api.read_namespaced_secret(name=name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise
    return sorted((secret.data or {}).keys())


def update_secret(namespace: str, name: str, data: dict[str, str]) -> bool:
    """WRITE. Merge-patches the given keys into an existing Secret."""
    namespace = _default_namespace(namespace)
    api = _client()
    try:
        api.patch_namespaced_secret(name=name, namespace=namespace, body={"stringData": data})
        return True
    except ApiException as exc:
        if exc.status == 404:
            return False
        raise


_EXEC_OUTPUT_CAP = 20_000


def exec_in_pod(
    namespace: str, pod_name: str, command: list[str], container: str | None = None, timeout: int = 30
) -> dict:
    """WRITE (arbitrary command execution). Sprint-2 Kubernetes Depth"""
    from kubernetes.stream import stream

    namespace = _default_namespace(namespace)
    api = _client()
    kwargs: dict = {"command": command, "stderr": True, "stdin": False, "stdout": True, "tty": False, "_preload_content": False}
    if container:
        kwargs["container"] = container
    resp = stream(api.connect_get_namespaced_pod_exec, pod_name, namespace, **kwargs)
    try:
        resp.run_forever(timeout=timeout)
        stdout = resp.read_stdout(timeout=5) or ""
        stderr = resp.read_stderr(timeout=5) or ""
        exit_code = resp.returncode
    finally:
        resp.close()

    return {
        "stdout": stdout[:_EXEC_OUTPUT_CAP],
        "stderr": stderr[:_EXEC_OUTPUT_CAP],
        "exit_code": exit_code if exit_code is not None else -1,
    }