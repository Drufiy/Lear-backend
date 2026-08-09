"""Track D days 4-5: kimi_client.py's lazy client construction.

v1 built its OpenAI clients at MODULE IMPORT TIME from a pydantic Settings
object requiring KIMI_API_KEY to exist -- would crash on import (including
every test run) in any environment without it set. This locks in the fix:
the module must import cleanly with zero env vars, and clients must only
be constructed lazily, on first real use. See kimi_client.py's docstring.
"""
from __future__ import annotations

import importlib

import pytest

import prash.brain.kimi_client as kc


@pytest.fixture(autouse=True)
def _reload_after_each_test():
    """Several tests reload the module to test import-time behavior with
    different env vars -- reload once more after each test so a reloaded
    module object with mutated globals never leaks into a later test file
    that also imports prash.brain.kimi_client."""
    yield
    importlib.reload(kc)


def test_module_imports_with_no_env_vars_set(monkeypatch):
    """The actual regression this guards against: v1's eager client
    construction would have raised at import time here."""
    for key in ("KIMI_API_KEY", "DEEPSEEK_API_KEY", "KIMI_MODEL", "DEEPSEEK_MODEL", "PRIMARY_MODEL"):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(kc)
    assert kc._kimi is None
    assert kc._deepseek is None


def test_kimi_client_constructed_lazily_on_first_call(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "sk-test")
    importlib.reload(kc)
    assert kc._kimi is None
    client = kc._kimi_client()
    assert client is not None
    assert kc._kimi is client  # cached singleton, not rebuilt


def test_deepseek_client_is_none_when_no_key_configured(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    importlib.reload(kc)
    assert kc._deepseek_client() is None


def test_deepseek_client_constructed_when_key_present(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    importlib.reload(kc)
    client = kc._deepseek_client()
    assert client is not None


def test_model_ids_read_from_env_with_v1_matching_defaults(monkeypatch):
    monkeypatch.delenv("KIMI_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("PRIMARY_MODEL", raising=False)
    assert kc._kimi_model() == "kimi-k2.6"
    assert kc._deepseek_model() == "deepseek-v4-flash"
    assert kc._primary_model() == "deepseek"

    monkeypatch.setenv("KIMI_MODEL", "kimi-custom")
    assert kc._kimi_model() == "kimi-custom"


def test_estimate_cost_uses_known_model_prices():
    cost = kc._estimate_cost_usd("deepseek-v4-flash", {"input_tokens": 1_000_000, "output_tokens": 1_000_000})
    assert cost == pytest.approx(0.42)


def test_estimate_cost_none_for_unknown_model():
    assert kc._estimate_cost_usd("some-unpriced-model", {"input_tokens": 100, "output_tokens": 100}) is None


def test_log_agent_call_never_raises_even_with_bad_usage():
    """_log_agent_call must never break the pipeline -- v1's version wrapped
    a Supabase insert in try/except for the same reason; this is the local-
    logging equivalent of that guarantee."""
    kc._log_agent_call("run-1", "diagnosis", "kimi-k2.6", [], "raw", {"ok": True}, {}, valid=True)


def test_mark_agent_run_outcome_is_a_no_op_without_run_id():
    kc.mark_agent_run_outcome(None, "verified")  # must not raise
