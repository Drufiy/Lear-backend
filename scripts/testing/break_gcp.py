#!/usr/bin/env python3
"""Reusable GCP Compute Engine failure fixture (TESTING_SETUP.md).

Owns one GCE instance end to end (tagged or named `prash-test-fixture`, or
the name given via --instance / GCP_INSTANCE_NAME). Force a REAL state
change on demand by stopping/starting the instance:

    break  -> stop the instance (gcloud compute instances stop). The
              connector maps STOPPED -> STABLE, so `prash investigate`
              reports a real, verifiable non-HEALTHY state.
    --heal -> start the instance again (gcloud compute instances start),
              restoring RUNNING -> HEALTHY.

Both go through the real `gcloud` CLI against the live project -- no mock.
The instance itself is unchanged; only its power state toggles, so the
fixture is cheap and safe to re-run.

    python3 scripts/testing/break_gcp.py [--instance <name>]          # stop (break)
    python3 scripts/testing/break_gcp.py [--instance <name>] --heal   # start (heal)

Requires GCP_PROJECT_ID and GCP_REGION (or GCP_ZONE) in .env, plus either
GOOGLE_APPLICATION_CREDENTIALS or `gcloud auth` on PATH. Resource name to
investigate with: the instance name, e.g.
`prash investigate <name> --provider gcp`.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

INSTANCE_TAG = "prash-test-fixture"


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
        "project": env.get("GCP_PROJECT_ID"),
        "zone": env.get("GCP_ZONE") or (env.get("GCP_REGION") + "-a" if env.get("GCP_REGION") else None),
        "instance": env.get("GCP_INSTANCE_NAME"),
    }


def _run_gcloud(args: list[str], project: str) -> subprocess.CompletedProcess:
    cmd = ["gcloud", "compute", "instances", *args, "--project", project, "--quiet"]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except FileNotFoundError:
        raise SystemExit("gcloud CLI not found on PATH -- install Google Cloud SDK or set GOOGLE_APPLICATION_CREDENTIALS") from None


def main() -> int:
    parser = argparse.ArgumentParser(description="Force/heal a real GCE instance state change (stop vs start).")
    parser.add_argument("--instance", help=f"GCE instance name (default: GCP_INSTANCE_NAME env, else '{INSTANCE_TAG}').")
    parser.add_argument("--zone", help="GCE zone (default: GCP_ZONE, else GCP_REGION + '-a').")
    parser.add_argument("--heal", action="store_true", help="Start the instance instead of stopping it.")
    args = parser.parse_args()

    creds = _load_creds()
    if not creds["project"]:
        print("GCP_PROJECT_ID not set", file=sys.stderr)
        return 1
    zone = args.zone or creds["zone"]
    if not zone:
        print("No zone given. Pass --zone, or set GCP_ZONE (or GCP_REGION) in .env", file=sys.stderr)
        return 1
    instance = args.instance or creds["instance"] or INSTANCE_TAG

    action = "start" if args.heal else "stop"
    print(f"gcloud: {action} instance '{instance}' in {zone} (project {creds['project']})")
    res = _run_gcloud([action, instance, "--zone", zone], creds["project"])
    if res.returncode != 0:
        print(f"gcloud {action} failed (exit {res.returncode}): {res.stderr.strip()[:400]}", file=sys.stderr)
        return 1

    print(res.stdout.strip())
    if args.heal:
        print("instance started -- poll_state() should report healthy (RUNNING) shortly")
    else:
        print("instance stopped -- poll_state() should report stable (STOPPED)")
        print(f"check state: prash investigate '{instance}' --provider gcp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
