#!/usr/bin/env python3
"""Reusable Grafana failure fixture (TESTING_SETUP.md).

Manages one alert rule, "Prash E2E Test Alert" (this rule already existed
from an earlier session -- this script just makes it toggleable instead of
permanently firing). The rule's condition is a pure math expression, no
external datasource needed, so this owns the rule end to end: no real
service is touched.

    python3 scripts/testing/break_grafana.py          # force Alert (1 > 0, always true)
    python3 scripts/testing/break_grafana.py --heal    # force OK (1 > 2, always false)

Unlike Datadog, there's no separate "submit a metric point" step -- the
rule's own query defines the value, so toggling it takes effect on Grafana's
next evaluation cycle for the rule's group (seconds, not the ~1-5min a
metric-based monitor needs to notice a new data point).

Grafana Cloud free tier hibernates when idle: a 503 "instance is loading"
on the first call after idle time is expected, not a bug -- it clears
within ~1min of the instance waking up. This script does not retry that
automatically; just re-run it if you see one.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

RULE_TITLE = "Prash E2E Test Alert"
RULE_UID = "afw5nq4yyq0owb"
FOLDER_UID = "cfvxtqfcnbq4gf"
RULE_GROUP = "prash-e2e-test"


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
        raise RuntimeError(f"Grafana API {exc.code}: {exc.read().decode(errors='replace')[:400]}") from exc


def main() -> int:
    env = {**_env(os.path.join(os.path.dirname(__file__), "..", "..", ".env")), **os.environ}
    url = (env.get("GRAFANA_URL") or "").rstrip("/")
    api_key = env.get("GRAFANA_API_KEY")
    if not url or not api_key:
        print("GRAFANA_URL / GRAFANA_API_KEY not set", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    heal = "--heal" in sys.argv
    expression = "1 > 2" if heal else "1 > 0"

    payload = {
        "uid": RULE_UID,
        "orgID": 1,
        "folderUID": FOLDER_UID,
        "ruleGroup": RULE_GROUP,
        "title": RULE_TITLE,
        "condition": "A",
        "data": [{
            "refId": "A",
            "queryType": "",
            "relativeTimeRange": {"from": 600, "to": 0},
            "datasourceUid": "__expr__",
            "model": {"expression": expression, "intervalMs": 1000, "maxDataPoints": 43200, "refId": "A", "type": "math"},
        }],
        "noDataState": "OK",
        "execErrState": "Error",
        "for": "0s",
        "annotations": {"summary": "Prash end-to-end test alert -- always fires unless healed, safe to silence/delete freely."},
        "labels": {"env": "prash-e2e-test"},
    }

    _request(url, headers, "PUT", f"/api/v1/provisioning/alert-rules/{RULE_UID}", payload)
    print(f"rule updated: expression={expression!r}")

    if heal:
        print("condition is now always-false -- should settle to no active alert within one evaluation cycle (seconds)")
    else:
        print("condition is now always-true -- should fire Alert within one evaluation cycle (seconds)")
        print(f"check state: prash investigate '{RULE_TITLE}' --provider grafana")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
