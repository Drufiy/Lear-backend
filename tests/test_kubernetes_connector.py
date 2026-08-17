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


def test_not_ready_with_restarts_and_no_waiting_reason_is_still_crash_loop(monkeypatch):
    """Real CI failure caught live (2026-08-09): a genuinely crash-looping
    pod polled mid-restart-attempt, when container_statuses.waiting is
    transiently empty (the split-second between a backoff wait ending and
    the actual restart attempt), came back problem=None entirely -- not
    even the StuckPending fallback, since a young pod (few restarts) hasn't
    hit the 120s age threshold yet. restart_count > 0 is itself sufficient
    independent evidence this is CrashLoopBackOff, regardless of what the
    current instantaneous waiting.reason snapshot says.
    """
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod.return_value = _pod(
        phase="Running",
        # No waiting/terminated reason set at all -- exactly the mid-restart
        # snapshot that caused the real CI failure.
        container_statuses=[_container_status(ready=False, restart_count=3)],
    )

    result = k8s.get_pod_status("prash-demo", "broken-app-abc")

    assert result[0].problem == "CrashLoopBackOff"


def test_not_ready_with_zero_restarts_and_no_waiting_reason_stays_unclassified(monkeypatch):
    """The restart_count>0 fallback must not fire for a pod that's simply
    still starting up for the first time (0 restarts) -- that's normal
    startup latency, not evidence of crash-looping. Age-gated StuckPending
    (tested separately) is what should eventually catch a pod stuck like
    this for too long, not an immediate CrashLoopBackOff label."""
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod.return_value = _pod(
        phase="Running",
        container_statuses=[_container_status(ready=False, restart_count=0)],
    )

    result = k8s.get_pod_status("prash-demo", "broken-app-abc")

    assert result[0].problem is None


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
# _preload_content=False (added 2026-08-17, see _read_pod_log_raw's docstring
# for the real bug this fixed) means read_namespaced_pod_log returns a
# response-like object with .data (bytes) + .release_conn(), not a plain str
# -- these mocks reflect the real client shape, not a plain string.

def _fake_log_response(text: str):
    return type("FakeLogResponse", (), {"data": text.encode(), "release_conn": lambda self: None})()


def test_logs_falls_back_to_previous_when_current_is_empty(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod_log.side_effect = [
        _fake_log_response(""),
        _fake_log_response("simulated failure: config file missing\n"),
    ]

    result = k8s.get_pod_logs("prash-demo", "broken-app-abc")

    assert result == "simulated failure: config file missing\n"
    assert fake_api.read_namespaced_pod_log.call_count == 2
    _, second_call_kwargs = fake_api.read_namespaced_pod_log.call_args_list[1]
    assert second_call_kwargs["previous"] is True


def test_logs_returns_current_without_fallback_when_present(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod_log.return_value = _fake_log_response("app started ok\n")

    result = k8s.get_pod_logs("prash-demo", "healthy-pod")

    assert result == "app started ok\n"
    assert fake_api.read_namespaced_pod_log.call_count == 1


def test_logs_returns_empty_string_not_raise_when_pod_not_found(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod_log.side_effect = ApiException(status=404)

    result = k8s.get_pod_logs("prash-demo", "does-not-exist")

    assert result == ""


def test_logs_are_real_decoded_text_not_a_stringified_bytes_wrapper(monkeypatch):
    """Regression test for the real bug found live 2026-08-17 building
    `prash logs`: without _preload_content=False, this kubernetes client
    version (36.0.3) silently returned the log text wrapped as the literal
    characters "b'...'" instead of decoded text -- a valid non-empty string,
    so nothing else here caught it. Confirmed live against a real pod before
    this test was written; asserting the shape here so it can't regress."""
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_pod_log.return_value = _fake_log_response("real log line\n")

    result = k8s.get_pod_logs("prash-demo", "any-pod")

    assert result == "real log line\n"
    assert not result.startswith("b'")
    _, call_kwargs = fake_api.read_namespaced_pod_log.call_args
    assert call_kwargs["_preload_content"] is False


# ── stream_pod_logs: live-follow, sprint-2 Kubernetes Depth (2026-08-17) ────

def _fake_streaming_response(lines: list[str]):
    released = {"value": False}
    resp = type(
        "FakeStreamingResponse",
        (),
        {
            "__iter__": lambda self: iter(line.encode() for line in lines),
            "release_conn": lambda self: released.__setitem__("value", True),
        },
    )()
    return resp, released


def test_stream_pod_logs_yields_decoded_lines_and_follows(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    resp, released = _fake_streaming_response(["line one\n", "line two\n"])
    fake_api.read_namespaced_pod_log.return_value = resp

    result = list(k8s.stream_pod_logs("prash-demo", "api", tail_lines=10))

    assert result == ["line one", "line two"]
    assert released["value"] is True
    _, call_kwargs = fake_api.read_namespaced_pod_log.call_args
    assert call_kwargs["follow"] is True
    assert call_kwargs["_preload_content"] is False


def test_stream_pod_logs_releases_connection_on_early_break(monkeypatch):
    """Breaking out of iteration early (e.g. Ctrl+C in the CLI) must not
    leak the underlying connection -- the finally: release_conn() is the
    whole point of testing this separately from the happy path above."""
    fake_api = _patched_core_api(monkeypatch)
    resp, released = _fake_streaming_response(["line one\n", "line two\n", "line three\n"])
    fake_api.read_namespaced_pod_log.return_value = resp

    gen = k8s.stream_pod_logs("prash-demo", "api", tail_lines=10)
    assert next(gen) == "line one"
    gen.close()

    assert released["value"] is True


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


# ── get_configmap / update_configmap: sprint-2 Kubernetes Depth (2026-08-17) ─

def test_get_configmap_returns_data(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_config_map.return_value = SimpleNamespace(data={"LOG_LEVEL": "info"})

    result = k8s.get_configmap("prash-demo", "app-config")

    assert result == {"LOG_LEVEL": "info"}


def test_get_configmap_returns_none_when_not_found(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_config_map.side_effect = ApiException(status=404)

    result = k8s.get_configmap("prash-demo", "does-not-exist")

    assert result is None


def test_update_configmap_merge_patches_only_the_given_keys(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.patch_namespaced_config_map.return_value = None

    result = k8s.update_configmap("prash-demo", "app-config", {"LOG_LEVEL": "debug"})

    assert result is True
    _, call_kwargs = fake_api.patch_namespaced_config_map.call_args
    assert call_kwargs["body"] == {"data": {"LOG_LEVEL": "debug"}}


def test_update_configmap_returns_false_when_not_found(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.patch_namespaced_config_map.side_effect = ApiException(status=404)

    result = k8s.update_configmap("prash-demo", "does-not-exist", {"K": "V"})

    assert result is False


# ── get_secret_keys / update_secret: never decode/hold plaintext values ────

def test_get_secret_keys_returns_only_key_names_not_values(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_secret.return_value = SimpleNamespace(
        data={"PASSWORD": "czNjcjN0", "USERNAME": "YWRtaW4="}
    )

    result = k8s.get_secret_keys("prash-demo", "db-creds")

    assert result == ["PASSWORD", "USERNAME"]
    assert "czNjcjN0" not in result
    assert "YWRtaW4=" not in result


def test_get_secret_keys_returns_none_when_not_found(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.read_namespaced_secret.side_effect = ApiException(status=404)

    result = k8s.get_secret_keys("prash-demo", "does-not-exist")

    assert result is None


def test_update_secret_uses_string_data_not_manual_base64(monkeypatch):
    """stringData lets the API server handle encoding server-side -- this
    connector must never base64-encode (or otherwise transform) a secret
    value itself, which is exactly what passing plain text via stringData
    guarantees."""
    fake_api = _patched_core_api(monkeypatch)
    fake_api.patch_namespaced_secret.return_value = None

    result = k8s.update_secret("prash-demo", "db-creds", {"PASSWORD": "plaintext-value"})

    assert result is True
    _, call_kwargs = fake_api.patch_namespaced_secret.call_args
    assert call_kwargs["body"] == {"stringData": {"PASSWORD": "plaintext-value"}}


def test_update_secret_returns_false_when_not_found(monkeypatch):
    fake_api = _patched_core_api(monkeypatch)
    fake_api.patch_namespaced_secret.side_effect = ApiException(status=404)

    result = k8s.update_secret("prash-demo", "does-not-exist", {"K": "V"})

    assert result is False
