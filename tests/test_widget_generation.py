"""Tests for the dynamic AI widget generation endpoint."""
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest

from prash.server import app
from prash.connectors.base import ConnectorState, ResourceState


@pytest.fixture
def client():
    return TestClient(app)


def test_generate_widgets_unknown_connector_returns_404(client):
    res = client.post("/api/connectors/nonexistent/generate-widgets", json={})
    assert res.status_code == 404
    data = res.json()
    assert data["error"] is True
    assert data["code"] == "CONNECTOR_NOT_FOUND"


def test_generate_widgets_aws_returns_dynamic_layout(client):
    res = client.post(
        "/api/connectors/aws/generate-widgets",
        json={"resource_id": "i-0abc123", "prompt": "Focus on CPU and disk performance"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["connector_id"] == "aws"
    assert data["resource_id"] == "i-0abc123"
    widgets = data["widgets"]
    assert len(widgets) >= 3

    widget_types = [w["type"] for w in widgets]
    assert "gauge" in widget_types
    assert "line_chart" in widget_types

    # Ensure position attributes exist for grid rendering
    for w in widgets:
        assert "row" in w["position"]
        assert "col" in w["position"]
        assert "span" in w["position"]
        assert w["ai_generated"] is True


def test_widget_generator_validation_and_parsing():
    from prash.widget_generator import (
        build_generation_prompt,
        validate_widget_config,
        parse_and_validate_llm_response,
        WidgetPosition,
        WidgetConfig,
    )

    # 1. Prompt generation
    prompt = build_generation_prompt(
        connector_id="k8s",
        connector_name="Kubernetes",
        category="containers",
        capabilities=["metrics", "status"],
        available_metrics=["cpu_usage", "memory_usage"],
        current_status="healthy",
        user_prompt="Focus on memory leaks",
        existing_templates=[],
    )
    assert "Kubernetes" in prompt
    assert "Focus on memory leaks" in prompt
    assert "cpu_usage" in prompt

    # 2. Validation: valid widget
    valid_w = {
        "id": "test_1",
        "type": "gauge",
        "label": "CPU Gauge",
        "position": {"row": 0, "col": 0, "span": 1},
    }
    assert validate_widget_config(valid_w) is True

    # 3. Validation: invalid widget type
    invalid_w_type = {
        "id": "test_2",
        "type": "unsupported_type",
        "label": "Bad Widget",
        "position": {"row": 0, "col": 0, "span": 1},
    }
    assert validate_widget_config(invalid_w_type) is False

    # 4. Validation: invalid span (>3 or <1)
    invalid_w_span = {
        "id": "test_3",
        "type": "line_chart",
        "label": "Bad Span",
        "position": {"row": 0, "col": 0, "span": 5},
    }
    assert validate_widget_config(invalid_w_span) is False

    # 5. LLM Response parser
    llm_json = """
    ```json
    {
      "rationale": "High memory attention layout",
      "widgets": [
        {
          "id": "k8s_mem_gauge",
          "type": "gauge",
          "label": "Memory Usage",
          "metric_keys": ["memory_usage"],
          "position": {"row": 0, "col": 0, "span": 1}
        },
        {
          "id": "k8s_bad_widget",
          "type": "nonexistent",
          "label": "Ignored",
          "position": {"row": 0, "col": 1, "span": 1}
        },
        {
          "id": "k8s_trend",
          "type": "line_chart",
          "label": "Memory Trend",
          "metric_keys": ["memory_usage"],
          "position": {"row": 0, "col": 1, "span": 2}
        }
      ]
    }
    ```
    """
    parsed_widgets, rationale = parse_and_validate_llm_response(llm_json, "k8s")
    assert len(parsed_widgets) == 2  # The invalid one was rejected
    assert parsed_widgets[0].type == "gauge"
    assert parsed_widgets[1].type == "line_chart"
    assert rationale == "High memory attention layout"


def test_widget_yaml_persistence_crud(client, tmp_path, monkeypatch):
    """Verifies GET, PUT, and DELETE /api/connectors/{id}/widgets persistence against prash.yaml."""
    test_yaml = tmp_path / "prash.yaml"
    test_yaml.write_text("projects: []\n")
    monkeypatch.setattr("prash.server.YAML_PATH", str(test_yaml))
    monkeypatch.setattr("prash.widget_generator.DEFAULT_YAML_PATH", str(test_yaml))

    # 1. GET default widgets when none custom-saved
    res_get = client.get("/api/connectors/aws/widgets?resource_id=i-test123")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["custom"] is False
    assert len(data_get["widgets"]) >= 3

    # 2. PUT custom layout
    custom_widgets = [
        {
            "id": "custom_cpu_gauge",
            "type": "gauge",
            "label": "Custom High-Priority CPU",
            "metric_keys": ["CPUUtilization"],
            "unit": "%",
            "position": {"row": 0, "col": 0, "span": 1},
            "ai_generated": True,
        },
        {
            "id": "custom_disk_chart",
            "type": "line_chart",
            "label": "Disk Read/Write Ops",
            "metric_keys": ["DiskReadOps", "DiskWriteOps"],
            "unit": "ops",
            "position": {"row": 0, "col": 1, "span": 2},
            "ai_generated": True,
        },
    ]

    res_put = client.put(
        "/api/connectors/aws/widgets",
        json={"resource_id": "i-test123", "widgets": custom_widgets},
    )
    assert res_put.status_code == 200
    data_put = res_put.json()
    assert data_put["success"] is True
    assert data_put["count"] == 2

    # 3. GET custom layout returns saved widgets
    res_get_saved = client.get("/api/connectors/aws/widgets?resource_id=i-test123")
    assert res_get_saved.status_code == 200
    saved_data = res_get_saved.json()
    assert saved_data["custom"] is True
    assert len(saved_data["widgets"]) == 2
    assert saved_data["widgets"][0]["label"] == "Custom High-Priority CPU"

    # 4. DELETE custom layout resets to defaults
    res_del = client.delete("/api/connectors/aws/widgets?resource_id=i-test123")
    assert res_del.status_code == 200
    assert res_del.json()["reset"] is True

    # 5. GET returns custom: False again
    res_get_after = client.get("/api/connectors/aws/widgets?resource_id=i-test123")
    assert res_get_after.status_code == 200
    assert res_get_after.json()["custom"] is False

