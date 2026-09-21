#!/usr/bin/env python3
"""Setup Datadog monitor for Lear Demo (tasks/.demo/07_DATADOG_SETUP.md).

Creates or idempotently updates:
  1. "Lear Demo: checkout-api health"
     Watches kubernetes.containers.running for checkout-api in lear-demo.
     Alerts when < 1 running container.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    env = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'").strip('"')
                env[k] = v
    return env


def main() -> int:
    env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    creds = {**load_env(env_file), **os.environ}

    api_key = creds.get("DATADOG_API_KEY")
    app_key = creds.get("DATADOG_APP_KEY")
    site = creds.get("DATADOG_SITE") or "datadoghq.com"

    if not api_key or not app_key:
        print("Error: DATADOG_API_KEY and DATADOG_APP_KEY must be set", file=sys.stderr)
        return 1

    base_url = f"https://api.{site}"
    headers = {
        "DD-API-KEY": api_key,
        "DD-APPLICATION-KEY": app_key,
        "Content-Type": "application/json",
    }

    # Fetch existing monitors
    req = urllib.request.Request(f"{base_url}/api/v1/monitor", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            monitors = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Failed to fetch monitors: {e}", file=sys.stderr)
        return 1

    monitor_name = "Lear Demo: checkout-api health"
    existing = next((m for m in monitors if m.get("name") == monitor_name), None)

    # Monitor query: alert if running containers < 1 in checkout-api deployment
    query = "avg(last_1m):avg:kubernetes.containers.running{kube_deployment:checkout-api,kube_namespace:lear-demo} < 1"
    payload = {
        "name": monitor_name,
        "type": "metric alert",
        "query": query,
        "message": "checkout-api is down in lear-demo namespace (Kubernetes container down) @all",
        "tags": ["team:lear-demo", "env:staging", "service:checkout-api"],
        "options": {
            "thresholds": {"critical": 1},
            "notify_no_data": True,
            "no_data_timeframe": 2,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    if existing:
        mid = existing["id"]
        req = urllib.request.Request(f"{base_url}/api/v1/monitor/{mid}", data=data, headers=headers, method="PUT")
        action = "Updated"
    else:
        req = urllib.request.Request(f"{base_url}/api/v1/monitor", data=data, headers=headers, method="POST")
        action = "Created"

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            print(f"{action} monitor successfully:")
            print(f"  ID:    {result.get('id')}")
            print(f"  Name:  {result.get('name')}")
            print(f"  State: {result.get('overall_state')}")
            print(f"  Query: {result.get('query')}")
            print(f"  URL:   https://app.{site}/monitors/{result.get('id')}")
    except urllib.error.HTTPError as exc:
        print(f"HTTPError {exc.code}: {exc.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error creating monitor: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
