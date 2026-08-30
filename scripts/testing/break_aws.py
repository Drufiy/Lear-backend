#!/usr/bin/env python3
"""Reusable AWS EC2 failure fixture (TESTING_SETUP.md).

Owns one EC2 instance end to end (tagged Name=prash-test-fixture, or the
instance id given via EC2_INSTANCE_ID / --instance-id). Force a REAL
failure state on demand -- an unhealthy systemd-ish unit simulated by a
marker file plus a runaway background process -- then heal it back.

The failure is deliberately service-level, not instance-level: the box
stays reachable so the diagnose path has real logs to read, while
poll_state() can report degraded/failed. No mock -- this is a genuine
broken service on a real instance.

    python3 scripts/testing/break_aws.py [--instance-id i-xxxx]          # force failure
    python3 scripts/testing/break_aws.py [--instance-id i-xxxx] --heal   # restore

Resource name to investigate with: the instance Name tag, "prash-test-fixture"
(or its instance id -- poll_state() resolves by either, same as every other
connector's resource shape here).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import boto3  # noqa: E402  # import after sys.path manipulation

INSTANCE_TAG = "prash-test-fixture"
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
        "aws_access_key_id": env.get("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": env.get("AWS_SECRET_ACCESS_KEY"),
        "region": env.get("AWS_REGION", "us-east-1"),
    }


def _ec2_client(creds):
    return boto3.client(
        "ec2",
        aws_access_key_id=creds["aws_access_key_id"],
        aws_secret_access_key=creds["aws_secret_access_key"],
        region_name=creds["region"],
    )


def _ssm_client(creds):
    return boto3.client(
        "ssm",
        aws_access_key_id=creds["aws_access_key_id"],
        aws_secret_access_key=creds["aws_secret_access_key"],
        region_name=creds["region"],
    )


def _resolve_instance(ec2, instance_id: str | None) -> str | None:
    if instance_id:
        return instance_id
    # EC2_INSTANCE_ID env override, then a Name-tagged fixture
    env_id = os.environ.get("EC2_INSTANCE_ID")
    if env_id:
        return env_id
    resp = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [INSTANCE_TAG]},
            {"Name": "instance-state-name", "Values": ["running"]},
        ]
    )
    instances = [
        i["InstanceId"]
        for r in resp.get("Reservations", [])
        for i in r.get("Instances", [])
        if i.get("State", {}).get("Name") == "running"
    ]
    if not instances:
        print(
            f"No running EC2 instance tagged Name={INSTANCE_TAG} found. "
            "Create one, or pass --instance-id / set EC2_INSTANCE_ID.",
            file=sys.stderr,
        )
        return None
    return instances[0]


def _run_ssm(ssm, instance_id: str, command: str) -> dict:
    """Run a command via SSM and wait for completion. Returns {status, stdout, stderr}."""
    send = ssm.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        Parameters={"commands": [command]},
        TimeoutSeconds=60,
    )
    command_id = send["Command"]["CommandId"]
    # Poll until the invocation finishes (in a subprocess we can block; this is a CLI script).
    for _ in range(30):
        time.sleep(2)
        inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
        status = inv.get("Status")
        if status not in ("Pending", "InProgress"):
            return {
                "status": status,
                "stdout": inv.get("StandardOutputContent", ""),
                "stderr": inv.get("StandardErrorContent", ""),
            }
    return {"status": "Timeout", "stdout": "", "stderr": "timed out waiting for SSM"}


def _ensure_ssm_agent(ssm, instance_id: str) -> bool:
    """Make sure the SSM agent is present; if not, fall back to SSH via a PEM."""
    res = _run_ssm(ssm, instance_id, "echo ssm-ok")
    return res.get("status") == "Success"


def _public_ip(ec2, instance_id: str) -> str:
    """Resolve the instance's public IPv4 address (required for SSH)."""
    resp = ec2.describe_instances(InstanceIds=[instance_id])
    try:
        ip = resp["Reservations"][0]["Instances"][0]["PublicIpAddress"]
    except (KeyError, IndexError):
        raise SystemExit(
            f"Instance {instance_id} has no public IP assigned -- cannot use the SSH fallback path."
        )
    if not ip:
        raise SystemExit(
            f"Instance {instance_id} has no public IP assigned -- cannot use the SSH fallback path."
        )
    return ip


def main() -> int:
    parser = argparse.ArgumentParser(description="Force/heal a real failure state on the prash AWS test instance.")
    parser.add_argument("--instance-id", help="Target EC2 instance id (default: EC2_INSTANCE_ID env, else Name tag).")
    parser.add_argument("--pem", help="Path to an SSH .pem for the SSH-fallback path (only if SSM agent is absent).")
    parser.add_argument("--heal", action="store_true", help="Restore the instance instead of breaking it.")
    args = parser.parse_args()

    creds = _load_creds()
    if not creds["aws_access_key_id"] or not creds["aws_secret_access_key"]:
        print("AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set", file=sys.stderr)
        return 1

    ec2 = _ec2_client(creds)
    instance_id = _resolve_instance(ec2, args.instance_id)
    if not instance_id:
        return 1

    ssm = _ssm_client(creds)

    # Establish reachability. Prefer SSM; if the agent is missing, use SSH
    # (the exact fallback path execute-aws exercises) when a --pem is given.
    use_ssh = False
    if not _ensure_ssm_agent(ssm, instance_id):
        if not args.pem:
            print(
                "SSM agent not reachable and no --pem given -- cannot run commands. "
                "Pass --pem to exercise the SSH fallback path.",
                file=sys.stderr,
            )
            return 1
        use_ssh = True

    def run(command: str) -> dict:
        if use_ssh:
            ssh_cmd = [
                "ssh", "-i", args.pem,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                f"ubuntu@{_public_ip(ec2, instance_id)}",
                command,
            ]
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=False)
            return {"status": "Success" if result.returncode == 0 else "Failed",
                    "stdout": result.stdout, "stderr": result.stderr}
        return _run_ssm(ssm, instance_id, command)

    if args.heal:
        script = f"""
set -e
rm -f {MARKER}
if systemctl list-unit-files | grep -q '{SERVICE}'; then
  systemctl stop {SERVICE} 2>/dev/null || true
  systemctl disable {SERVICE} 2>/dev/null || true
  rm -f /etc/systemd/system/{SERVICE}
  systemctl daemon-reload 2>/dev/null || true
fi
pkill -f 'prash-test-fixture-loop' 2>/dev/null || true
rm -f {WATCHDOG}
echo healed
"""
        res = run(script)
        print(f"heal command status: {res.get('status')}")
        if res.get("stderr", "").strip():
            print(f"stderr: {res['stderr'].strip()}")
        print("instance restored -- poll_state() should settle back to HEALTHY shortly")
        return 0

    # Break: install a fake systemd unit whose ExecStart is a background loop
    # that logs a watchdog line each second to BOTH journald and the on-disk
    # watchdog file. The unit's Type is simple and it keeps running, so
    # systemctl sees it as "active (running)" while the app it simulates is
    # genuinely wedged -- and the watchdog file gives the diagnosis brain
    # (and execute-aws / fetch_logs) real lines to read.
    script = f"""
set -e
cat > /etc/systemd/system/{SERVICE} <<'EOF'
[Unit]
Description=Prash test fixture simulated service
After=network.target

[Service]
Type=simple
ExecStart=/bin/sh -c 'while true; do echo "prash-test-fixture-loop watchdog tick: $(date -u +%%H:%%M:%%S)"; echo "prash-test-fixture-loop watchdog tick: $(date -u +%%H:%%M:%%S)" >> {WATCHDOG}; sleep 1; done'
Restart=always
EOF
systemctl daemon-reload
systemctl enable {SERVICE} >/dev/null 2>&1 || true
systemctl start {SERVICE}
touch {MARKER}
sleep 2
systemctl status {SERVICE} --no-pager | head -n 8 || true
echo '--- watchdog ---'
tail -n 3 {WATCHDOG} 2>/dev/null || echo '(no watchdog log yet)'
"""
    res = run(script)
    print(f"break command status: {res.get('status')}")
    if res.get("stderr", "").strip():
        print(f"stderr: {res['stderr'].strip()}")
    print(f"failure state forced on {instance_id} -- a fake service is now 'running' but wedged")
    print(f"check state: prash investigate '{INSTANCE_TAG}' --provider aws")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
