"""Live-cluster tests for prash/connectors/kubernetes.py — the §6 sub-task
("Testing actions without a real cluster... Use kind... Owner: Aradhya,
alongside the day 1-2 connector") that got missed when the connector itself
shipped. tests/test_kubernetes_connector.py covers the classification logic
thoroughly with mocks; this file is the other half — proving the real
kubernetes-client wiring actually works against a real API server, which no
amount of mocking can guarantee (auth, RBAC, actual response shapes).

Skipped unless PRASH_LIVE_K8S_TESTS=1 is set, so this never accidentally
runs in the regular mocked test job or in local dev without a cluster.
CI sets it only in the dedicated k8s-live-tests job (ubuntu-latest only —
see .github/workflows/ci.yml for why macOS/Windows runners are excluded).

Requires prash/connectors/testdata/broken-pod.yaml already applied and the
pod already reached CrashLoopBackOff before this runs (the CI job handles
that; see its "wait for CrashLoopBackOff" step).
"""
from __future__ import annotations

import os
import time

import pytest

from prash.connectors.kubernetes import (
    get_pod_events,
    get_pod_logs,
    get_pod_status,
    get_previous_revision,
    restart_pod,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("PRASH_LIVE_K8S_TESTS") != "1",
    reason="live k8s tests only run with PRASH_LIVE_K8S_TESTS=1 against a real cluster (see CI's k8s-live-tests job)",
)

_NAMESPACE = "prash-demo"


def _find_broken_pod_name() -> str:
    pods = get_pod_status(_NAMESPACE)
    assert pods, f"expected at least one pod in {_NAMESPACE} — is broken-pod.yaml applied?"
    crash_looping = [p for p in pods if p.problem == "CrashLoopBackOff"]
    assert crash_looping, f"no CrashLoopBackOff pod found yet in {_NAMESPACE}; pods={pods}"
    return crash_looping[0].name


def test_get_pod_status_detects_real_crash_loop_via_list():
    pods = get_pod_status(_NAMESPACE)
    assert any(p.problem == "CrashLoopBackOff" for p in pods)


def test_get_pod_status_detects_real_crash_loop_via_name():
    name = _find_broken_pod_name()
    pods = get_pod_status(_NAMESPACE, name)
    assert len(pods) == 1
    assert pods[0].problem == "CrashLoopBackOff"
    assert pods[0].restart_count >= 1
    assert pods[0].ready is False


def test_get_pod_logs_falls_back_to_previous_attempt():
    """The exact behavior manually verified during development (PRASH_V2.md
    §10, 2026-08-09) -- locking it into CI instead of relying on that one-off
    manual check staying true forever."""
    name = _find_broken_pod_name()
    logs = get_pod_logs(_NAMESPACE, name)
    assert "simulated failure: config file missing" in logs


def test_get_pod_events_returns_real_events():
    name = _find_broken_pod_name()
    events = get_pod_events(_NAMESPACE, name)
    assert events, "expected at least one real k8s Event for the crash-looping pod"
    assert any("backoff" in (e.get("reason") or "").lower() for e in events)


def test_get_previous_revision_is_none_for_a_fresh_deployment():
    """broken-app has only ever had one revision -- confirms the connector
    correctly reports 'nothing to roll back to' against a real API server,
    not just the mocked ReplicaSet-list logic in the unit tests."""
    assert get_previous_revision(_NAMESPACE, "broken-app") is None


def test_restart_pod_actually_deletes_and_recreates():
    name = _find_broken_pod_name()
    assert restart_pod(_NAMESPACE, name) is True

    # Deletion is accepted synchronously by the API server, but the list
    # endpoint reflecting it can lag by a beat — short poll instead of a
    # bare assert to avoid CI flakiness on the exact propagation timing.
    names_after: set[str] = set()
    for _ in range(10):
        names_after = {p.name for p in get_pod_status(_NAMESPACE)}
        if name not in names_after:
            break
        time.sleep(1)
    assert name not in names_after, "the deleted pod name should be gone — Deployment recreates under a new name"
    assert names_after, "Deployment should have recreated a replacement pod"


def test_restart_pod_returns_false_for_a_pod_that_does_not_exist():
    assert restart_pod(_NAMESPACE, "definitely-not-a-real-pod-name") is False
