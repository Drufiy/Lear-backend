"""Gitleaks connector (Sprint 2 Tier 3, PRASH_V2.md §7b). Structurally
different from the other Tier 3 connectors -- no HTTP at all, since
gitleaks is a local CLI tool. Tests mock subprocess.run (writing a fake
report to the --report-path the real binary would populate) and
shutil.which, rather than urllib.
"""

from __future__ import annotations

import json
import subprocess

from prash.connectors.gitleaks import GitleaksConnector, GitleaksError


def _fake_run_writing_report(findings):
    """Build a fake subprocess.run that writes `findings` (a list of
    gitleaks-shaped dicts) to whatever --report-path the real command line
    asked for, simulating what the real binary would produce."""

    def fake_run(cmd, capture_output=True, text=True, timeout=300):
        report_path = cmd[cmd.index("--report-path") + 1]
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(findings, f)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    return fake_run


def test_authenticate_true_when_binary_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/gitleaks")
    gl = GitleaksConnector({})
    assert gl.authenticate() is True


def test_authenticate_false_when_binary_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    gl = GitleaksConnector({})
    assert gl.authenticate() is False


def test_locate_returns_empty_for_nonexistent_path():
    gl = GitleaksConnector({})
    assert gl.locate("/no/such/path/anywhere") == {}


def test_locate_returns_abs_path_for_real_directory(tmp_path):
    gl = GitleaksConnector({})
    handle = gl.locate(str(tmp_path))
    assert handle["path"] == str(tmp_path)
    assert handle["is_git_repo"] is False


def test_locate_detects_git_repo(tmp_path):
    (tmp_path / ".git").mkdir()
    gl = GitleaksConnector({})
    assert gl.locate(str(tmp_path))["is_git_repo"] is True


def test_poll_state_not_found_for_missing_path():
    from prash.connectors.base import ConnectorState

    gl = GitleaksConnector({})
    assert gl.poll_state("/no/such/path").state == ConnectorState.NOT_FOUND


def test_poll_state_unknown_when_binary_missing(monkeypatch, tmp_path):
    from prash.connectors.base import ConnectorState

    monkeypatch.setattr("shutil.which", lambda name: None)
    gl = GitleaksConnector({})
    state = gl.poll_state(str(tmp_path))
    assert state.state == ConnectorState.UNKNOWN
    assert "gitleaks binary not found" in state.detail["error"]


def test_poll_state_healthy_when_no_leaks_found(monkeypatch, tmp_path):
    from prash.connectors.base import ConnectorState

    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/gitleaks")
    monkeypatch.setattr(subprocess, "run", _fake_run_writing_report([]))
    gl = GitleaksConnector({})
    state = gl.poll_state(str(tmp_path))
    assert state.state == ConnectorState.HEALTHY
    assert state.detail["leak_count"] == 0


def test_poll_state_failed_when_leaks_found(monkeypatch, tmp_path):
    from prash.connectors.base import ConnectorState

    findings = [{"RuleID": "generic-api-key", "File": "config.py", "StartLine": 42, "Fingerprint": "abc123", "Secret": "sk_live_reallysecretvalue", "Match": "API_KEY=sk_live_reallysecretvalue"}]
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/gitleaks")
    monkeypatch.setattr(subprocess, "run", _fake_run_writing_report(findings))
    gl = GitleaksConnector({})
    state = gl.poll_state(str(tmp_path))
    assert state.state == ConnectorState.FAILED
    assert state.detail["leak_count"] == 1
    assert state.detail["findings"] == [{"rule_id": "generic-api-key", "file": "config.py", "line": 42, "fingerprint": "abc123"}]


def test_poll_state_never_leaks_the_actual_secret_value(monkeypatch, tmp_path):
    """The critical safety property: gitleaks' own report includes the raw
    matched secret text in Match/Secret -- neither must ever reach the
    connector's output, matching this repo's edit-secret precedent."""
    findings = [{"RuleID": "aws-access-key", "File": ".env", "StartLine": 3, "Fingerprint": "xyz", "Secret": "AKIASUPERSECRETVALUE", "Match": "AWS_KEY=AKIASUPERSECRETVALUE"}]
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/gitleaks")
    monkeypatch.setattr(subprocess, "run", _fake_run_writing_report(findings))
    gl = GitleaksConnector({})
    state = gl.poll_state(str(tmp_path))
    dumped = json.dumps(state.detail)
    assert "AKIASUPERSECRETVALUE" not in dumped


def test_run_scan_raises_on_nonzero_exit(monkeypatch, tmp_path):
    def fake_run(cmd, capture_output=True, text=True, timeout=300):
        return subprocess.CompletedProcess(cmd, returncode=2, stdout="", stderr="fatal: something broke")

    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/gitleaks")
    monkeypatch.setattr(subprocess, "run", fake_run)
    gl = GitleaksConnector({})
    state = gl.poll_state(str(tmp_path))
    from prash.connectors.base import ConnectorState

    assert state.state == ConnectorState.UNKNOWN
    assert "exited 2" in state.detail["error"]


def test_fetch_logs_never_leaks_secret_value(monkeypatch, tmp_path):
    findings = [{"RuleID": "generic-api-key", "File": "config.py", "StartLine": 42, "Fingerprint": "abc123", "Secret": "sk_live_reallysecretvalue", "Match": "whatever"}]
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/gitleaks")
    monkeypatch.setattr(subprocess, "run", _fake_run_writing_report(findings))
    gl = GitleaksConnector({})
    lines = gl.fetch_logs(str(tmp_path))
    assert lines == ["generic-api-key in config.py:42"]
    assert "sk_live_reallysecretvalue" not in " ".join(lines)
