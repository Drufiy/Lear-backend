#!/usr/bin/env python3
"""Reusable GCP failure fixture (TESTING_SETUP.md).

Owns one GCP instance end to end (target instance given via --instance-name).
Force a REAL failure state on demand -- an unhealthy systemd-ish unit simulated by a
marker file plus a runaway background process -- then heal it back.

The failure is deliberately service-level, not instance-level: the box
stays reachable so the diagnose path has real logs to read, while
poll_state() can report degraded/failed. No mock -- this is a genuine
broken service on a real instance.

    python3 scripts/testing/break_gcp.py --instance-name drufiy-proxy          # force failure
    python3 scripts/testing/break_gcp.py --instance-name drufiy-proxy --heal   # restore

"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

MARKER = "/tmp/prash-test-fixture-break"
WATCHDOG = "/tmp/prash-test-fixture-watchdog.log"
SERVICE = "prash-test-fixture.service"

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
        "gcp_project_id": env.get("GCP_PROJECT_ID"),
        "gcp_region": env.get("GCP_REGION", "us-central1"),
        "google_application_credentials": env.get("GOOGLE_APPLICATION_CREDENTIALS"),
    }

def _resolve_zone(project: str, instance: str, creds: dict) -> str | None:
    gcloud_cmd = "gcloud.cmd" if os.name == "nt" else "gcloud"
    cmd_list = [gcloud_cmd, "compute", "instances", "list", "--project", project, f'--filter=name="{instance}"', '--format="value(zone)"']
    env = os.environ.copy()
    if creds.get("google_application_credentials"):
        env["GOOGLE_APPLICATION_CREDENTIALS"] = creds["google_application_credentials"]
    try:
        res = subprocess.run(
            " ".join(cmd_list) if os.name == "nt" else cmd_list,
            capture_output=True, text=True, check=True, shell=(os.name == "nt"), env=env
        )
        zone = res.stdout.strip().split('/')[-1]
        return zone if zone else None
    except subprocess.CalledProcessError:
        return None

def main() -> int:
    parser = argparse.ArgumentParser(description="Force/heal a real failure state on the prash GCP test instance.")
    parser.add_argument("--instance-name", required=True, help="Target GCP instance name.")
    parser.add_argument("--heal", action="store_true", help="Restore the instance instead of breaking it.")
    parser.add_argument("--ip", help="External IP for SSH fallback.")
    parser.add_argument("--pem", help="PEM key path for SSH fallback.")
    args = parser.parse_args()

    creds = _load_creds()
    if not creds["gcp_project_id"]:
        print("GCP_PROJECT_ID not set", file=sys.stderr)
        return 1

    zone = _resolve_zone(creds["gcp_project_id"], args.instance_name, creds)
    
    def run(command: str) -> dict:
        if args.ip and args.pem:
            ssh_cmd = [
                "ssh", "-i", args.pem,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                f"ubuntu@{args.ip}",
                command
            ]
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=False)
            return {"status": "Success" if result.returncode == 0 else "Failed",
                    "stdout": result.stdout, "stderr": result.stderr}
        
        if not zone:
            print(f"Could not find zone for instance {args.instance_name}, provide --ip and --pem for fallback", file=sys.stderr)
            sys.exit(1)

        gcloud_cmd = "gcloud.cmd" if os.name == "nt" else "gcloud"
        ssh_cmd = [
            gcloud_cmd, "compute", "ssh", args.instance_name,
            "--zone", zone,
            "--project", creds["gcp_project_id"],
            "--command", command,
            "--quiet"
        ]
        env = os.environ.copy()
        if creds.get("google_application_credentials"):
            env["GOOGLE_APPLICATION_CREDENTIALS"] = creds["google_application_credentials"]
        result = subprocess.run(
            " ".join(ssh_cmd) if os.name == "nt" else ssh_cmd,
            capture_output=True, text=True, check=False, shell=(os.name == "nt"), env=env
        )
        return {"status": "Success" if result.returncode == 0 else "Failed",
                "stdout": result.stdout, "stderr": result.stderr}

    if args.heal:
        script = f"""
set -e
rm -f {MARKER}
if systemctl list-unit-files | grep -q '{SERVICE}'; then
  sudo systemctl stop {SERVICE} 2>/dev/null || true
  sudo systemctl disable {SERVICE} 2>/dev/null || true
  sudo rm -f /etc/systemd/system/{SERVICE}
  sudo systemctl daemon-reload 2>/dev/null || true
fi
sudo pkill -f 'prash-test-fixture-loop' 2>/dev/null || true
rm -f {WATCHDOG}
echo healed
"""
        res = run(script)
        print(f"heal command status: {res.get('status')}")
        if res.get("stderr", "").strip():
            print(f"stderr: {res['stderr'].strip()}")
        print("instance restored -- poll_state() should settle back to HEALTHY shortly")
        return 0

    script = f"""
set -e
sudo cat > /tmp/{SERVICE} <<'EOF'
[Unit]
Description=Prash test fixture simulated service
After=network.target

[Service]
Type=simple
ExecStart=/bin/sh -c 'while true; do echo "prash-test-fixture-loop watchdog tick: $(date -u +%%H:%%M:%%S)"; echo "prash-test-fixture-loop watchdog tick: $(date -u +%%H:%%M:%%S)" >> {WATCHDOG}; sleep 1; done'
Restart=always
EOF
sudo mv /tmp/{SERVICE} /etc/systemd/system/{SERVICE}
sudo systemctl daemon-reload
sudo systemctl enable {SERVICE} >/dev/null 2>&1 || true
sudo systemctl start {SERVICE}
touch {MARKER}
sleep 2
sudo systemctl status {SERVICE} --no-pager | head -n 8 || true
echo '--- watchdog ---'
tail -n 3 {WATCHDOG} 2>/dev/null || echo '(no watchdog log yet)'
"""
    res = run(script)
    print(f"break command status: {res.get('status')}")
    if res.get("stderr", "").strip():
        print(f"stderr: {res['stderr'].strip()}")
    print(f"failure state forced on {args.instance_name} -- a fake service is now 'running' but wedged")
    print(f"check state: prash investigate '{args.instance_name}' --provider gcp")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
