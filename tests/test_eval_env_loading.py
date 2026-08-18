"""Regression for the Notion "evals/run_eval.py never loads .env" bug
(found 2026-08-17, fixed 2026-08-18, PRASH_V2.md §10). Without this, running
the eval harness in a shell that hadn't already exported DEEPSEEK_API_KEY/
KIMI_API_KEY silently ran with no model key at all.
"""
from __future__ import annotations

import os

from evals.run_eval import load_env_credentials


def test_loads_key_from_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=from-dot-env\n")
    monkeypatch.setenv("PRASH_ENV", str(env_file))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    load_env_credentials()

    assert os.environ["DEEPSEEK_API_KEY"] == "from-dot-env"


def test_shell_exported_value_wins_over_dot_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=from-dot-env\n")
    monkeypatch.setenv("PRASH_ENV", str(env_file))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-shell")

    load_env_credentials()

    assert os.environ["DEEPSEEK_API_KEY"] == "from-shell"


def test_blank_dot_env_value_treated_as_absent(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("KIMI_API_KEY=\n")
    monkeypatch.setenv("PRASH_ENV", str(env_file))
    monkeypatch.delenv("KIMI_API_KEY", raising=False)

    load_env_credentials()

    assert "KIMI_API_KEY" not in os.environ
