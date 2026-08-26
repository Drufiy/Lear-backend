#!/usr/bin/env python3
"""Reusable PagerDuty failure fixture (TESTING_SETUP.md).

Fires a real event at the "prash-v2" service via the Events API v2
(PAGERDUTY_ROUTING_KEY), using a fixed dedup_key so repeated runs update
the same incident instead of piling up new ones each time. No mock -- this
is a genuine triggered/resolved incident on the real service.

    python3 scripts/testing/break_pagerduty.py          # trigger (open incident)
    python3 scripts/testing/break_pagerduty.py --heal   # resolve it

Resource name to investigate with: the PagerDuty service name, "prash-v2"
(not the dedup key -- poll_state() resolves by service, same as every
other connector's resource shape here).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

DEDUP_KEY = "prash-test-fixture"
SERVICE_NAME = "prash-v2"


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


def main() -> int:
    env = {**_env(os.path.join(os.path.dirname(__file__), "..", "..", ".env")), **os.environ}
    routing_key = env.get("PAGERDUTY_ROUTING_KEY")
    if not routing_key:
        print("PAGERDUTY_ROUTING_KEY not set", file=sys.stderr)
        return 1

    heal = "--heal" in sys.argv
    body = {
        "routing_key": routing_key,
        "dedup_key": DEDUP_KEY,
        "event_action": "resolve" if heal else "trigger",
    }
    if not heal:
        body["payload"] = {
            "summary": "Prash test fixture -- safe to acknowledge/resolve freely",
            "source": "scripts/testing/break_pagerduty.py",
            "severity": "critical",
            "custom_details": {"owner": "prash-test-fixture"},
        }

    req = urllib.request.Request(
        "https://events.pagerduty.com/v2/enqueue",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print(f"PagerDuty Events API {exc.code}: {exc.read().decode(errors='replace')[:400]}", file=sys.stderr)
        return 1

    print(f"event accepted: {raw}")
    if heal:
        print(f"resolve sent -- incident should close within seconds")
    else:
        print(f"trigger sent -- should appear as an open incident within seconds")
        print(f"check state: prash investigate '{SERVICE_NAME}' --provider pagerduty")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
