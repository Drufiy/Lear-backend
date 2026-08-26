#!/usr/bin/env python3
"""Reusable Datadog failure fixture (TESTING_SETUP.md).

Creates (idempotently) one monitor, `prash-test-synthetic-error-rate`, on a
synthetic custom metric this script owns end to end -- no real service is
touched. Run with no args to force it into Alert; `--heal` submits a clean
value so it settles back to OK. Safe to re-run any number of times.

    python3 scripts/testing/break_datadog.py          # force Alert
    python3 scripts/testing/break_datadog.py --heal    # back to OK
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

MONITOR_NAME = "prash-test-synthetic-error-rate"
METRIC_NAME = "prash.test.synthetic_error_rate"


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


def _request(base_url: str, headers: dict, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Datadog API {exc.code}: {exc.read().decode(errors='replace')[:400]}") from exc


def main() -> int:
    env = {**_env(os.path.join(os.path.dirname(__file__), "..", "..", ".env")), **os.environ}
    api_key = env.get("DATADOG_API_KEY")
    app_key = env.get("DATADOG_APP_KEY")
    site = env.get("DATADOG_SITE") or "datadoghq.com"
    if not api_key or not app_key:
        print("DATADOG_API_KEY / DATADOG_APP_KEY not set", file=sys.stderr)
        return 1

    base_url = f"https://api.{site}"
    headers = {
        "DD-API-KEY": api_key,
        "DD-APPLICATION-KEY": app_key,
        "Content-Type": "application/json",
    }

    heal = "--heal" in sys.argv
    value = 0 if heal else 999

    now = int(time.time())
    _request(base_url, headers, "POST", "/api/v1/series", {
        "series": [{
            "metric": METRIC_NAME,
            "type": "gauge",
            "points": [[now, value]],
            "tags": ["source:prash-test-fixture"],
        }]
    })
    print(f"submitted {METRIC_NAME}={value}")

    monitors = _request(base_url, headers, "GET", "/api/v1/monitor")
    existing = next((m for m in monitors if m.get("name") == MONITOR_NAME), None)

    query = f"avg(last_5m):avg:{METRIC_NAME}{{*}} > 50"
    payload = {
        "name": MONITOR_NAME,
        "type": "metric alert",
        "query": query,
        "message": "Prash test fixture -- safe to ignore/mute, owned by scripts/testing/break_datadog.py",
        "tags": ["prash:test-fixture"],
        "options": {"thresholds": {"critical": 50}, "notify_no_data": False},
    }
    if existing:
        _request(base_url, headers, "PUT", f"/api/v1/monitor/{existing['id']}", payload)
        monitor_id = existing["id"]
        print(f"monitor exists: id={monitor_id}")
    else:
        created = _request(base_url, headers, "POST", "/api/v1/monitor", payload)
        monitor_id = created["id"]
        print(f"monitor created: id={monitor_id}")

    if heal:
        print("submitted a clean value -- monitor will settle to OK within ~5min")
    else:
        print(f"submitted an over-threshold value -- monitor should show Alert within ~1-5min")
        print(f"check state: prash investigate '{MONITOR_NAME}' --provider datadog")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
