from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

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

    # Watch surface (Phase 3 rollout): the already-active alert is baselined
    # silently by watch(), so the first poll is deduped silence; flipping the
    # alerts endpoint to empty turns the previously-firing instance into a
    # recovery -- resolved alerts leave the Alertmanager list entirely, so
    # absence IS the recovery signal.
    handle = connector.watch("ci-alert")
    assert handle.rule_uid == "ci-alert"
    assert handle.poll() == []

    _register_mapping(_grafana_mapping("GET", "/api/alertmanager/grafana/api/v2/alerts", [], priority=1))
    recovered = handle.poll()
    assert [e["event_type"] for e in recovered] == ["alert_recovered"]
    assert "no longer listed" in recovered[0]["summary"]

    # get_stats over the same mock: the annotation body references neither
    # the rule uid nor the title (unattributed -> omitted), and the active
    # alert carries no startsAt inside the window. An empty window is a
    # valid result, not an error.
    assert connector.get_stats("ci-alert") == []


def test_grafana_connector_get_stats_annotates_state_changes() -> None:
    _register_mapping(_grafana_mapping("GET", "/api/org", {"id": 1, "name": "CI Org"}))
    _register_mapping(
        _grafana_mapping(
            "GET",
            "/api/v1/provisioning/alert-rules",
            [{"uid": "ci-alert", "title": "CI Test Alert"}],
        )
    )
    ts = int(datetime(2026, 9, 9, 11, 0, tzinfo=timezone.utc).timestamp() * 1000)
    _register_mapping(
        _grafana_mapping(
            "GET",
            "/api/annotations",
            [
                # matched by title in text; Alerting -> alert_firing
                {"time": ts, "newState": "Alerting", "prevState": "Pending", "text": "CI Test Alert", "tags": []},
                # references neither uid nor title -> unattributed, omitted
                {"time": ts, "newState": "Alerting", "prevState": "Pending", "text": "other rule fired", "tags": ["other"]},
            ],
        )
    )
    _register_mapping(_grafana_mapping("GET", "/api/alertmanager/grafana/api/v2/alerts", []))

    connector = GrafanaConnector(
        {
            "GRAFANA_URL": os.environ["GRAFANA_URL"],
            "GRAFANA_API_KEY": os.environ["GRAFANA_API_KEY"],
        }
    )

    events = connector.get_stats("ci-alert", since=datetime(2026, 9, 9, 10, 0, tzinfo=timezone.utc))

    assert [e["event_type"] for e in events] == ["alert_firing"]
    assert "Pending -> Alerting" in events[0]["summary"]
    assert events[0]["timestamp"].isoformat() == "2026-09-09T11:00:00+00:00"


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
