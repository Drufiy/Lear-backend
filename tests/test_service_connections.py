import ast
import os
from unittest.mock import MagicMock

import dotenv
import pytest
from fastapi.testclient import TestClient

from prash.connector_registry import AuthField, CONNECTOR_REGISTRY, ConnectorRegistryEntry, clear_connector_cache
from prash.connectors.base import Connector, WatchHandle
from prash.server import _active_watches, _connection_states, _verify_persisted_connector, app


class DynamicConnector(Connector):
    calls = []
    result = True
    error = None
    identity = {}
    env_calls = []

    def __init__(self, credentials):
        super().__init__(credentials)
        type(self).calls.append(dict(credentials))
        self.auth_identity = dict(type(self).identity)
        self.auth_error = type(self).error

    def authenticate(self):
        type(self).env_calls.append({"token": os.environ.get("DYNAMIC_TOKEN"), "region": os.environ.get("DYNAMIC_REGION")})
        if isinstance(type(self).result, Exception):
            raise type(self).result
        return type(self).result

    def locate(self, resource):
        return {"id": resource}


@pytest.fixture
def service_client(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr("prash.server.ENV_PATH", str(env_path))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(env_path))
    entry = ConnectorRegistryEntry(
        id="dynamic",
        name="Dynamic Provider",
        category="monitoring",
        icon="box",
        color="#123456",
        connector_class_path=DynamicConnector,
        auth_fields=[
            AuthField("DYNAMIC_TOKEN", "Token", "password"),
            AuthField("DYNAMIC_REGION", "Region", "text", required=False, default="local"),
        ],
        widget_templates=[],
    )
    DynamicConnector.calls = []
    DynamicConnector.result = True
    DynamicConnector.error = None
    DynamicConnector.identity = {}
    DynamicConnector.env_calls = []
    clear_connector_cache()
    _active_watches.clear()
    _connection_states.clear()
    with pytest.MonkeyPatch.context() as registry_patch:
        registry_patch.setitem(CONNECTOR_REGISTRY, "dynamic", entry)
        with TestClient(app) as client:
            yield client, env_path
    clear_connector_cache()
    _active_watches.clear()
    _connection_states.clear()


def test_connect_uses_registry_class_authenticates_then_persists(service_client):
    client, env_path = service_client
    DynamicConnector.identity = {"account": "acct-42", "api_key": "must-not-leak"}

    response = client.post("/api/connectors/dynamic/connect", json={"DYNAMIC_TOKEN": "abcdefghi"})

    assert response.status_code == 200
    assert DynamicConnector.calls[-1]["DYNAMIC_TOKEN"] == "abcdefghi"
    assert dotenv.dotenv_values(env_path) == {"DYNAMIC_TOKEN": "abcdefghi", "DYNAMIC_REGION": "local"}
    body = response.json()
    assert body["status"] == "healthy"
    assert body["last_verified"]
    assert body["error"] is None
    # identity is a human-readable string built by _get_provider_identity
    # (per-connector-type: AWS account/region, GitHub owner, etc., falling
    # back to "{name} Verified" for a connector with no special case) --
    # NOT the connector's own raw auth_identity dict. Keeping the string
    # form was a deliberate choice: it's what the desktop UI displays, and
    # _get_provider_identity has real per-connector logic worth keeping
    # (see server.py's connection-state cache comment, 2026-09-14).
    assert body["identity"] == "Dynamic Provider Verified"
    assert "abcdefghi" not in response.text


def test_constructor_receives_only_selected_registry_fields(service_client):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=old-token\nOTHER_PROVIDER_SECRET=never-pass\nDESKTOP_THEME=dark\n", encoding="utf-8")

    response = client.post("/api/connectors/dynamic/connect", json={"DYNAMIC_TOKEN": "new-token"})

    assert response.status_code == 200
    assert DynamicConnector.calls[-1] == {"DYNAMIC_TOKEN": "new-token", "DYNAMIC_REGION": "local"}


def test_failed_update_preserves_existing_env_and_scrubs_error(service_client):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=old-token\nOTHER=value\n", encoding="utf-8")
    _connection_states["dynamic"] = {
        "status": "healthy",
        "last_verified": "2026-01-01T00:00:00+00:00",
        "error": None,
        "identity": {"account": "old"},
    }
    DynamicConnector.result = RuntimeError("provider rejected new-secret")

    response = client.post("/api/connectors/dynamic/connect", json={"DYNAMIC_TOKEN": "new-secret"})

    assert response.status_code == 401
    assert env_path.read_text(encoding="utf-8") == "DYNAMIC_TOKEN=old-token\nOTHER=value\n"
    assert "new-secret" not in response.text
    assert "[redacted]" in response.json()["message"]
    assert _connection_states["dynamic"] == {
        "status": "healthy",
        "last_verified": "2026-01-01T00:00:00+00:00",
        "error": None,
        "identity": {"account": "old"},
    }


def test_false_authentication_is_never_saved(service_client):
    client, env_path = service_client
    DynamicConnector.result = False
    DynamicConnector.error = "Provider says unauthorized"

    response = client.post("/api/connectors/dynamic/connect", json={"DYNAMIC_TOKEN": "bad-token"})

    assert response.status_code == 401
    assert not env_path.exists()
    assert response.json()["message"] == "Provider says unauthorized"


def test_update_can_reuse_unsubmitted_existing_fields(service_client):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=existing\nDYNAMIC_REGION=west\n", encoding="utf-8")

    response = client.post("/api/connectors/dynamic/connect", json={"DYNAMIC_TOKEN": "replacement"})

    assert response.status_code == 200
    assert DynamicConnector.calls[-1]["DYNAMIC_REGION"] == "west"
    assert dotenv.dotenv_values(env_path)["DYNAMIC_REGION"] == "west"


def test_update_can_explicitly_clear_optional_field(service_client):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=existing\nDYNAMIC_REGION=west\n", encoding="utf-8")

    response = client.post("/api/connectors/dynamic/connect", json={"DYNAMIC_REGION": ""})

    assert response.status_code == 200
    assert DynamicConnector.calls[-1] == {"DYNAMIC_TOKEN": "existing", "DYNAMIC_REGION": ""}
    assert dotenv.dotenv_values(env_path) == {"DYNAMIC_TOKEN": "existing"}


def test_unknown_fields_are_rejected_without_persistence(service_client):
    client, env_path = service_client

    response = client.post(
        "/api/connectors/dynamic/connect",
        json={"DYNAMIC_TOKEN": "valid-token", "UNREGISTERED_SECRET": "hidden"},
    )

    assert response.status_code == 400
    assert not env_path.exists()
    assert "hidden" not in response.text


def test_disconnect_removes_registry_fields_and_stops_watches(service_client):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=value\nDYNAMIC_REGION=west\nOTHER=keep\n", encoding="utf-8")
    handle = MagicMock(spec=WatchHandle)
    _active_watches["dynamic:one"] = handle
    _active_watches["other:two"] = MagicMock(spec=WatchHandle)

    response = client.delete("/api/connectors/dynamic/disconnect")

    assert response.status_code == 200
    assert response.json()["status"] == "unconfigured"
    assert dotenv.dotenv_values(env_path) == {"OTHER": "keep"}
    handle.stop.assert_called_once_with()
    assert "dynamic:one" not in _active_watches
    assert "other:two" in _active_watches


def test_manual_check_returns_status_metadata(service_client):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=value\n", encoding="utf-8")
    DynamicConnector.identity = {"username": "real-user"}

    response = client.post("/api/connectors/dynamic/check")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["last_verified"]
    assert response.json()["error"] is None
    # identity is the human-readable string from _get_provider_identity, not
    # the connector's raw auth_identity -- see the identical note on
    # test_connect_uses_registry_class_authenticates_then_persists.
    assert response.json()["identity"] == "Dynamic Provider Verified"


def test_health_check_marks_expired_and_does_not_retry_known_invalid(service_client):
    _, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=value\n", encoding="utf-8")
    DynamicConnector.result = False
    DynamicConnector.error = "revoked"

    first = _verify_persisted_connector("dynamic", automatic=True)
    second = _verify_persisted_connector("dynamic", automatic=True)

    assert first["status"] == "expired"
    assert first["error"] == "revoked"
    assert first["last_verified"] is None
    assert first["last_checked"]
    assert second == first
    assert len(DynamicConnector.calls) == 1


def test_persisted_health_constructor_receives_only_owned_fields(service_client):
    _, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=value\nOTHER_PROVIDER_SECRET=never-pass\n", encoding="utf-8")

    state = _verify_persisted_connector("dynamic")

    assert state["status"] == "healthy"
    assert DynamicConnector.calls[-1] == {"DYNAMIC_TOKEN": "value", "DYNAMIC_REGION": "local"}


def test_failed_check_preserves_last_successful_verification(service_client):
    _, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=value\n", encoding="utf-8")
    _connection_states["dynamic"] = {
        "status": "healthy",
        "last_verified": "2026-01-01T00:00:00+00:00",
        "last_checked": "2026-01-01T00:00:00+00:00",
        "error": None,
        "identity": {"account": "old"},
    }
    DynamicConnector.result = False
    DynamicConnector.error = "revoked"

    state = _verify_persisted_connector("dynamic")

    assert state["status"] == "expired"
    assert state["last_verified"] == "2026-01-01T00:00:00+00:00"
    assert state["last_checked"] != state["last_verified"]


def test_cached_healthy_state_is_invalidated_when_required_credentials_removed(service_client):
    client, env_path = service_client
    env_path.write_text("", encoding="utf-8")
    _connection_states["dynamic"] = {
        "status": "healthy",
        "last_verified": "2026-01-01T00:00:00+00:00",
        "last_checked": "2026-01-01T00:00:00+00:00",
        "error": None,
        "identity": {"account": "old"},
    }

    listed = next(item for item in client.get("/api/connectors").json()["connectors"] if item["id"] == "dynamic")

    assert listed["status"] == "unconfigured"
    assert listed["identity"] == ""


def test_status_does_not_reauthenticate(service_client):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=value\n", encoding="utf-8")
    _connection_states["dynamic"] = {
        "status": "expired",
        "last_verified": "2026-01-01T00:00:00+00:00",
        "error": "revoked",
        "identity": {},
    }

    response = client.get("/api/connectors/dynamic/status")

    assert response.json()["status"] == "expired"
    assert DynamicConnector.calls == []


def test_config_masks_first_three_and_last_three(service_client):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=abcdefghijk\n", encoding="utf-8")

    response = client.get("/api/config")

    assert response.json()["raw"]["DYNAMIC_TOKEN"] == "abc...ijk"
    assert "abcdefghijk" not in response.text


def test_config_masks_short_values_without_disclosure(service_client):
    client, env_path = service_client
    env_path.write_text("SHORT_SECRET=xy\n", encoding="utf-8")

    response = client.get("/api/config")

    # /api/config's own mask() uses a fixed-width bullet for short values
    # (<=6 chars) rather than length-revealing asterisks -- matches
    # test_desktop_api.py::test_CONFIG_MASKED_CREDENTIALS, the other
    # currently-relied-on caller of this same endpoint.
    assert response.json()["raw"]["SHORT_SECRET"] == "••••••••"
    assert "xy" not in response.text


def test_legacy_config_rejects_registry_credentials_but_keeps_desktop_settings(service_client):
    client, env_path = service_client

    rejected = client.post("/api/config", json={"DYNAMIC_TOKEN": "secret", "DESKTOP_THEME": "dark"})
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "CONNECTOR_AUTH_REQUIRED"
    assert "/connect" in rejected.json()["message"]
    assert not env_path.exists()

    accepted = client.post("/api/config", json={"DESKTOP_THEME": "dark"})
    assert accepted.status_code == 200
    assert dotenv.dotenv_values(env_path) == {"DESKTOP_THEME": "dark"}


def test_registry_responses_include_masked_auth_metadata(service_client):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=abcdefghijk\nDYNAMIC_REGION=xy\n", encoding="utf-8")

    list_body = client.get("/api/connectors").json()["connectors"]
    listed = next(item for item in list_body if item["id"] == "dynamic")
    detail = client.get("/api/connectors/dynamic").json()

    for body in (listed, detail):
        fields = {field["key"]: field for field in body["auth_fields"]}
        assert fields["DYNAMIC_TOKEN"]["configured"] is True
        assert fields["DYNAMIC_TOKEN"]["masked_value"] == "abc...ijk"
        assert fields["DYNAMIC_REGION"]["masked_value"] == "***"
        assert "abcdefghijk" not in str(body)
        assert "xy" not in str(body)


def test_candidate_environment_is_isolated_and_restored(service_client, monkeypatch):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=persisted-secret\nDYNAMIC_REGION=west\n", encoding="utf-8")
    monkeypatch.setenv("DYNAMIC_TOKEN", "stale-secret")
    monkeypatch.setenv("DYNAMIC_REGION", "stale-region")

    response = client.post("/api/connectors/dynamic/connect", json={"DYNAMIC_TOKEN": "candidate-secret"})

    assert response.status_code == 200
    assert DynamicConnector.env_calls[-1] == {"token": "candidate-secret", "region": "west"}
    assert os.environ["DYNAMIC_TOKEN"] == "stale-secret"
    assert os.environ["DYNAMIC_REGION"] == "stale-region"


def test_reused_secret_is_redacted_from_failure_and_identity(service_client):
    client, env_path = service_client
    env_path.write_text("DYNAMIC_TOKEN=reused-secret\n", encoding="utf-8")
    DynamicConnector.result = False
    DynamicConnector.error = "reused-secret was rejected"
    DynamicConnector.identity = {"nested": {"note": "reused-secret"}}

    response = client.post("/api/connectors/dynamic/connect", json={"DYNAMIC_REGION": "north"})

    assert response.status_code == 401
    assert "reused-secret" not in response.text
    assert "[redacted]" in response.text


def test_connect_route_has_no_connector_specific_branching():
    import inspect
    import prash.server

    tree = ast.parse(inspect.getsource(prash.server.connect_connector))
    compared_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not (compared_literals & set(CONNECTOR_REGISTRY))
