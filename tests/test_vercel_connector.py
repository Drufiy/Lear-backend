"""Vercel connector (redeploy/rollback added Sprint 2 Tier 3, PRASH_V2.md
§7b). Same monkeypatched-urlopen style as the other connector tests."""

from __future__ import annotations

import json
import urllib.request

from prash.connectors.vercel import VercelConnector


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _sequenced_urlopen(monkeypatch, bodies: list[bytes]):
    calls = []
    index = {"i": 0}

    def fake_urlopen(req, timeout=30):
        calls.append(req)
        body = bodies[index["i"]]
        index["i"] += 1
        return _FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


def _capture_urlopen(monkeypatch, body: bytes = b"{}"):
    return _sequenced_urlopen(monkeypatch, [body])


def test_redeploy_with_explicit_deployment_id(monkeypatch):
    calls = _capture_urlopen(monkeypatch, json.dumps({"id": "dpl_new", "readyState": "QUEUED"}).encode())
    vc = VercelConnector({"VERCEL_TOKEN": "t"})
    result = vc.redeploy("my-app", deployment_id="dpl_old")
    assert result["id"] == "dpl_new"
    assert calls[0].full_url == "https://api.vercel.com/v13/deployments"
    payload = json.loads(calls[0].data)
    assert payload == {"deploymentId": "dpl_old", "name": "my-app"}


def test_redeploy_defaults_to_latest_deployment(monkeypatch):
    bodies = [
        json.dumps({"deployments": [{"uid": "dpl_latest"}]}).encode(),
        json.dumps({"id": "dpl_new"}).encode(),
    ]
    calls = _sequenced_urlopen(monkeypatch, bodies)
    vc = VercelConnector({"VERCEL_TOKEN": "t"})
    vc.redeploy("my-app")
    assert "v1/deployments?projectId=my-app" in calls[0].full_url
    payload = json.loads(calls[1].data)
    assert payload["deploymentId"] == "dpl_latest"


def test_redeploy_raises_when_no_deployments_exist(monkeypatch):
    from prash.connectors.vercel import VercelError

    _capture_urlopen(monkeypatch, json.dumps({"deployments": []}).encode())
    vc = VercelConnector({"VERCEL_TOKEN": "t"})
    try:
        vc.redeploy("my-app")
        assert False, "expected VercelError"
    except VercelError as exc:
        assert "no deployments found" in str(exc)


def test_rollback_hits_dedicated_rollback_endpoint(monkeypatch):
    calls = _capture_urlopen(monkeypatch, json.dumps({"status": "in-progress"}).encode())
    vc = VercelConnector({"VERCEL_TOKEN": "t"})
    vc.rollback("my-app", "dpl_previous")
    assert calls[0].full_url == "https://api.vercel.com/v9/projects/my-app/rollback/dpl_previous"
    assert calls[0].get_method() == "POST"
