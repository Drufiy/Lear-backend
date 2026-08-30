#!/usr/bin/env python3
"""Reusable Vercel failure fixture (TESTING_SETUP.md).

Vercel has no "incident" toggle like PagerDuty/Datadog -- the natural
failure/recovery pair is redeploy vs rollback, exactly the two write actions
the connector live-verified in the 2026-08-24 E2E sprint. So this fixture:

    break  -> create a fresh deployment (redeploy the current production
              deployment). A new deployment is real infrastructure churn
              and makes poll_state() report a non-READY state briefly.
    --heal -> roll production back to the deployment that was live before
              the break, restoring the prior state.

Both go through Vercel's real API (same endpoints VercelConnector uses):
redeploy = POST /v13/deployments {deploymentId, name}; rollback =
POST /v9/projects/{id}/rollback/{deploymentId}. No mock.

    python3 scripts/testing/break_vercel.py [--project <name>]          # redeploy (break)
    python3 scripts/testing/break_vercel.py [--project <name>] --heal   # rollback (heal)

Requires VERCEL_TOKEN in .env (and optionally VERCEL_PROJECT, or pass
--project). Resource name to investigate with: the Vercel project name,
e.g. `prash investigate <project> --provider vercel`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API_URL = "https://api.vercel.com"


def _env(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not os.path.exists(path):
        return out
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _load_creds() -> dict[str, str]:
    repo_env = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env = {**_env(repo_env), **os.environ}
    return {
        "token": env.get("VERCEL_TOKEN"),
        "project": env.get("VERCEL_PROJECT"),
    }


def _request(token: str, method: str, path: str, body: dict | None = None) -> dict:
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{API_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"Vercel API {exc.code}: {exc.read().decode(errors='replace')[:400]}"
        ) from exc


def _latest_deployment(token: str, project: str) -> str:
    resp = _request(token, "GET", f"/v1/deployments?projectId={project}&limit=1")
    items = resp.get("deployments", []) if isinstance(resp, dict) else []
    if not items:
        raise SystemExit(f"no deployments found for project {project}")
    return items[0]["uid"]


def _production_deployment(token: str, project: str) -> str | None:
    """The deployment currently aliased to production (targets.production.id)
    -- the rollback target, NOT the most-recent deployment."""
    resp = _request(token, "GET", f"/v9/projects/{project}")
    return (resp.get("targets") or {}).get("production", {}).get("id")


def main() -> int:
    parser = argparse.ArgumentParser(description="Force/heal real Vercel deployment churn (redeploy vs rollback).")
    parser.add_argument("--project", help="Vercel project id or name (default: VERCEL_PROJECT env).")
    parser.add_argument("--heal", action="store_true", help="Roll production back to the pre-break deployment instead of redeploying.")
    args = parser.parse_args()

    creds = _load_creds()
    if not creds["token"]:
        print("VERCEL_TOKEN not set", file=sys.stderr)
        return 1
    project = args.project or creds["project"]
    if not project:
        print(
            "No project given. Pass --project <name> or set VERCEL_PROJECT in .env "
            "(the 2026-08-24 sprint project may no longer be current -- re-check with "
            "`prash investigate <project> --provider vercel` first).",
            file=sys.stderr,
        )
        return 1

    if args.heal:
        # Roll back to whatever was production BEFORE the last break. We need
        # the deployment list ordered newest-first and the pre-break one is
        # the second entry (the break created the newest). If production is
        # already the pre-break deployment, this is a no-op-ish safety.
        deploys = _request(token=creds["token"], method="GET", path=f"/v1/deployments?projectId={project}&limit=2")
        items = deploys.get("deployments", []) if isinstance(deploys, dict) else []
        if len(items) < 2:
            print("fewer than 2 deployments -- nothing to roll back to", file=sys.stderr)
            return 1
        target = items[1]["uid"]
        print(f"rolling production back to deployment {target} (pre-break)")
        resp = _request(creds["token"], "POST", f"/v9/projects/{project}/rollback/{target}")
        print(f"rollback response: {resp}")
        print(f"check state: prash investigate '{project}' --provider vercel")
        return 0

    # Break: redeploy the current production deployment (creates a new one).
    prod_id = _production_deployment(creds["token"], project)
    target = prod_id or _latest_deployment(creds["token"], project)
    print(f"redeploying deployment {target} (new deployment will be created)")
    resp = _request(creds["token"], "POST", "/v13/deployments", {"deploymentId": target, "name": project})
    new_id = resp.get("id") or resp.get("uid") or "?"
    print(f"new deployment created: {new_id}")
    print(f"check state: prash investigate '{project}' --provider vercel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
