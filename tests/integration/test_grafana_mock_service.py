from __future__ import annotations

import json
import os
import urllib.request

import pytest

from prash.connectors.base import ConnectorState
from prash.connectors.grafana import GrafanaConnector


WIREMOCK_BASE_URL = os.getenv("WIREMOCK_BASE_URL")
pytestmark = pytest.mark.skipif(not WIREMOCK_BASE_URL, reason="WireMock is not configured")


@pytest.fixture(autouse=True)
def _reset_mappings() -> None:
    request = urllib.request.Request(
        f"{WIREMOCK_BASE_URL}/__admin/mappings",
        method="DELETE",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 200


def _register_mapping(mapping: dict) -> None:
    request = urllib.request.Request(
        f"{WIREMOCK_BASE_URL}/__admin/mappings",
        data=json.dumps(mapping).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 201


def _grafana_mapping(
    method: str,
    path: str,
    body: object,
    body_patterns: list[dict] | None = None,
    status: int = 200,
    priority: int | None = None,
) -> dict:
    request: dict = {
        "method": method,
        "urlPath": path,
        "headers": {"Authorization": {"equalTo": "Bearer ci-test-token"}},
    }
    if body_patterns:
        request["bodyPatterns"] = body_patterns
    mapping = {
        "request": request,
        "response": {
            "status": status,
            "headers": {"Content-Type": "application/json"},
            "jsonBody": body,
        },
    }
    if priority is not None:
        mapping["priority"] = priority
    return mapping


def test_grafana_connector_lifecycle_over_http() -> None:
    _register_mapping(_grafana_mapping("GET", "/api/org", {"id": 1, "name": "CI Org"}))
    _register_mapping(
        _grafana_mapping(
            "GET",
            "/api/v1/provisioning/alert-rules",
            [{"uid": "ci-alert", "title": "CI Test Alert"}],
        )
    )
    _register_mapping(
        _grafana_mapping(
            "GET",
            "/api/alertmanager/grafana/api/v2/alerts",
            [{"labels": {"alertname": "CI Test Alert"}, "status": {"state": "active"}}],
        )
    )
    _register_mapping(
        _grafana_mapping(
            "GET",
            "/api/annotations",
            [{"time": 1000, "text": "CI deployment"}],
        )
    )
    _register_mapping(
        _grafana_mapping(
            "POST",
            "/api/alertmanager/grafana/api/v2/silences",
            {"silenceID": "ci-silence-1"},
            [
                {"matchesJsonPath": "$.matchers[?(@.name == 'alertname' && @.value == 'CI Test Alert')]"},
                {"matchesJsonPath": "$.startsAt"},
                {"matchesJsonPath": "$.endsAt"},
            ],
        )
    )

    connector = GrafanaConnector(
        {
            "GRAFANA_URL": os.environ["GRAFANA_URL"],
            "GRAFANA_API_KEY": os.environ["GRAFANA_API_KEY"],
        }
    )

    assert connector.authenticate() is True
    assert connector.locate("ci-alert") == {"uid": "ci-alert", "title": "CI Test Alert"}

    state = connector.poll_state("ci-alert")
    assert state.state == ConnectorState.FAILED
    assert state.detail["active_alert_count"] == 1

    assert connector.fetch_logs("ci-alert") == ["1000 CI deployment"]
    assert connector.silence_alert("ci-alert", minutes=30)["silenceID"] == "ci-silence-1"


def test_grafana_connector_reports_unknown_on_alert_api_failure() -> None:
    _register_mapping(
        _grafana_mapping(
            "GET",
            "/api/v1/provisioning/alert-rules",
            [{"uid": "ci-failing-alert", "title": "CI Failing Alert"}],
        )
    )
    _register_mapping(
        _grafana_mapping(
            "GET",
            "/api/alertmanager/grafana/api/v2/alerts",
            {"message": "forced CI failure"},
            status=500,
            priority=1,
        )
    )

    connector = GrafanaConnector(
        {
            "GRAFANA_URL": os.environ["GRAFANA_URL"],
            "GRAFANA_API_KEY": os.environ["GRAFANA_API_KEY"],
        }
    )

    state = connector.poll_state("ci-failing-alert")

    assert state.state == ConnectorState.UNKNOWN
    assert state.detail == {
        "uid": "ci-failing-alert",
        "title": "CI Failing Alert",
        "error": "could not fetch alert state",
    }
