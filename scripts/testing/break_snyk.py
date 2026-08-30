#!/usr/bin/env python3
"""Reusable Snyk failure fixture (TESTING_SETUP.md).

Owns one Snyk test project end to end, the same way break_datadog.py owns
its monitor: a git repo (`prash-snyk-fixture`) whose dependency manifest
is toggled between a KNOWN-VULNERABLE version and a patched one. Snyk
scans the repo's manifest, so:

    break  -> set the vulnerable dependency (old lodash with a known
              high-severity CVE) and push -> Snyk re-import reports
              critical/high -> poll_state() reports FAILED.
    --heal -> set the patched dependency and push -> next scan is clean
              -> poll_state() reports HEALTHY.

No mock -- the vulnerable dependency is real (lodash@4.17.20 has
CVE-2021-23337, prototype pollution, high severity) and Snyk genuinely
flags it.

    python3 scripts/testing/break_snyk.py [--repo <owner/repo>]           # break
    python3 scripts/testing/break_snyk.py [--repo <owner/repo>] --heal    # heal

Requires GITHUB_TOKEN (to push the fixture repo) and, for the Snyk side,
SNYK_API_TOKEN + SNYK_ORG_ID (to trigger a re-import / check state).
Resource name to investigate with: the Snyk project name, which is the
repo path, e.g. `prash investigate <owner>/prash-snyk-fixture
--provider snyk` (after importing the repo into Snyk once -- the script
prints the import step if the project isn't found).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

FIXTURE_REPO = "prash-snyk-fixture"
# lodash 4.17.20: known high-severity prototype-pollution CVEs (e.g.
# CVE-2021-23337). Patched in 4.17.21.
VULNERABLE = "4.17.20"
PATCHED = "4.17.21"


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
        "github_token": env.get("GITHUB_TOKEN"),
        "snyk_token": env.get("SNYK_API_TOKEN"),
        "snyk_org": env.get("SNYK_ORG_ID"),
    }


def _github(token: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"https://api.github.com{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API {exc.code}: {exc.read().decode(errors='replace')[:300]}") from exc


def _snyk(token: str, org: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
    req = urllib.request.Request(f"https://api.snyk.io{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Snyk API {exc.code}: {exc.read().decode(errors='replace')[:300]}") from exc


def _manifest(lodash_version: str) -> str:
    return json.dumps({
        "name": "prash-snyk-fixture",
        "version": "1.0.0",
        "private": True,
        "dependencies": {"lodash": lodash_version},
    }, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Toggle a real known-vulnerable dependency in the prash Snyk fixture repo.")
    parser.add_argument("--repo", help="owner/repo for the fixture (default: <your github login>/prash-snyk-fixture).")
    parser.add_argument("--heal", action="store_true", help="Set the patched lodash version instead of the vulnerable one.")
    args = parser.parse_args()

    creds = _load_creds()
    if not creds["github_token"]:
        print("GITHUB_TOKEN not set", file=sys.stderr)
        return 1

    # Resolve the repo owner from the token if --repo not given.
    if args.repo:
        repo = args.repo
    else:
        user = _github(creds["github_token"], "GET", "/user")
        repo = f"{user.get('login', '')}/{FIXTURE_REPO}"
    owner, name = repo.split("/", 1)

    # Idempotently ensure the fixture repo exists.
    try:
        _github(creds["github_token"], "GET", f"/repos/{repo}")
        print(f"fixture repo exists: {repo}")
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise
        _github(creds["github_token"], "POST", "/user/repos", {"name": name, "private": True, "description": "Prash Snyk test fixture -- has a real known-vulnerable dependency when broken."})
        print(f"fixture repo created: {repo}")

    # Write the manifest and push it.
    version = PATCHED if args.heal else VULNERABLE
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-b", "main", tmp], check=True, capture_output=True)
        subprocess.run(["git", "-C", tmp, "config", "user.email", "fixture@test.local"], check=True, capture_output=True)
        subprocess.run(["git", "-C", tmp, "config", "user.name", "Prash Fixture"], check=True, capture_output=True)
        with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as f:
            f.write(_manifest(version))
        subprocess.run(["git", "-C", tmp, "add", "package.json"], check=True, capture_output=True)
        subprocess.run(["git", "-C", tmp, "commit", "-m", f"fixture: lodash {version}"], check=True, capture_output=True)
        push = subprocess.run(
            ["git", "-C", tmp, "push", "-f", f"https://x-access-token:{creds['github_token']}@github.com/{repo}.git", "main"],
            capture_output=True, text=True, check=False,
        )
        if push.returncode != 0:
            print(f"push failed: {push.stderr.strip()[:300]}", file=sys.stderr)
            return 1
    print(f"pushed package.json with lodash {version}")

    # Snyk side: trigger a re-import so Snyk re-scans the manifest.
    if creds["snyk_token"] and creds["snyk_org"]:
        try:
            integrations = _snyk(creds["snyk_token"], creds["snyk_org"], "GET", f"/v1/org/{creds['snyk_org']}/integrations")
            gh = next((i for i in integrations.get("integrations", []) if "github" in i.get("type", "").lower()), None)
            if gh:
                import_body = {"target": {"owner": owner, "name": name, "branch": "main"}, "files": [{"path": "package.json"}]}
                _snyk(creds["snyk_token"], creds["snyk_org"], "POST", f"/v1/org/{creds['snyk_org']}/integrations/{gh['id']}/import", import_body)
                print("Snyk re-import triggered -- scan usually lands within ~1min")
            else:
                print("no GitHub integration found in Snyk -- import the repo manually once, then this script can re-import")
        except RuntimeError as exc:
            print(f"could not trigger Snyk re-import: {exc}", file=sys.stderr)
            return 1
    else:
        print("SNYK_API_TOKEN/SNYK_ORG_ID not set -- skipping Snyk re-import. Import the repo into Snyk once manually.")

    if args.heal:
        print(f"manifest is now patched (lodash {PATCHED}) -- next scan should be clean")
    else:
        print(f"manifest now has vulnerable lodash {VULNERABLE} -- next scan should report critical/high")
        print(f"check state: prash investigate '{repo}' --provider snyk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
