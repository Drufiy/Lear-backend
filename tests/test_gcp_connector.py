"""GCP connector unit tests.

No real GCP access in CI (or on this machine): the connector's
`_HAS_GCP` API path needs the google libs, and the fallback shells out to
the `gcloud` CLI. These tests mock `subprocess.run` to exercise the
gcloud-fallback path (the one that runs here), plus the state mapping and
the auth gate. The API path (discovery.build) is covered structurally by
the same logic; a live run is tracked in TESTING_SETUP.md.
"""

from __future__ import annotations

import subprocess

from prash.connectors.base import ConnectorState
from prash.connectors.gcp import GCPConnector


def _creds(**over):
    base = {
        "GCP_PROJECT_ID": "my-gcp-project",
        "GCP_REGION": "us-central1",
        "GOOGLE_APPLICATION_CREDENTIALS": "",
    }
    base.update(over)
    return base


def _completed(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def _patch_gcloud(monkeypatch, outputs):
    """Route the connector's subprocess.run calls to scripted outputs keyed
    by which gcloud subcommand is being invoked."""
    calls = []

    def fake_run(cmd, capture_output=True, text=True, check=True, timeout=None):
        calls.append(cmd)
        # Find the subcommand: e.g. ["gcloud","compute","instances","list",...]
        sub = cmd[3] if len(cmd) > 3 else ""
        if sub in outputs:
            out = outputs[sub]
            if isinstance(out, Exception):
                raise out
            return _completed(stdout=out)
        return _completed()

    monkeypatch.setattr("prash.connectors.gcp.subprocess.run", fake_run)
    return calls


def test_authenticate_requires_project():
    conn = GCPConnector({})
    assert conn.authenticate() is False


def test_authenticate_true_with_project_and_gcloud(monkeypatch):
    monkeypatch.setattr(
        "prash.connectors.gcp.subprocess.run",
        lambda *a, **k: _completed(stdout="token"),
    )
    conn = GCPConnector(_creds())
    assert conn.authenticate() is True


def test_authenticate_false_when_gcloud_missing(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("gcloud not found")

    monkeypatch.setattr("prash.connectors.gcp.subprocess.run", boom)
    conn = GCPConnector(_creds())
    assert conn.authenticate() is False


def test_locate_via_gcloud(monkeypatch):
    _patch_gcloud(
        monkeypatch,
        {
            "list": "us-central1-a",
            "describe": '{"name": "prash-test-fixture", "zone": "projects/my-gcp-project/zones/us-central1-a", "machineType": "projects/my-gcp-project/zones/us-central1-a/machineTypes/e2-micro", "status": "RUNNING"}',
        },
    )
    conn = GCPConnector(_creds())
    handle = conn.locate("prash-test-fixture")
    assert handle["instance_name"] == "prash-test-fixture"
    assert handle["zone"] == "us-central1-a"
    assert handle["state"] == "RUNNING"


def test_locate_not_found_returns_empty(monkeypatch):
    _patch_gcloud(
        monkeypatch,
        {
            "list": "",  # no zone found -> locate returns {}
        },
    )
    conn = GCPConnector(_creds())
    assert conn.locate("missing-instance") == {}


def test_poll_state_running_is_healthy(monkeypatch):
    _patch_gcloud(
        monkeypatch,
        {
            "list": "us-central1-a",
            "describe": '{"name": "prash-test-fixture", "zone": "z/us-central1-a", "machineType": "m/e2-micro", "status": "RUNNING"}',
        },
    )
    conn = GCPConnector(_creds())
    state = conn.poll_state("prash-test-fixture")
    assert state.state is ConnectorState.HEALTHY


def test_poll_state_stopped_is_stable(monkeypatch):
    _patch_gcloud(
        monkeypatch,
        {
            "list": "us-central1-a",
            "describe": '{"name": "prash-test-fixture", "zone": "z/us-central1-a", "machineType": "m/e2-micro", "status": "STOPPED"}',
        },
    )
    conn = GCPConnector(_creds())
    state = conn.poll_state("prash-test-fixture")
    assert state.state is ConnectorState.STABLE


def test_poll_state_provisioning_is_deploying(monkeypatch):
    _patch_gcloud(
        monkeypatch,
        {
            "list": "us-central1-a",
            "describe": '{"name": "prash-test-fixture", "zone": "z/us-central1-a", "machineType": "m/e2-micro", "status": "PROVISIONING"}',
        },
    )
    conn = GCPConnector(_creds())
    state = conn.poll_state("prash-test-fixture")
    assert state.state is ConnectorState.DEPLOYING


def test_poll_state_not_found_when_unauthenticated():
    conn = GCPConnector({})
    state = conn.poll_state("anything")
    assert state.state is ConnectorState.UNKNOWN
    assert state.detail.get("error") == "unauthenticated"


def test_fetch_logs_uses_serial_port_output(monkeypatch):
    calls = _patch_gcloud(
        monkeypatch,
        {
            "list": "us-central1-a",
            "get-serial-port-output": "booting...\nkernel panic!",
        },
    )
    conn = GCPConnector(_creds())
    logs = conn.fetch_logs("prash-test-fixture")
    assert logs == ["booting...", "kernel panic!"]
    # The call must carry the zone and project
    serial_calls = [c for c in calls if len(c) > 3 and c[3] == "get-serial-port-output"]
    assert serial_calls and "--zone" in serial_calls[0]
