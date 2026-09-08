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
