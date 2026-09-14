"""Tests for the AI widget generation endpoints and persistence."""
from fastapi.testclient import TestClient
import pytest

from prash.server import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    yaml_path = tmp_path / "prash.yaml"
    monkeypatch.setattr("prash.server.ENV_PATH", str(env_path))
    monkeypatch.setattr("prash.connector_registry.ENV_PATH", str(env_path))
    monkeypatch.setattr("prash.server.YAML_PATH", str(yaml_path))
    return TestClient(app)


def test_generate_widgets_unknown_connector_returns_404(client):
    res = client.post("/api/connectors/nonexistent/generate-widgets", json={})
    assert res.status_code == 404
    data = res.json()
    assert data["error"] is True
    assert data["code"] == "CONNECTOR_NOT_FOUND"


def test_generate_widgets_aws_falls_back_to_registry_templates_honestly(client):
    res = client.post(
        "/api/connectors/aws/generate-widgets",
        json={"resource_id": "i-0abc123", "prompt": "Focus on CPU and disk performance"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["connector_id"] == "aws"
    assert data["resource_id"] == "i-0abc123"
    assert data["source"] == "template"
    assert data["rejected"] == []

    widgets = data["widgets"]
    assert len(widgets) >= 3

    widget_types = [w["type"] for w in widgets]
    assert "gauge" in widget_types
    assert "line_chart" in widget_types

    # Registry templates are not AI output and must not be labelled as such.
    for w in widgets:
        assert "row" in w["position"]
        assert "col" in w["position"]
        assert "span" in w["position"]
        assert w["ai_generated"] is False


def test_generate_widgets_uses_valid_ai_candidates_and_reports_rejections(client):
    res = client.post(
        "/api/connectors/aws/generate-widgets",
        json={
            "resource_id": "i-0abc123",
            "widgets": [
                {"id": "ai_cpu", "type": "gauge", "label": "CPU Load", "metric_keys": ["CPUUtilization"], "unit": "%"},
                {"id": "bad_type", "type": "pie_chart", "label": "Pie"},
                {"id": "bad_metric", "type": "metric_card", "label": "Ghost", "metric_keys": ["NotARealMetric"]},
            ],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "ai"
    assert len(data["widgets"]) == 1
    assert data["widgets"][0]["id"] == "ai_cpu"
    assert data["widgets"][0]["ai_generated"] is True
    assert len(data["rejected"]) == 2
    assert any("unsupported widget type" in reason for reason in data["rejected"])
    assert any("unknown metric keys" in reason for reason in data["rejected"])


def test_generate_widgets_falls_back_when_all_candidates_invalid(client):
    res = client.post(
        "/api/connectors/aws/generate-widgets",
        json={"resource_id": "i-1", "widgets": [{"id": "x", "type": "pie_chart", "label": "Pie"}]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "template"
    assert data["rejected"], "invalid candidates must be reported"
    assert all(w["ai_generated"] is False for w in data["widgets"])


def test_generated_layout_is_persisted_and_readable(client):
    client.post("/api/connectors/aws/generate-widgets", json={"resource_id": "i-0abc123"})

    res = client.get("/api/connectors/aws/widgets?resource=i-0abc123")
    assert res.status_code == 200
    data = res.json()
    assert data["saved"] is True
    assert len(data["widgets"]) >= 3

    # A different resource scope must not see the saved layout.
    other = client.get("/api/connectors/aws/widgets?resource=i-other")
    assert other.json()["saved"] is False
    assert other.json()["widgets"] == []


def test_save_widget_layout_validates_and_persists(client):
    payload = {
        "resource_id": "i-0abc123",
        "widgets": [
            {"id": "cpu", "type": "gauge", "label": "CPU", "metric_keys": ["cpu"], "unit": "%"},
            {"id": "net", "type": "line_chart", "label": "Network", "metric_keys": ["NetworkIn"]},
        ],
    }
    res = client.put("/api/connectors/aws/widgets", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["saved"] is True
    assert [w["id"] for w in data["widgets"]] == ["cpu", "net"]
    assert all(w["ai_generated"] is False for w in data["widgets"])
    assert all("position" in w for w in data["widgets"])

    reloaded = client.get("/api/connectors/aws/widgets?resource=i-0abc123").json()
    assert [w["id"] for w in reloaded["widgets"]] == ["cpu", "net"]


def test_save_widget_layout_rejects_invalid_definitions_without_persisting(client):
    res = client.put(
        "/api/connectors/aws/widgets",
        json={"resource_id": "i-1", "widgets": [{"id": "bad", "type": "pie_chart", "label": "Pie"}]},
    )
    assert res.status_code == 400
    body = res.json()
    assert body["code"] == "WIDGET_VALIDATION_FAILED"
    assert body["detail"]["rejected"]

    # Nothing was persisted.
    assert client.get("/api/connectors/aws/widgets?resource=i-1").json()["saved"] is False


def test_save_widget_layout_requires_a_non_empty_list(client):
    res = client.put("/api/connectors/aws/widgets", json={"resource_id": "i-1", "widgets": []})
    assert res.status_code == 400
    assert res.json()["code"] == "BAD_REQUEST"
