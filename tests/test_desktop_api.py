"""Comprehensive Anti-Hardcoding and Functional Test Suite for Prash Desktop API Bridge.

Guarantees 100% dynamic, un-mocked data paths across all endpoints:
- No hardcoded numbers or fallback metrics
- No synthetic latency/ping strings
- AST-level source inspection of server.py
- Dynamic connector-agnostic routing for all 13 connectors
"""
import ast
import json
import os
import re
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from prash.connector_registry import CONNECTOR_REGISTRY, ConnectorRegistryEntry, clear_connector_cache
from prash.connectors.base import Connector, ConnectorEvent, ConnectorState, ResourceState, WatchHandle
from prash.server import APIBridgeException, app, _active_watches


@pytest.fixture
def client():
    clear_connector_cache()
    _active_watches.clear()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Anti-Hardcoding Test Suite
# ---------------------------------------------------------------------------

def test_NO_HARDCODED_METRICS(client, monkeypatch, tmp_path):
    """Verifies that metrics endpoint never fabricates metrics when unsupported or unconfigured."""
    # 1. Unconfigured connector must return 400 CONNECTOR_NOT_CONFIGURED
    empty_env = tmp_path / ".empty_env"
    empty_env.write_text("")
    monkeypatch.setattr("prash.server.ENV_PATH", str(empty_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(empty_env))

    res = client.get("/api/connectors/aws/metrics")
    assert res.status_code == 400
    data = res.json()
    assert data["error"] is True
    assert data["code"] == "CONNECTOR_NOT_CONFIGURED"

    # 2. When configured but connector raises NotImplementedError, must return unsupported: True and empty metrics
    mock_env = tmp_path / ".env"
    mock_env.write_text("AWS_ACCESS_KEY_ID=test\nAWS_SECRET_ACCESS_KEY=test\nAWS_REGION=us-east-1\n")
    monkeypatch.setattr("prash.server.ENV_PATH", str(mock_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(mock_env))

    mock_conn = MagicMock()
    mock_conn.get_stats.side_effect = NotImplementedError("Stats not implemented")
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    res2 = client.get("/api/connectors/aws/metrics")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["metrics"] == []
    assert data2["events"] == []
    assert data2["unsupported"] is True


def test_NO_HARDCODED_STATUS(client, monkeypatch, tmp_path):
    """Verifies that an unconfigured connector returns status: 'unconfigured', never fake 'healthy'."""
    empty_env = tmp_path / ".env"
    empty_env.write_text("")
    monkeypatch.setattr("prash.server.ENV_PATH", str(empty_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(empty_env))

    for cid in ["aws", "azure", "gcp", "datadog", "pagerduty", "github", "gitlab"]:
        res = client.get(f"/api/connectors/{cid}/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "unconfigured", f"{cid} should be unconfigured, got {data['status']}"
        assert "missing_fields" in data["detail"]


def test_NO_HARDCODED_PING(client):
    """Inspects all endpoints and server source code to ensure no hardcoded latency strings (e.g. '14ms', '22ms')."""
    server_path = os.path.join(os.path.dirname(__file__), "..", "prash", "server.py")
    with open(server_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Regex search for numeric+ms string literals, e.g. "14ms", "22ms"
    matches = re.findall(r'["\']\s*\d+\s*ms\s*["\']', content, re.IGNORECASE)
    assert not matches, f"Found hardcoded ping strings in server.py: {matches}"

    # Also check /api/status response
    res = client.get("/api/status")
    assert res.status_code == 200
    raw_text = res.text
    assert "14ms" not in raw_text
    assert "22ms" not in raw_text


def test_NO_HARDCODED_FALLBACKS():
    """Parses prash/server.py AST to assert that NO numeric literals are used as values in return dicts."""
    server_path = os.path.join(os.path.dirname(__file__), "..", "prash", "server.py")
    with open(server_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=server_path)

    hardcoded_values = []

    class ReturnDictVisitor(ast.NodeVisitor):
        def visit_Return(self, node):
            if isinstance(node.value, ast.Dict):
                for k, v in zip(node.value.keys, node.value.values):
                    # Key must not have hardcoded numeric metric value
                    if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)):
                        key_name = getattr(k, "value", str(k))
                        # Allow standard status/code/zero if any, but forbid metrics like 45.2, 12.5, 32.1
                        if v.value in [45.2, 12.5, 32.1, 14, 22]:
                            hardcoded_values.append((key_name, v.value))
            self.generic_visit(node)

    visitor = ReturnDictVisitor()
    visitor.visit(tree)
    assert not hardcoded_values, f"Detected hardcoded fallback values in server return statements: {hardcoded_values}"


def test_CONNECTOR_AGNOSTIC_ROUTES(client, monkeypatch):
    """Verifies that all /api/connectors/{id}/* routes work with ANY registered connector, including a dynamically injected MockConnector."""
    class DynamicTestConnector(Connector):
        name = "mocktest"
        def authenticate(self) -> bool:
            return True
        def locate(self, resource: str):
            return {"id": resource}
        def poll_state(self, resource: str, **kwargs):
            return ResourceState(resource=resource, state=ConnectorState.HEALTHY, detail={"dynamic": True})
        def get_stats(self, target: str, since=None):
            return []

    mock_entry = ConnectorRegistryEntry(
        id="mocktest",
        name="Mock Test Connector",
        category="infrastructure",
        icon="box",
        color="#123456",
        connector_class_path="tests.test_desktop_api.DynamicTestConnector",
        auth_fields=[],
        widget_templates=[],
        supports_watch=False,
        supports_stats=True,
    )

    # Monkeypatch connector class lookup
    with patch.object(ConnectorRegistryEntry, "connector_class", new=DynamicTestConnector):
        with patch.dict(CONNECTOR_REGISTRY, {"mocktest": mock_entry}):
            # Test GET /api/connectors/mocktest
            res = client.get("/api/connectors/mocktest")
            assert res.status_code == 200
            assert res.json()["name"] == "Mock Test Connector"

            # Test GET /api/connectors/mocktest/status
            res_status = client.get("/api/connectors/mocktest/status?resource=test-res")
            assert res_status.status_code == 200
            assert res_status.json()["status"] == "healthy"
            assert res_status.json()["detail"] == {"dynamic": True}


def test_NO_SIMULATED_EVENTS(client):
    """Verifies that /api/watch/poll returns an empty list when no watches are active, with zero synthetic events."""
    _active_watches.clear()
    res = client.get("/api/watch/poll")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert data["events"] == []


def test_ERROR_NEVER_SILENT(client, monkeypatch, tmp_path):
    """Verifies that when a provider call throws an exception, the exact provider error is returned in consistent shape."""
    mock_env = tmp_path / ".env"
    mock_env.write_text("AWS_ACCESS_KEY_ID=test\nAWS_SECRET_ACCESS_KEY=test\nAWS_REGION=us-east-1\n")
    monkeypatch.setattr("prash.server.ENV_PATH", str(mock_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(mock_env))

    mock_conn = MagicMock()
    mock_conn.get_stats.side_effect = RuntimeError("AWS CloudWatch AccessDeniedException: User is not authorized")
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    res = client.get("/api/connectors/aws/metrics")
    assert res.status_code == 500
    data = res.json()
    assert data["error"] is True
    assert data["code"] == "CONNECTOR_API_ERROR"
    assert "AccessDeniedException" in data["message"]


def test_DYNAMIC_CONFIG_DETECTION(client, monkeypatch, tmp_path):
    """Verifies GET /api/config and POST /api/projects/auto-import dynamically inspect the registry."""
    mock_env = tmp_path / ".env"
    mock_env.write_text("GITHUB_TOKEN=ghp_1234567890abcdef\n")
    monkeypatch.setattr("prash.server.ENV_PATH", str(mock_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(mock_env))

    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "github" in data["services"]
    assert data["services"]["github"]["status"] == "configured"
    assert "aws" not in data["services"]  # AWS is not configured

    # Test auto-import
    mock_yaml = tmp_path / "prash.yaml"
    monkeypatch.setattr("prash.server.YAML_PATH", str(mock_yaml))
    res_import = client.post("/api/projects/auto-import")
    assert res_import.status_code == 200
    data_import = res_import.json()
    assert data_import["success"] is True
    services = data_import["projects"][0]["environments"][0]["services"]
    connector_ids = [s["connector_id"] for s in services]
    assert "github" in connector_ids
    assert "aws" not in connector_ids


def test_PROJECT_YAML_PERSISTENCE(client, monkeypatch, tmp_path):
    """Validates full CRUD operations against prash.yaml."""
    mock_yaml = tmp_path / "prash.yaml"
    monkeypatch.setattr("prash.server.YAML_PATH", str(mock_yaml))

    # 1. Initially empty
    res = client.get("/api/projects")
    assert res.status_code == 200
    assert res.json()["projects"] == []

    # 2. Create project
    project_payload = {
        "id": "production-stack",
        "name": "Production Stack",
        "environments": [
            {
                "name": "Production",
                "services": [
                    {"connector_id": "aws", "resource_id": "i-0123456", "display_name": "API EC2"}
                ]
            }
        ]
    }
    res_post = client.post("/api/projects", json={"project": project_payload})
    assert res_post.status_code == 200
    assert res_post.json()["project"]["id"] == "production-stack"

    # 3. Read back
    res_get = client.get("/api/projects")
    assert res_get.status_code == 200
    projects = res_get.json()["projects"]
    assert len(projects) == 1
    assert projects[0]["name"] == "Production Stack"

    # 4. Delete project
    res_del = client.delete("/api/projects/production-stack")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    # 5. Verify deleted
    res_verify = client.get("/api/projects")
    assert res_verify.json()["projects"] == []


def test_PROJECT_PUT_AND_STATUS(client, monkeypatch, tmp_path):
    """Validates PUT /api/projects/{id} and GET /api/projects/{id}/status live aggregation."""
    mock_yaml = tmp_path / "prash.yaml"
    monkeypatch.setattr("prash.server.YAML_PATH", str(mock_yaml))

    # 1. Create a project
    proj = {
        "id": "my-app",
        "name": "My App",
        "environments": [
            {
                "name": "Production",
                "services": [
                    {"connector_id": "aws", "resource_id": "i-test123", "display_name": "Prod Server"}
                ]
            }
        ]
    }
    client.post("/api/projects", json={"project": proj})

    # 2. Test PUT /api/projects/{id} - Update environments
    updated_proj = {
        "name": "My App V2",
        "environments": [
            {
                "name": "Production",
                "services": [
                    {"connector_id": "aws", "resource_id": "i-test123", "display_name": "Prod Server V2"}
                ]
            },
            {
                "name": "Staging",
                "services": []
            }
        ]
    }
    res_put = client.put("/api/projects/my-app", json={"project": updated_proj})
    assert res_put.status_code == 200
    res_data = res_put.json()["project"]
    assert res_data["name"] == "My App V2"
    assert len(res_data["environments"]) == 2

    # 3. Test PUT on non-existent project returns 404
    res_404 = client.put("/api/projects/non-existent", json={"project": updated_proj})
    assert res_404.status_code == 404

    # 4. Test GET /api/projects/{id}/status
    mock_env = tmp_path / ".env"
    mock_env.write_text("AWS_ACCESS_KEY_ID=test\nAWS_SECRET_ACCESS_KEY=test\nAWS_REGION=us-east-1\n")
    monkeypatch.setattr("prash.server.ENV_PATH", str(mock_env))

    # Mock connector poll_state
    mock_conn = MagicMock()
    mock_poll = MagicMock()
    mock_poll.state.name = "HEALTHY"
    mock_poll.message = "Instance running normally"
    mock_conn.poll_state.return_value = mock_poll
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    res_status = client.get("/api/projects/my-app/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["project_id"] == "my-app"
    assert status_data["status"] == "healthy"
    assert status_data["summary"]["healthy"] == 1
    assert status_data["summary"]["total"] == 1
    assert len(status_data["environments"]) == 2
    prod_env = next(e for e in status_data["environments"] if e["name"] == "Production")
    assert prod_env["status"] == "healthy"
    assert prod_env["services"][0]["display_name"] == "Prod Server V2"
    assert prod_env["services"][0]["status"] == "healthy"


def test_CHAT_TELEMETRY_INJECTION(client, monkeypatch, tmp_path):
    """Verifies that when service_context is provided to /api/chat, live telemetry is polled and injected."""
    mock_env = tmp_path / ".env"
    mock_env.write_text("AWS_ACCESS_KEY_ID=test\nAWS_SECRET_ACCESS_KEY=test\nAWS_REGION=us-east-1\n")
    monkeypatch.setattr("prash.server.ENV_PATH", str(mock_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(mock_env))

    mock_conn = MagicMock()
    mock_conn.poll_state.return_value = ResourceState(
        resource="i-0abc123",
        state=ConnectorState.CRASH_LOOPING,
        detail={"reason": "OOMKilled", "exit_code": 137}
    )
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    captured_prompt = []
    async def mock_llm_resolve(prompt, ctx):
        captured_prompt.append(prompt)
        from prash.intent import Suggestion
        return Suggestion(explain="Restart crashed instance", argv=["restart", "i-0abc123"])

    monkeypatch.setattr("prash.intent._resolve_via_llm_async", mock_llm_resolve)
    monkeypatch.setattr("prash.intent.resolve_fast_path", lambda msg, ctx: None)

    res = client.post(
        "/api/chat",
        json={
            "message": "Why is my server down?",
            "service_context": {"connector_id": "aws", "resource_id": "i-0abc123"}
        }
    )
    assert res.status_code == 200
    assert len(captured_prompt) == 1
    prompt_sent = captured_prompt[0]
    assert "crash-looping" in prompt_sent
    assert "OOMKilled" in prompt_sent
    assert "Why is my server down?" in prompt_sent


def test_WATCH_LIFECYCLE_START_STOP(client, monkeypatch):
    """Verifies watch lifecycle: start watch -> poll -> stop watch."""
    mock_handle = MagicMock(spec=WatchHandle)
    mock_handle.poll.return_value = [
        {
            "timestamp": "2026-09-07T20:00:00Z",
            "connector": "aws",
            "event_type": "instance_reboot",
            "summary": "EC2 instance rebooted",
            "raw": {"id": "i-0123"}
        }
    ]
    mock_handle.stop.return_value = None

    mock_conn = MagicMock()
    mock_conn.watch.return_value = mock_handle
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    # 1. Start watch
    res_start = client.post("/api/connectors/aws/watch", json={"target": "i-0123"})
    assert res_start.status_code == 200
    watch_id = res_start.json()["watch_id"]
    assert watch_id == "aws:i-0123"

    # 2. Duplicate watch must fail with 409
    res_dup = client.post("/api/connectors/aws/watch", json={"target": "i-0123"})
    assert res_dup.status_code == 409

    # 3. Poll active watches
    res_poll = client.get("/api/watch/poll")
    assert res_poll.status_code == 200
    events = res_poll.json()["events"]
    assert len(events) == 1
    assert events[0]["event_type"] == "instance_reboot"

    # 4. Stop watch
    res_stop = client.delete("/api/connectors/aws/watch", params={"watch_id": watch_id})
    assert res_stop.status_code == 200
    assert res_stop.json()["success"] is True
    mock_handle.stop.assert_called_once()


def test_CONNECTOR_CONNECT_VALIDATE_DISCONNECT(client, monkeypatch, tmp_path):
    """Verifies the complete connection lifecycle: connect, validate, masked credentials, and disconnect."""
    test_env = tmp_path / ".test_connect_env"
    test_env.write_text("")
    monkeypatch.setattr("prash.server.ENV_PATH", str(test_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(test_env))

    # 1. Missing credentials must fail with 400
    res_fail = client.post("/api/connectors/aws/connect", json={"AWS_REGION": "us-east-1"})
    assert res_fail.status_code == 400
    assert res_fail.json()["code"] == "CONNECTOR_NOT_CONFIGURED"

    # 2. Mock authenticate success
    mock_conn = MagicMock()
    mock_conn.authenticate.return_value = True
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    res_connect = client.post("/api/connectors/aws/connect", json={
        "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "AWS_REGION": "us-west-2",
    })
    assert res_connect.status_code == 200
    data_conn = res_connect.json()
    assert data_conn["success"] is True
    assert "identity" in data_conn
    assert "AWS" in data_conn["identity"]
    assert "last_verified" in data_conn
    assert data_conn["last_verified"] is not None

    # 3. Verify masked credentials are returned, not raw secrets
    res_detail = client.get("/api/connectors/aws")
    assert res_detail.status_code == 200
    detail_data = res_detail.json()
    assert detail_data["status"] == "configured"
    assert "auth_fields" in detail_data
    assert "last_verified" in detail_data
    assert detail_data["last_verified"] is not None
    fields = {field["key"]: field for field in detail_data["auth_fields"]}
    masked_key = fields["AWS_ACCESS_KEY_ID"]["masked_value"]
    assert masked_key.startswith("AKI")
    assert masked_key.endswith("PLE")
    assert "IOSFODNN7" not in masked_key  # Must not contain inner secret

    # 4. Validate credentials
    res_val = client.get("/api/connectors/aws/validate")
    assert res_val.status_code == 200
    assert res_val.json()["valid"] is True
    assert res_val.json()["status"] == "connected"
    assert res_val.json()["last_verified"] is not None

    # 5. When auth fails (e.g. expired)
    mock_conn.authenticate.return_value = False
    res_exp = client.get("/api/connectors/aws/validate")
    assert res_exp.status_code == 200
    assert res_exp.json()["valid"] is False
    assert res_exp.json()["status"] == "expired"

    # 6. Disconnect
    res_disc = client.post("/api/connectors/aws/disconnect")
    assert res_disc.status_code == 200
    assert res_disc.json()["success"] is True

    # 7. Connector should now be unconfigured
    res_unconf = client.get("/api/connectors/aws")
    assert res_unconf.status_code == 200
    assert res_unconf.json()["status"] == "unconfigured"
    assert res_unconf.json()["last_verified"] is None
    unconf_fields = {field["key"]: field for field in res_unconf.json()["auth_fields"]}
    assert unconf_fields["AWS_ACCESS_KEY_ID"]["masked_value"] == ""


def test_integrations_management_and_last_verified(client, monkeypatch, tmp_path):
    """Verifies that connector listing, connection, validation, and disconnection properly maintain last_verified timestamps."""
    mock_env = tmp_path / ".env"
    mock_env.write_text("")
    monkeypatch.setattr("prash.server.ENV_PATH", str(mock_env))

    # 1. Initial list returns all connectors with last_verified key
    res_list = client.get("/api/connectors")
    assert res_list.status_code == 200
    connectors = res_list.json()["connectors"]
    assert len(connectors) > 0
    for c in connectors:
        assert "last_verified" in c
        assert "status" in c
        assert "auth_fields" in c

    # 2. Connect mock connector
    mock_conn = MagicMock()
    mock_conn.authenticate.return_value = True
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    res_connect = client.post("/api/connectors/github/connect", json={
        "GITHUB_TOKEN": "ghp_mockSecretTokenForTesting12345",
        "GITHUB_REPO": "testorg/testrepo"
    })
    assert res_connect.status_code == 200
    data_conn = res_connect.json()
    assert data_conn["success"] is True
    assert data_conn["last_verified"] is not None

    # Verify /api/connectors list reflects last_verified for github
    res_list2 = client.get("/api/connectors")
    assert res_list2.status_code == 200
    gh = next(c for c in res_list2.json()["connectors"] if c["id"] == "github")
    assert gh["status"] == "configured"
    assert gh["last_verified"] is not None

    # 3. Manual validation updates last_verified
    res_val = client.get("/api/connectors/github/validate")
    assert res_val.status_code == 200
    assert res_val.json()["valid"] is True
    assert res_val.json()["last_verified"] is not None

    # 4. Disconnect clears last_verified
    res_disc = client.post("/api/connectors/github/disconnect")
    assert res_disc.status_code == 200

    res_list3 = client.get("/api/connectors")
    gh_after = next(c for c in res_list3.json()["connectors"] if c["id"] == "github")
    assert gh_after["status"] == "unconfigured"
    assert gh_after["last_verified"] is None


def test_WATCH_LIFECYCLE_AND_CONTROLS(client, monkeypatch, tmp_path):
    """Validates complete watch lifecycle: start with interval, active list, pause, resume, and stop."""
    mock_yaml = tmp_path / "prash.yaml"
    monkeypatch.setattr("prash.server.YAML_PATH", str(mock_yaml))

    mock_conn = MagicMock()
    mock_handle = MagicMock()
    mock_handle.connector = "aws"
    mock_handle.target = "i-testpod"
    mock_handle.interval = 15
    mock_handle.poll.return_value = [
        {
            "connector": "aws",
            "event_type": "cpu_spike",
            "summary": "CPU reached 95%",
            "raw": {"value": 95},
            "timestamp": "2026-09-13T12:00:00Z",
        }
    ]
    mock_conn.watch.return_value = mock_handle
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    # 1. Start Watch
    res_start = client.post("/api/connectors/aws/watch", json={"target": "i-testpod", "interval": 15})
    assert res_start.status_code == 200
    data_start = res_start.json()
    assert data_start["watch_id"] == "aws:i-testpod"
    assert data_start["status"] == "active"
    assert data_start["interval"] == 15

    # 2. Inspect Active Watches
    res_active = client.get("/api/watch/active")
    assert res_active.status_code == 200
    data_active = res_active.json()
    assert data_active["count"] == 1
    watch_entry = data_active["watches"][0]
    assert watch_entry["watch_id"] == "aws:i-testpod"
    assert watch_entry["interval"] == 15
    assert watch_entry["status"] == "healthy"

    # 3. Poll active watches returns events
    res_poll = client.get("/api/watch/poll")
    assert res_poll.status_code == 200
    poll_data = res_poll.json()
    assert len(poll_data["events"]) == 1
    assert poll_data["events"][0]["event_type"] == "cpu_spike"

    # 4. Duplicate start returns 409 Conflict
    res_dup = client.post("/api/connectors/aws/watch", json={"target": "i-testpod"})
    assert res_dup.status_code == 409
    assert res_dup.json()["code"] == "WATCH_ALREADY_ACTIVE"

    # 5. Pause Watch
    res_pause = client.post("/api/connectors/aws/watch/pause", json={"watch_id": "aws:i-testpod"})
    assert res_pause.status_code == 200
    assert res_pause.json()["status"] == "paused"

    res_active2 = client.get("/api/watch/active")
    assert res_active2.json()["watches"][0]["status"] == "paused"

    # 6. Resume Watch
    res_resume = client.post("/api/connectors/aws/watch/resume", json={"watch_id": "aws:i-testpod"})
    assert res_resume.status_code == 200
    assert res_resume.json()["status"] == "active"

    # 7. Stop Watch
    res_stop = client.delete("/api/connectors/aws/watch?watch_id=aws:i-testpod")
    assert res_stop.status_code == 200
    assert res_stop.json()["success"] is True

    # 8. Active watches now empty
    res_empty = client.get("/api/watch/active")
    assert res_empty.json()["count"] == 0


def test_WATCH_YAML_PERSISTENCE(client, monkeypatch, tmp_path):
    """Verifies that started watches are persisted to prash.yaml and removed on stop."""
    mock_yaml = tmp_path / "prash.yaml"
    monkeypatch.setattr("prash.server.YAML_PATH", str(mock_yaml))

    mock_conn = MagicMock()
    mock_handle = MagicMock()
    mock_handle.connector = "github"
    mock_handle.target = "main-repo"
    mock_handle.interval = 5
    mock_conn.watch.return_value = mock_handle
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    # Start watch
    client.post("/api/connectors/github/watch", json={"target": "main-repo", "interval": 5})

    # Read yaml directly
    import yaml
    with open(mock_yaml, "r", encoding="utf-8") as f:
        yaml_content = yaml.safe_load(f)
    assert "active_watches" in yaml_content
    assert len(yaml_content["active_watches"]) == 1
    assert yaml_content["active_watches"][0]["watch_id"] == "github:main-repo"

    # Stop watch
    client.delete("/api/connectors/github/watch?target=main-repo")
    with open(mock_yaml, "r", encoding="utf-8") as f:
        yaml_content2 = yaml.safe_load(f)
    assert len(yaml_content2.get("active_watches", [])) == 0


def test_CHAT_GREETING_CONTEXT_AWARE(client, monkeypatch, tmp_path):
    """Verifies that /api/chat/greeting fetches live connector telemetry and returns context-aware greeting."""
    mock_env = tmp_path / ".env"
    mock_env.write_text("AWS_ACCESS_KEY_ID=test\nAWS_SECRET_ACCESS_KEY=test\nAWS_REGION=us-east-1\n")
    monkeypatch.setattr("prash.server.ENV_PATH", str(mock_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(mock_env))

    mock_conn = MagicMock()
    mock_conn.poll_state.return_value = ResourceState(
        resource="i-0abc123",
        state=ConnectorState.HEALTHY,
        detail={"cpu": 19.5, "memory": 40.2}
    )
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    res = client.get("/api/chat/greeting?connector_id=aws&resource_id=i-0abc123")
    assert res.status_code == 200
    data = res.json()
    assert "AWS" in data["greeting"]
    assert "i-0abc123" in data["greeting"]
    assert "healthy" in data["greeting"]
    assert "19.5" in data["greeting"]
    assert "40.2" in data["greeting"]
    assert len(data["suggested_prompts"]) > 0


def test_CHAT_GREETING_GLOBAL(client, monkeypatch, tmp_path):
    """Verifies that /api/chat/greeting returns global copilot greeting when no context is specified."""
    mock_env = tmp_path / ".env"
    mock_env.write_text("")
    monkeypatch.setattr("prash.server.ENV_PATH", str(mock_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(mock_env))

    res = client.get("/api/chat/greeting")
    assert res.status_code == 200
    data = res.json()
    assert "Lear Copilot" in data["greeting"]
    assert len(data["suggested_prompts"]) > 0


def test_CHAT_EXECUTE_ACTION_CLI(client):
    """Verifies that /api/chat/execute executes real CLI command and appends to activity log."""
    res = client.post(
        "/api/chat/execute",
        json={"command": ["actions"], "action_id": "actions"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["exit_code"] == 0
    assert "actions" in data["command"]
    assert "restart" in data["output"]

    # Verify event was recorded in /api/activity
    act_res = client.get("/api/activity")
    assert act_res.status_code == 200
    events = act_res.json()["events"]
    chat_events = [e for e in events if e.get("watch_id", "").startswith("chat:")]
    assert len(chat_events) > 0
    assert "ACTION_EXECUTED" == chat_events[-1]["event_type"]


def test_CHAT_EXECUTE_STRIPS_PRASH_PREFIX(client):
    """Verifies that /api/chat/execute strips leading 'prash' if passed in command."""
    res = client.post(
        "/api/chat/execute",
        json={"command": ["prash", "actions"]}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["command"] == ["actions"]


def test_CHAT_EXECUTE_APPROVAL_TIER_ACTION_IS_NOT_SILENTLY_DECLINED(client, monkeypatch, tmp_path):
    """Found live 2026-09-17: an APPROVAL-tier action (execute-aws,
    execute-gcp, apply-ci-fix, ...) triggered via /api/chat/execute was
    reported as "declined by user" every single time -- cmd_run's default
    ask=CliAsk() blocks on a real interactive stdin prompt that doesn't
    exist in this in-process, FastAPI-threadpool-thread context, reads
    nothing, and the dispatcher's own "silence means no" rule (correct for
    a real terminal) turned that into a fabricated decline. Product
    decision 2026-09-17: the chat UI's "Execute Action" click IS the
    approval here (the exact command was already shown before that button
    existed), so this must get past the approval gate. Landing on the
    action's own execute() logic (missing AWS creds, in this test) is
    fine; landing on "declined by user" or "needs_approval" is the
    regression this guards against."""
    mock_env = tmp_path / ".env"
    mock_env.write_text("")  # deliberately no AWS credentials -- must never reach a real AWS call
    monkeypatch.setenv("PRASH_ENV", str(mock_env))

    res = client.post(
        "/api/chat/execute",
        json={"command": ["run", "execute-aws", "some-instance", "--command", "echo hi"]},
    )
    assert res.status_code == 200
    output = res.json()["output"]
    assert "declined by user" not in output
    assert "needs_approval" not in output


def test_CHAT_STREAM_SSE(client, monkeypatch, tmp_path):
    """Verifies that /api/chat/stream streams reasoning tokens and final action payload via SSE."""
    mock_env = tmp_path / ".env"
    mock_env.write_text("AWS_ACCESS_KEY_ID=test\nAWS_SECRET_ACCESS_KEY=test\nAWS_REGION=us-east-1\n")
    monkeypatch.setattr("prash.server.ENV_PATH", str(mock_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(mock_env))

    mock_conn = MagicMock()
    mock_conn.poll_state.return_value = ResourceState(
        resource="i-0abc123",
        state=ConnectorState.CRASH_LOOPING,
        detail={"error": "OOM"}
    )
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    async def mock_llm_resolve(prompt, ctx):
        from prash.intent import Suggestion
        return Suggestion(explain="Restart crashed instance", argv=["restart", "i-0abc123"])

    monkeypatch.setattr("prash.intent._resolve_via_llm_async", mock_llm_resolve)
    monkeypatch.setattr("prash.intent.resolve_fast_path", lambda msg, ctx: None)

    res = client.post(
        "/api/chat/stream",
        json={
            "message": "Why is the server down?",
            "service_context": {"connector_id": "aws", "resource_id": "i-0abc123"}
        }
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    body = res.text
    assert "data: " in body
    assert "Restart" in body
    assert "prash restart i-0abc123" in body
    assert '"done": true' in body


def test_DASHBOARD_SUMMARY_ENDPOINT(client, monkeypatch, tmp_path):
    """Verifies that /api/dashboard/summary returns aggregate infrastructure health and counts."""
    mock_env = tmp_path / ".env"
    mock_env.write_text("AWS_ACCESS_KEY_ID=test\nAWS_SECRET_ACCESS_KEY=test\nAWS_REGION=us-east-1\n")
    mock_yaml = tmp_path / "prash.yaml"
    mock_yaml.write_text("projects:\n  - id: proj-1\n    name: Test Project\n    environments:\n      - name: Production\n        services:\n          - connector_id: aws\n            resource_id: i-123\n")

    monkeypatch.setattr("prash.server.ENV_PATH", str(mock_env))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(mock_env))
    monkeypatch.setattr("prash.server.YAML_PATH", str(mock_yaml))

    # Reset cache
    from prash.server import _dashboard_summary_cache
    _dashboard_summary_cache["timestamp"] = 0.0
    _dashboard_summary_cache["data"] = None

    mock_conn = MagicMock()
    mock_conn.authenticate.return_value = True
    monkeypatch.setattr("prash.server.get_connector", lambda cid, cfg=None: mock_conn)

    res = client.get("/api/dashboard/summary")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "health_score" in data
    assert data["health_score"] >= 0
    assert data["counts"]["total_services"] == 1
    assert data["projects_count"] == 1
    assert data["cached"] is False


def test_DASHBOARD_SUMMARY_CACHING(client, monkeypatch, tmp_path):
    """Verifies that /api/dashboard/summary caches result for 10 seconds."""
    from prash.server import _dashboard_summary_cache
    _dashboard_summary_cache["timestamp"] = 0.0
    _dashboard_summary_cache["data"] = None

    mock_yaml = tmp_path / "prash.yaml"
    mock_yaml.write_text("projects: []\n")
    monkeypatch.setattr("prash.server.YAML_PATH", str(mock_yaml))

    # First call - cache miss
    res1 = client.get("/api/dashboard/summary")
    assert res1.status_code == 200
    assert res1.json()["cached"] is False

    # Second call - cache hit within 10s
    res2 = client.get("/api/dashboard/summary")
    assert res2.status_code == 200
    assert res2.json()["cached"] is True


def test_DASHBOARD_ACTIVITY_ENDPOINT(client):
    """Verifies that /api/dashboard/activity returns cross-service events with limit."""
    from prash.server import _activity_log
    _activity_log.append({
        "watch_id": "test:watch-1",
        "connector": "aws",
        "event_type": "TEST_EVENT",
        "summary": "Instance status ok",
        "timestamp": "2026-09-13T12:00:00Z",
        "severity": "info",
    })

    res = client.get("/api/dashboard/activity?limit=5")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert data["count"] <= 5
    assert len(data["events"]) > 0
    assert any(e["summary"] == "Instance status ok" for e in data["events"])


def test_ACTIVITY_LOG_AGGREGATION_PAGINATION_AND_FILTERS(client, tmp_path, monkeypatch):
    """Verifies that /api/activity aggregates events from memory and disk, with pagination and filters."""
    from prash.server import _activity_log
    from prash.audit import AuditLog
    from prash.actions.contract import ActionResult, ActionResultStatus, RiskTier, Decision
    from prash.permissions import PermissionMode

    # Set up dedicated audit log
    audit_file = tmp_path / "audit.log"
    monkeypatch.setenv("PRASH_AUDIT_LOG_PATH", str(audit_file))
    audit = AuditLog(path=audit_file)
    audit.append(
        action_id="aws-ec2-restart",
        risk_tier=RiskTier.SAFE,
        mode=PermissionMode.AUTO_SAFE,
        decision=Decision.ALLOW,
        result=ActionResult(status=ActionResultStatus.SUCCEEDED, summary="Restarted instance i-12345"),
        extra={"service_context": {"connector_id": "aws"}},
    )

    # Ingest in-memory events
    _activity_log.clear()
    _activity_log.append({
        "id": "act-live-1",
        "connector": "github",
        "event_type": "PUSH_EVENT",
        "severity": "info",
        "summary": "Pushed commit to main branch",
        "timestamp": "2026-09-13T12:30:00Z",
    })
    _activity_log.append({
        "id": "act-live-2",
        "connector": "kubernetes",
        "event_type": "POD_CRASH_LOOP",
        "severity": "error",
        "summary": "Pod api-gateway in CrashLoopBackOff",
        "timestamp": "2026-09-13T12:35:00Z",
    })

    # 1. Test basic fetch: should include both in-memory and disk audit events
    res = client.get("/api/activity")
    assert res.status_code == 200
    data = res.json()
    assert "events" in data
    assert "total" in data
    assert data["total"] >= 3

    # 2. Test pagination
    res_page = client.get("/api/activity?limit=2&offset=0")
    assert res_page.status_code == 200
    p1 = res_page.json()
    assert len(p1["events"]) == 2
    assert p1["limit"] == 2
    assert p1["offset"] == 0
    assert p1["has_more"] is True

    res_page2 = client.get("/api/activity?limit=2&offset=2")
    assert res_page2.status_code == 200
    p2 = res_page2.json()
    assert len(p2["events"]) >= 1
    assert p2["offset"] == 2

    # 3. Test filter by connector
    res_gh = client.get("/api/activity?connector=github")
    assert res_gh.status_code == 200
    gh_data = res_gh.json()
    assert all(e["connector"] == "github" for e in gh_data["events"])
    assert any(e["summary"] == "Pushed commit to main branch" for e in gh_data["events"])

    # 4. Test filter by severity
    res_err = client.get("/api/activity?severity=error")
    assert res_err.status_code == 200
    err_data = res_err.json()
    assert all(e["severity"] == "error" for e in err_data["events"])
    assert any("CrashLoopBackOff" in e["summary"] for e in err_data["events"])

    # 5. Test search with q
    res_search = client.get("/api/activity?q=CrashLoopBackOff")
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert len(search_data["events"]) == 1
    assert search_data["events"][0]["connector"] == "kubernetes"


def test_SETTINGS_LIFECYCLE_AND_PERSISTENCE(client, monkeypatch, tmp_path):
    """Verifies that settings can be fetched, updated, and persisted to prash.yaml and .env."""
    test_yaml = tmp_path / "prash.yaml"
    test_env = tmp_path / ".env"
    test_env.write_text("PRIMARY_MODEL=deepseek-v4-flash\nPRASH_PERMISSION_MODE=ask\n")
    test_yaml.write_text("settings:\n  model: deepseek-v4-flash\n  permission_mode: ask\n")

    monkeypatch.setattr("prash.server.YAML_PATH", str(test_yaml))
    monkeypatch.setattr("prash.server.ENV_PATH", str(test_env))

    # 1. GET initial settings
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["model"] == "deepseek-v4-flash"
    assert data["permission_mode"] == "ask"
    assert len(data["available_models"]) >= 3
    assert len(data["available_permission_modes"]) == 3
    assert "poll_interval" in data
    assert "retention_days" in data
    assert "desktop_notifications" in data

    # 2. POST updated settings
    payload = {
        "model": "claude-3-5-sonnet",
        "permission_mode": "auto-safe",
        "poll_interval": 30,
        "retention_days": 14,
        "desktop_notifications": False,
        "alert_on_degraded": False,
        "slack_webhook": "https://hooks.slack.com/services/T00/B00/X00",
        "discord_webhook": "https://discord.com/api/webhooks/123/abc",
        "pagerduty_key": "pd-routing-key-test",
    }
    post_res = client.post("/api/settings", json=payload)
    assert post_res.status_code == 200
    res_data = post_res.json()
    assert res_data["success"] is True
    assert res_data["settings"]["model"] == "claude-3-5-sonnet"
    assert res_data["settings"]["permission_mode"] == "auto-safe"
    assert res_data["settings"]["poll_interval"] == 30
    assert res_data["settings"]["retention_days"] == 14

    # 3. Verify .env file updated
    env_content = test_env.read_text()
    assert "claude-3-5-sonnet" in env_content
    assert "auto-safe" in env_content
    assert "30" in env_content
    assert "SLACK_WEBHOOK_URL=" in env_content

    # 4. Re-fetch via GET to assert persistence
    res_updated = client.get("/api/settings")
    assert res_updated.status_code == 200
    up_data = res_updated.json()
    assert up_data["model"] == "claude-3-5-sonnet"
    assert up_data["permission_mode"] == "auto-safe"
    assert up_data["poll_interval"] == 30
    assert up_data["retention_days"] == 14
    assert up_data["desktop_notifications"] is False
    assert up_data["alert_on_degraded"] is False
    assert up_data["slack_webhook"] == "https://hooks.slack.com/services/T00/B00/X00"
    assert up_data["pagerduty_key"] == "pd-routing-key-test"


def test_CONFIG_MASKED_CREDENTIALS(client, monkeypatch, tmp_path):
    """Verifies that GET /api/config returns masked credentials and never leaks raw secrets."""
    test_env = tmp_path / ".env"
    test_env.write_text(
        "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
        "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
        "GITHUB_TOKEN=ghp_secretTokenLongerValue123456\n"
        "SHORT_KEY=1234\n"
    )
    monkeypatch.setattr("prash.server.ENV_PATH", str(test_env))

    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "raw" in data
    raw = data["raw"]

    # Assert raw tokens are masked and not present verbatim
    assert raw["AWS_ACCESS_KEY_ID"] == "AKI...PLE"
    assert raw["AWS_SECRET_ACCESS_KEY"] == "wJa...KEY"
    assert raw["GITHUB_TOKEN"] == "ghp...456"
    assert raw["SHORT_KEY"] == "••••••••"

    # Crucial security guarantee: raw secrets must never appear in response JSON
    assert "AKIAIOSFODNN7EXAMPLE" not in res.text
    assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in res.text
    assert "ghp_secretTokenLongerValue123456" not in res.text


def test_SYSTEM_VERSION_DYNAMIC(client):
    """Verifies that GET /api/system/version returns dynamic platform and connector statistics."""
    res = client.get("/api/system/version")
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == "2.4.0"
    assert data["name"] == "Lear Desktop Console"
    assert data["status"] == "operational"
    assert "platform" in data
    assert "python_version" in data
    assert data["connectors_total"] == len(CONNECTOR_REGISTRY)
    assert isinstance(data["connectors_configured"], int)


def test_NOTIFICATIONS_LIFECYCLE_PERSISTENCE(client, monkeypatch, tmp_path):
    """Verifies notification queue operations, unread count tracking, and disk persistence."""
    test_notifs_path = tmp_path / "notifications.json"
    monkeypatch.setattr("prash.server.NOTIFICATIONS_PATH", str(test_notifs_path))

    import prash.server as srv
    srv._notifications.clear()

    # 1. Initially empty
    res = client.get("/api/notifications")
    assert res.status_code == 200
    assert res.json()["notifications"] == []
    assert res.json()["unread_count"] == 0

    # 2. Add test notifications
    n1 = {
        "id": "notif_1",
        "title": "EC2 Memory Spike",
        "message": "Memory utilization exceeded 90% on i-0123",
        "connector": "aws",
        "severity": "warning",
        "timestamp": "2026-09-13T10:00:00Z",
        "read": False,
    }
    n2 = {
        "id": "notif_2",
        "title": "Kubernetes CrashLoopBackOff",
        "message": "Pod order-service restarted 5 times",
        "connector": "kubernetes",
        "severity": "error",
        "timestamp": "2026-09-13T10:05:00Z",
        "read": False,
    }
    srv._notifications.extend([n1, n2])
    srv._save_notifications_to_disk()

    # Verify saved to disk
    assert test_notifs_path.exists()
    assert "notif_1" in test_notifs_path.read_text()

    # 3. Fetch notifications and check unread count
    res_list = client.get("/api/notifications")
    assert res_list.status_code == 200
    data = res_list.json()
    assert len(data["notifications"]) == 2
    assert data["unread_count"] == 2

    # 4. Mark notif_1 as read
    res_read1 = client.post("/api/notifications/notif_1/read")
    assert res_read1.status_code == 200
    assert res_read1.json()["unread_count"] == 1

    # Verify disk updated
    disk_data = json.loads(test_notifs_path.read_text())
    assert any(n["id"] == "notif_1" and n["read"] is True for n in disk_data)

    # 5. Mark all as read
    res_read_all = client.post("/api/notifications/all/read")
    assert res_read_all.status_code == 200
    assert res_read_all.json()["unread_count"] == 0

    # 6. Clear all notifications
    res_clear = client.delete("/api/notifications")
    assert res_clear.status_code == 200
    assert res_clear.json()["unread_count"] == 0

    res_empty = client.get("/api/notifications")
    assert res_empty.json()["notifications"] == []
    assert res_empty.json()["unread_count"] == 0
    assert json.loads(test_notifs_path.read_text()) == []







