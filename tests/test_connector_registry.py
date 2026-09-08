"""Unit and Completeness Tests for the Prash Connector Registry (Feature 02)."""
import os
import re
from pathlib import Path

import pytest

from prash.connector_registry import (
    CONNECTOR_REGISTRY,
    ConnectorRegistryEntry,
    discover_configured,
    get_connector,
    get_missing_fields,
    is_connector_configured,
    registry_to_json,
)
from prash.connectors.base import Connector


VALID_CATEGORIES = {"infrastructure", "cicd", "monitoring", "security", "iac"}
VALID_WIDGET_TYPES = {"gauge", "line_chart", "status_grid", "event_timeline", "metric_card", "bar_chart"}


def test_registry_has_all_13_connectors():
    expected = {
        "aws", "azure", "gcp", "kubernetes", "vercel",
        "github", "gitlab", "datadog", "grafana",
        "pagerduty", "snyk", "gitleaks", "terraform"
    }
    assert set(CONNECTOR_REGISTRY.keys()) == expected


def test_every_connector_has_name_and_id():
    for cid, entry in CONNECTOR_REGISTRY.items():
        assert entry.id == cid
        assert bool(entry.name.strip())


def test_every_connector_has_category():
    for cid, entry in CONNECTOR_REGISTRY.items():
        assert entry.category in VALID_CATEGORIES, f"{cid} has invalid category {entry.category}"


def test_every_connector_has_icon_and_color():
    color_regex = re.compile(r"^#[0-9a-fA-F]{6}$")
    for cid, entry in CONNECTOR_REGISTRY.items():
        assert bool(entry.icon.strip()), f"{cid} missing icon"
        assert color_regex.match(entry.color), f"{cid} has invalid hex color {entry.color}"


def test_every_connector_has_at_least_one_widget_template():
    for cid, entry in CONNECTOR_REGISTRY.items():
        assert len(entry.widget_templates) > 0, f"{cid} has no widget templates"
        for w in entry.widget_templates:
            assert w.type in VALID_WIDGET_TYPES, f"{cid} widget {w.id} has invalid type {w.type}"
            assert len(w.metric_keys) > 0, f"{cid} widget {w.id} has no metric keys"


def test_every_connector_class_is_importable():
    for cid, entry in CONNECTOR_REGISTRY.items():
        cls = entry.connector_class
        assert issubclass(cls, Connector), f"{cid} class {cls} does not inherit from Connector"


def test_every_auth_field_has_key_and_label():
    env_var_regex = re.compile(r"^[A-Z0-9_]+$")
    for cid, entry in CONNECTOR_REGISTRY.items():
        keys_seen = set()
        for f in entry.auth_fields:
            assert bool(f.label.strip()), f"{cid} field {f.key} missing label"
            assert env_var_regex.match(f.key), f"{cid} field key '{f.key}' is not a valid env var name"
            assert f.key not in keys_seen, f"{cid} has duplicate auth field {f.key}"
            keys_seen.add(f.key)


def test_discover_configured_with_empty_env():
    configured = discover_configured({})
    # Empty env should have zero configured services
    assert configured == []


def test_discover_configured_with_full_env():
    full_env = {
        "AWS_ACCESS_KEY_ID": "AKIA...",
        "AWS_SECRET_ACCESS_KEY": "secret",
        "AZURE_SUBSCRIPTION_ID": "sub",
        "AZURE_TENANT_ID": "tenant",
        "AZURE_CLIENT_ID": "client",
        "AZURE_CLIENT_SECRET": "sec",
        "GCP_PROJECT_ID": "proj",
        "VERCEL_TOKEN": "tok",
        "GITHUB_TOKEN": "ghp",
        "GITLAB_TOKEN": "glp",
        "DATADOG_API_KEY": "ddkey",
        "DATADOG_APP_KEY": "ddapp",
        "GRAFANA_URL": "http://grafana",
        "GRAFANA_API_KEY": "gkey",
        "PAGERDUTY_API_KEY": "pdkey",
        "SNYK_API_TOKEN": "snykkey",
        "SNYK_ORG_ID": "snykorg",
        "GITLEAKS_BINARY": "gitleaks",
        "TERRAFORM_STATE_PATH": ".",
    }
    configured = discover_configured(full_env)
    assert "aws" in configured
    assert "azure" in configured
    assert "gcp" in configured
    assert "vercel" in configured
    assert "github" in configured
    assert "gitlab" in configured
    assert "datadog" in configured
    assert "grafana" in configured
    assert "pagerduty" in configured
    assert "snyk" in configured
    assert "gitleaks" in configured
    assert "terraform" in configured


def test_discover_configured_with_partial_env():
    # Only AWS access key provided (missing secret key) -> not configured
    partial_env = {"AWS_ACCESS_KEY_ID": "AKIA..."}
    assert not is_connector_configured("aws", partial_env)
    assert "AWS_SECRET_ACCESS_KEY" in get_missing_fields("aws", partial_env)


def test_registry_to_json_shape():
    json_data = registry_to_json({})
    assert len(json_data) == 13
    for item in json_data:
        assert "id" in item
        assert "name" in item
        assert "category" in item
        assert "status" in item
        assert "auth_fields" in item
        assert "widget_templates" in item
        assert "supports_watch" in item
        assert "supports_stats" in item
        assert "supports_execute" in item


def test_EVERY_CONNECTOR_IN_PRASH_CONNECTORS_IS_REGISTERED():
    connectors_dir = Path(__file__).parent.parent / "prash" / "connectors"
    py_files = [
        f.stem for f in connectors_dir.glob("*.py")
        if f.stem not in ("__init__", "base")
    ]
    registered = set(CONNECTOR_REGISTRY.keys())
    for py_file in py_files:
        assert py_file in registered, f"Connector module {py_file}.py is not registered in CONNECTOR_REGISTRY!"
