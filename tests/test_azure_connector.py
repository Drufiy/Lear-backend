"""Azure connector unit tests.

PR #33 added AzureConnector with no test file at all (AWS got one, GCP already
had one). These cover the path that actually runs here: with the azure SDK
absent (`_HAS_AZURE` forced False) the connector shells out to the `az` CLI, so
we mock `subprocess.run` and exercise the auth gate, locate, and the
poll_state PowerState->ConnectorState mapping. Also pins that execute-azure is
registered in the dispatcher (PR #33 claimed it was "wired" but it wasn't).
"""

from __future__ import annotations

import subprocess

import pytest

import prash.connectors.azure as azure_mod
from prash.connectors.azure import AzureConnector
from prash.connectors.base import ConnectorState


def _creds(**over):
    base = {
        "AZURE_SUBSCRIPTION_ID": "sub-123",
        "AZURE_TENANT_ID": "",
        "AZURE_CLIENT_ID": "",
        "AZURE_CLIENT_SECRET": "",
    }
    base.update(over)
    return base


def _completed(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


@pytest.fixture(autouse=True)
def _force_cli_path(monkeypatch):
    """Force the CLI fallback so tests are deterministic whether or not the
    azure SDK happens to be installed in the environment."""
    monkeypatch.setattr("prash.connectors.azure._HAS_AZURE", False)


def _patch_az(monkeypatch, *, account_ok=True, rg="my-rg", vm_json=None):
    calls = []

    def fake_run(cmd, capture_output=True, text=True, check=True):
        calls.append(cmd)
        if "account" in cmd:  # az account show
            if account_ok:
                return _completed(stdout='{"id": "sub-123", "name": "Production"}')
            raise subprocess.CalledProcessError(1, cmd)
        if cmd[:3] == ["az", "vm", "list"]:
            return _completed(stdout=rg)
        if cmd[:3] == ["az", "vm", "show"]:
            return _completed(stdout=vm_json or "{}")
        return _completed()

    monkeypatch.setattr("prash.connectors.azure.subprocess.run", fake_run)
    return calls


def test_authenticate_requires_subscription():
    assert AzureConnector({}).authenticate() is False


def test_authenticate_via_cli(monkeypatch):
    _patch_az(monkeypatch, account_ok=True)
    connector = AzureConnector(_creds())
    assert connector.authenticate() is True
    assert connector.auth_identity == {"subscription": "Production"}
    assert connector.auth_error is None


def test_explicit_service_principal_failure_does_not_fall_back_to_cli(monkeypatch):
    monkeypatch.setattr(azure_mod.subprocess, "run", lambda *a, **k: pytest.fail("CLI fallback used"))
    monkeypatch.setattr(azure_mod, "_HAS_AZURE", True)
    monkeypatch.setattr(azure_mod, "ClientSecretCredential", lambda **kwargs: object(), raising=False)

    class BrokenCompute:
        def __init__(self, *args):
            raise RuntimeError("candidate rejected")

    monkeypatch.setattr(azure_mod, "ComputeManagementClient", BrokenCompute, raising=False)
    connector = AzureConnector(_creds(AZURE_TENANT_ID="tenant", AZURE_CLIENT_ID="client", AZURE_CLIENT_SECRET="bad"))
    assert connector.authenticate() is False
    assert "candidate rejected" in connector.auth_error


def test_authenticate_false_when_cli_missing(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("az not found")

    monkeypatch.setattr("prash.connectors.azure.subprocess.run", boom)
    assert AzureConnector(_creds()).authenticate() is False


def test_locate_via_cli(monkeypatch):
    vm_json = '{"name": "web-vm", "rg": "my-rg", "loc": "eastus", "size": "Standard_B1s", "state": "VM running"}'
    _patch_az(monkeypatch, rg="my-rg", vm_json=vm_json)
    handle = AzureConnector(_creds()).locate("web-vm")
    assert handle["vm_name"] == "web-vm"
    assert handle["resource_group"] == "my-rg"
    assert handle["state"] == "running"  # "VM running" -> "running"


def test_locate_returns_empty_when_no_resource_group(monkeypatch):
    _patch_az(monkeypatch, rg="")  # vm list finds no RG
    assert AzureConnector(_creds()).locate("ghost-vm") == {}


def test_poll_state_running_is_healthy(monkeypatch):
    vm_json = '{"name": "web-vm", "rg": "my-rg", "loc": "eastus", "size": "Standard_B1s", "state": "VM running"}'
    _patch_az(monkeypatch, vm_json=vm_json)
    state = AzureConnector(_creds()).poll_state("web-vm")
    assert state.state is ConnectorState.HEALTHY


def test_poll_state_deallocated_is_stable(monkeypatch):
    vm_json = '{"name": "web-vm", "rg": "my-rg", "loc": "eastus", "size": "Standard_B1s", "state": "VM deallocated"}'
    _patch_az(monkeypatch, vm_json=vm_json)
    state = AzureConnector(_creds()).poll_state("web-vm")
    assert state.state is ConnectorState.STABLE


def test_poll_state_not_found_when_vm_missing(monkeypatch):
    _patch_az(monkeypatch, rg="")  # locate returns {} -> NOT_FOUND
    state = AzureConnector(_creds()).poll_state("ghost-vm")
    assert state.state is ConnectorState.NOT_FOUND


def test_poll_state_unauthenticated_is_unknown():
    state = AzureConnector({}).poll_state("web-vm")
    assert state.state is ConnectorState.UNKNOWN
    assert state.detail.get("error") == "unauthenticated"


def test_execute_azure_action_registered():
    # PR #33 claimed execute-azure was "wired into the dispatcher"; it wasn't.
    from prash.cli import _build_dispatcher
    from prash.permissions import PermissionMode

    dispatcher = _build_dispatcher(PermissionMode.ASK)
    assert "execute-azure" in dispatcher.available
