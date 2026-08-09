"""Track B: the Kubernetes connector (prash/connectors/kubernetes.py).

Unit-level: the real kubernetes.client.CoreV1Api/AppsV1Api are mocked so
these run anywhere, no cluster needed -- CI included. The connector was
separately verified against a real live kind cluster and a genuine
CrashLoopBackOff pod during development (see PRASH_V2.md, 2026-08-09);
these tests lock in that verified behaviour so it can't silently regress.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from kubernetes.client.rest import ApiException

from prash.connectors import kubernetes as k8s


@pytest.fixture(autouse=True)
def _reset_client_singleton():
    """The module caches a CoreV1Api singleton; make sure each test gets
    a clean patch instead of leaking the previous test's mock.
    """
    k8s._core_api = None
    yield
    k8s._core_api = None


def _container_status(name="app", ready=True, restart_count=0, waiting_reason=None, terminated_reason=None, last_terminated_reason=None):
    waiting = SimpleNamespace(reason=waiting_reason) if waiting_reason else None
    terminated = SimpleNamespace(reason=terminated_reason) if terminated_reason else None
    last_terminated = SimpleNamespace(reason=last_terminated_reason) if last_terminated_reason else None
    return SimpleNamespace(
        name=name,
        ready=ready,
        restart_count=restart_count,
        state=SimpleNamespace(waiting=waiting, terminated=terminated),
        last_state=SimpleNamespace(terminated=last_terminated),
    )


def _pod(name="broken-app-abc", namespace="prash-demo", phase="Running", container_statuses=None, start_time=None):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace=namespace, creation_timestamp=start_time),
        status=SimpleNamespace(phase=phase, container_statuses=container_statuses or [], start_time=start_time),
    )


def _patched_core_api(monkeypatch):
    fake_api = MagicMock()
    monkeypatch.setattr(k8s, "_client", lambda: fake_api)
    return fake_api


# ── get_pod_status: the four states Track D + Track E both key off ─────────

def test_crash_loop_back_off_detected(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod.return_value = _pod(
        container_statuses=[_container_status(ready=False, restart_count=18, waiting_reason="CrashLoopBackOff")]
    )

    result = k8s.get_pod_status("prash-demo", "broken-app-abc")

    assert len(result) == 1
    assert result[0].problem == "CrashLoopBackOff"
    assert result[0].restart_count == 18
    assert result[0].ready is False


def test_image_pull_back_off_detected(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod.return_value = _pod(
        phase="Pending",
        container_statuses=[_container_status(ready=False, waiting_reason="ImagePullBackOff")],
    )

    result = k8s.get_pod_status("prash-demo", "broken-app-abc")

    assert result[0].problem == "ImagePullBackOff"


def test_err_image_pull_maps_to_image_pull_back_off(monkeypatch):
    """ErrImagePull is the transient state before it settles into
    ImagePullBackOff -- both must map to the same category the watcher
    and brain share (PRASH_V2.md §8), not two different unhandled states.
    """
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod.return_value = _pod(
        phase="Pending",
        container_statuses=[_container_status(ready=False, waiting_reason="ErrImagePull")],
    )

    result = k8s.get_pod_status("prash-demo", "broken-app-abc")

    assert result[0].problem == "ImagePullBackOff"


def test_oom_killed_detected_from_last_state(monkeypatch):
    """The common real shape: container restarted after OOM, so the OOM
    reason lives in last_state.terminated, not current state.
    """
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod.return_value = _pod(
        container_statuses=[_container_status(ready=True, restart_count=1, last_terminated_reason="OOMKilled")]
    )

    result = k8s.get_pod_status("prash-demo", "broken-app-abc")

    assert result[0].problem == "OOMKilled"


def test_stuck_pending_after_threshold(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    old_start = datetime.now(timezone.utc) - timedelta(seconds=k8s._STUCK_THRESHOLD_SECONDS + 30)
    fake_api.read_namespaced_pod.return_value = _pod(phase="Pending", start_time=old_start)

    result = k8s.get_pod_status("prash-demo", "broken-app-abc")

    assert result[0].problem == "StuckPending"


def test_recently_pending_is_not_yet_stuck(monkeypatch):
    """A pod Pending for 10 seconds is normal scheduling latency, not a
    problem -- must not false-positive during ordinary startup.
    """
    fake_api = _patched_core_api(monkeypatch)
    recent_start = datetime.now(timezone.utc) - timedelta(seconds=10)
    fake_api.read_namespaced_pod.return_value = _pod(phase="Pending", start_time=recent_start)

    result = k8s.get_pod_status("prash-demo", "broken-app-abc")

    assert result[0].problem is None


def test_healthy_pod_has_no_problem(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod.return_value = _pod(
        container_statuses=[_container_status(ready=True, restart_count=0)]
    )

    result = k8s.get_pod_status("prash-demo", "broken-app-abc")

    assert result[0].problem is None
    assert result[0].ready is True


def test_multi_container_pod_flags_the_broken_one(monkeypatch):
    """A healthy sidecar must not mask a crash-looping main container."""
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod.return_value = _pod(
        container_statuses=[
            _container_status(name="sidecar", ready=True, restart_count=0),
            _container_status(name="main", ready=False, restart_count=9, waiting_reason="CrashLoopBackOff"),
        ]
    )

    result = k8s.get_pod_status("prash-demo", "broken-app-abc")

    assert result[0].problem == "CrashLoopBackOff"
    assert result[0].ready is False  # not all containers ready


def test_pod_not_found_returns_empty_list_not_raise(monkeypatch):
    """Track C's restart-pod verify() step relies on this: an empty list
    is its 'pod missing' signal, so this must never raise for 404.
    """
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod.side_effect = ApiException(status=404)

    result = k8s.get_pod_status("prash-demo", "does-not-exist")

    assert result == []


def test_list_all_pods_in_namespace_when_no_name_given(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.list_namespaced_pod.return_value = SimpleNamespace(
        items=[_pod(name="a"), _pod(name="b")]
    )

    result = k8s.get_pod_status("prash-demo")

    assert [p.name for p in result] == ["a", "b"]


# ── get_pod_logs: the previous-attempt fallback, verified live 2026-08-09 ──

def test_logs_falls_back_to_previous_when_current_is_empty(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod_log.side_effect = ["", "simulated failure: config file missing\n"]

    result = k8s.get_pod_logs("prash-demo", "broken-app-abc")

    assert result == "simulated failure: config file missing\n"
    assert fake_api.read_namespaced_pod_log.call_count == 2
    _, second_call_kwargs = fake_api.read_namespaced_pod_log.call_args_list[1]
    assert second_call_kwargs["previous"] is True


def test_logs_returns_current_without_fallback_when_present(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod_log.return_value = "app started ok\n"

    result = k8s.get_pod_logs("prash-demo", "healthy-pod")

    assert result == "app started ok\n"
    assert fake_api.read_namespaced_pod_log.call_count == 1


def test_logs_returns_empty_string_not_raise_when_pod_not_found(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod_log.side_effect = ApiException(status=404)

    result = k8s.get_pod_logs("prash-demo", "does-not-exist")

    assert result == ""


# ── get_pod_events ──────────────────────────────────────────────────────────

def test_events_sorted_most_recent_first(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    older = SimpleNamespace(
        type="Normal", reason="Pulling", message="Pulling image", count=1,
        last_timestamp=datetime(2026, 8, 9, 12, 31, 0, tzinfo=timezone.utc), event_time=None,
    )
    newer = SimpleNamespace(
        type="Warning", reason="BackOff", message="Back-off restarting", count=5,
        last_timestamp=datetime(2026, 8, 9, 12, 33, 0, tzinfo=timezone.utc), event_time=None,
    )
    fake_api.list_namespaced_event.return_value = SimpleNamespace(items=[older, newer])

    result = k8s.get_pod_events("prash-demo", "broken-app-abc")

    assert [e["reason"] for e in result] == ["BackOff", "Pulling"]


def test_events_empty_list_when_none_found(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.list_namespaced_event.return_value = SimpleNamespace(items=[])

    result = k8s.get_pod_events("prash-demo", "broken-app-abc")

    assert result == []


# ── restart_pod ──────────────────────────────────────────────────────────────

def test_restart_pod_deletes_and_returns_true(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)

    ok = k8s.restart_pod("prash-demo", "broken-app-abc")

    assert ok is True
    fake_api.delete_namespaced_pod.assert_called_once_with(name="broken-app-abc", namespace="prash-demo")


def test_restart_pod_returns_false_when_not_found(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.delete_namespaced_pod.side_effect = ApiException(status=404)

    ok = k8s.restart_pod("prash-demo", "does-not-exist")

    assert ok is False


# ── get_previous_revision: powers Track C's rollback, no separate store ────

def test_previous_revision_found_when_two_exist(monkeypatch):
    _patched_core_api(monkeypatch)
    monkeypatch.setattr(k8s.client, "AppsV1Api", lambda api_client: MagicMock(
        list_namespaced_replica_set=MagicMock(return_value=SimpleNamespace(items=[
            SimpleNamespace(
                metadata=SimpleNamespace(
                    owner_references=[SimpleNamespace(kind="Deployment", name="broken-app")],
                    annotations={"deployment.kubernetes.io/revision": "1"},
                )
            ),
            SimpleNamespace(
                metadata=SimpleNamespace(
                    owner_references=[SimpleNamespace(kind="Deployment", name="broken-app")],
                    annotations={"deployment.kubernetes.io/revision": "2"},
                )
            ),
        ]))
    ))

    result = k8s.get_previous_revision("prash-demo", "broken-app")

    assert result == {"revision": 1}


def test_previous_revision_none_when_only_one_exists(monkeypatch):
    _patched_core_api(monkeypatch)
    monkeypatch.setattr(k8s.client, "AppsV1Api", lambda api_client: MagicMock(
        list_namespaced_replica_set=MagicMock(return_value=SimpleNamespace(items=[
            SimpleNamespace(
                metadata=SimpleNamespace(
                    owner_references=[SimpleNamespace(kind="Deployment", name="broken-app")],
                    annotations={"deployment.kubernetes.io/revision": "1"},
                )
            ),
        ]))
    ))

    result = k8s.get_previous_revision("prash-demo", "broken-app")

    assert result is None


def test_previous_revision_ignores_replicasets_from_other_deployments(monkeypatch):
    _patched_core_api(monkeypatch)
    monkeypatch.setattr(k8s.client, "AppsV1Api", lambda api_client: MagicMock(
        list_namespaced_replica_set=MagicMock(return_value=SimpleNamespace(items=[
            SimpleNamespace(
                metadata=SimpleNamespace(
                    owner_references=[SimpleNamespace(kind="Deployment", name="some-other-app")],
                    annotations={"deployment.kubernetes.io/revision": "7"},
                )
            ),
        ]))
    ))

    result = k8s.get_previous_revision("prash-demo", "broken-app")

    assert result is None
