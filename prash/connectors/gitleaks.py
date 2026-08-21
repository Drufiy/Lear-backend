"""Gitleaks connector (Sprint 2 Tier 3, PRASH_V2.md §7b).

Structurally different from every other connector in this repo, and
deliberately not forced into the same shape: gitleaks is a local CLI tool,
not a hosted service with an API. There is no token to hold, no account to
authenticate against -- the actual precondition is "is the binary
installed," so authenticate() checks that instead of a credential.
`resource` is a local filesystem path to a git checkout, not an id/name
pair. Runs the binary via subprocess and parses its JSON report -- the
same "shell out, parse structured output" pattern AWSConnector's SSH
fallback already uses in this codebase, just as the primary mechanism here
rather than a fallback.

Scans git history by default (gitleaks' own default behavior and its
actual designed purpose -- a secret committed once and later removed is
still leaked in history, which is the whole reason this tool exists over
a plain grep of the working tree). Pass no_git=True for a working-tree-only
scan when history access isn't wanted or available.

Critical safety note, matching this repo's existing "credentials never
leave your machine" posture (see edit_config.py's EditSecretAction, which
never echoes a Secret's value): gitleaks' JSON report includes the actual
matched secret text in its `Match`/`Secret` fields. Both are stripped
before anything here returns to a caller -- only the rule id, file, line
number, and gitleaks' own fingerprint (a hash-like dedup id, not the
secret itself) are ever surfaced.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, Mapping

from .base import Connector, ConnectorState, ResourceState


class GitleaksError(RuntimeError):
    pass


class GitleaksConnector(Connector):
    name = "gitleaks"
    read_capabilities = ("secret_scan",)

    def __init__(self, credentials: Mapping[str, Any]):
        super().__init__(credentials)
        self.binary = credentials.get("GITLEAKS_BINARY") or "gitleaks"

    def authenticate(self) -> bool:
        return shutil.which(self.binary) is not None

    def locate(self, resource: str) -> Dict[str, Any]:
        path = os.path.abspath(os.path.expanduser(resource))
        if not os.path.isdir(path):
            return {}
        return {"path": path, "is_git_repo": os.path.isdir(os.path.join(path, ".git"))}

    def _run_scan(self, path: str, no_git: bool) -> list[Dict[str, Any]]:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = os.path.join(tmpdir, "report.json")
            cmd = [self.binary, "detect", "--source", path, "--report-format", "json", "--report-path", report_path, "--exit-code", "0"]
            if no_git:
                cmd.append("--no-git")
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            except FileNotFoundError as exc:
                raise GitleaksError(f"gitleaks binary not found ({self.binary}): {exc}") from exc
            except subprocess.TimeoutExpired as exc:
                raise GitleaksError(f"gitleaks scan timed out after {exc.timeout}s") from exc
            # exit-code 0 forces a clean process exit regardless of findings
            # (gitleaks' own default is 1-if-found, which would otherwise
            # look like a scan failure rather than "it worked and found
            # something"). A non-zero code here means the scan itself broke.
            if proc.returncode != 0:
                raise GitleaksError(f"gitleaks exited {proc.returncode}: {proc.stderr.strip()[:300]}")
            if not os.path.exists(report_path):
                return []
            with open(report_path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            return json.loads(raw) if raw else []

    def poll_state(self, resource: str, no_git: bool = False, **kwargs: Any) -> ResourceState:
        handle = self.locate(resource)
        if not handle:
            return ResourceState(resource, ConnectorState.NOT_FOUND, {})
        if not self.authenticate():
            return ResourceState(resource, ConnectorState.UNKNOWN, {"error": f"gitleaks binary not found: {self.binary}"})
        try:
            findings = self._run_scan(handle["path"], no_git)
        except GitleaksError as exc:
            return ResourceState(resource, ConnectorState.UNKNOWN, {"path": handle["path"], "error": str(exc)})
        state = ConnectorState.FAILED if findings else ConnectorState.HEALTHY
        # Never include Match/Secret -- those hold the actual leaked text.
        safe_findings = [
            {"rule_id": f.get("RuleID", ""), "file": f.get("File", ""), "line": f.get("StartLine"), "fingerprint": f.get("Fingerprint", "")}
            for f in findings
        ]
        return ResourceState(resource, state, {"path": handle["path"], "leak_count": len(findings), "findings": safe_findings})

    def fetch_logs(self, resource: str, no_git: bool = False, **kwargs: Any) -> list[str]:
        handle = self.locate(resource)
        if not handle or not self.authenticate():
            return []
        try:
            findings = self._run_scan(handle["path"], no_git)
        except GitleaksError:
            return []
        return [f"{f.get('RuleID', '?')} in {f.get('File', '?')}:{f.get('StartLine', '?')}" for f in findings]
