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


def test_kimi_client_raises_a_clear_error_naming_kimi_api_key_when_blank(monkeypatch):
    """Real bug, caught live (2026-08-15): a blank KIMI_API_KEY reached the
    bare AsyncOpenAI(api_key=None, ...) construction and raised the SDK's
    own generic "Missing credentials... set OPENAI_API_KEY" error -- true,
    but it never once names KIMI_API_KEY, the actual local config gap.
    Issue #5, PRASH_V2.md §10."""
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    importlib.reload(kc)
    with pytest.raises(kc.DiagnosisValidationError, match="KIMI_API_KEY"):
        kc._kimi_client()


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


# ── DeepSeek max_tokens truncation (found live, 2026-09-09 dogfooding) ───────
# DeepSeek's thinking mode emits reasoning and the final tool call in ONE
# continuous token stream sharing a single max_tokens budget. At the old
# value (8000), a real diagnosis prompt (59KB system prompt + real CI logs)
# reliably burned the entire budget on reasoning and got cut off before
# emitting anything — confirmed live: output_tokens exactly 8000,
# finish_reason "length", empty tool_calls and content. Every one of that
# night's 9 sub-diagnosis calls failed this way before falling back to Kimi.

class _FakeUsage:
    def __init__(self, prompt_tokens=100, completion_tokens=8000):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None, reasoning_content=""):
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content

    def model_dump(self):
        return {"content": self.content, "tool_calls": self.tool_calls, "reasoning_content": self.reasoning_content}


class _FakeChoice:
    def __init__(self, message, finish_reason=None):
        self.message = message
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, choices, usage=None):
        self.choices = choices
        self.usage = usage or _FakeUsage()


def _truncated_response():
    """Simulates the exact live failure: reasoning consumed the whole budget,
    finish_reason is "length", and neither a tool call nor any content survived."""
    msg = _FakeMessage(content=None, tool_calls=None, reasoning_content="")
    return _FakeResponse([_FakeChoice(msg, finish_reason="length")], usage=_FakeUsage(completion_tokens=8000))


def test_call_deepseek_uses_the_raised_max_tokens_budget(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    captured = {}

    async def fake_create_chat(client, **kwargs):
        captured.update(kwargs)
        msg = _FakeMessage(content=None, tool_calls=[])
        return _FakeResponse([_FakeChoice(msg, finish_reason="stop")])

    monkeypatch.setattr(kc, "_create_chat", fake_create_chat)
    import asyncio
    asyncio.run(kc._call_deepseek("deepseek-v4-flash", [{"role": "user", "content": "x"}], {"name": "t", "parameters": {}}))
    assert captured["max_tokens"] == kc.DEEPSEEK_MAX_OUTPUT_TOKENS
    assert kc.DEEPSEEK_MAX_OUTPUT_TOKENS > 8000  # the old, too-low value


def test_call_deepseek_truncation_returns_none_not_a_crash(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")

    async def fake_create_chat(client, **kwargs):
        return _truncated_response()

    monkeypatch.setattr(kc, "_create_chat", fake_create_chat)
    import asyncio
    args, raw, usage = asyncio.run(
        kc._call_deepseek("deepseek-v4-flash", [{"role": "user", "content": "x"}], {"name": "t", "parameters": {}})
    )
    assert args is None
    assert usage["output_tokens"] == 8000


def test_call_deepseek_logs_truncation_distinctly_from_a_declined_tool_call(monkeypatch, caplog):
    """The bug this whole fix targets: a truncated response used to log
    identically to "the model just didn't call the tool" (reasoning=N chars,
    tool_calls=0), giving no signal that max_tokens was the actual cause."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")

    async def fake_create_chat(client, **kwargs):
        return _truncated_response()

    monkeypatch.setattr(kc, "_create_chat", fake_create_chat)
    import asyncio
    import logging
    with caplog.at_level(logging.WARNING, logger="prash.brain.kimi_client"):
        asyncio.run(
            kc._call_deepseek("deepseek-v4-flash", [{"role": "user", "content": "x"}], {"name": "t", "parameters": {}})
        )
    assert any("truncated" in rec.message.lower() and "max_tokens" in rec.message for rec in caplog.records)


def test_call_deepseek_does_not_warn_of_truncation_when_model_simply_declines(monkeypatch, caplog):
    """A clean finish_reason="stop" with no tool call is the model choosing
    not to call the tool — a real, distinct outcome that must NOT be
    misreported as truncation."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")

    async def fake_create_chat(client, **kwargs):
        msg = _FakeMessage(content="I don't think a fix is needed here.", tool_calls=[])
        return _FakeResponse([_FakeChoice(msg, finish_reason="stop")])

    monkeypatch.setattr(kc, "_create_chat", fake_create_chat)
    import asyncio
    import logging
    with caplog.at_level(logging.WARNING, logger="prash.brain.kimi_client"):
        asyncio.run(
            kc._call_deepseek("deepseek-v4-flash", [{"role": "user", "content": "x"}], {"name": "t", "parameters": {}})
        )
    assert not any("truncated" in rec.message.lower() for rec in caplog.records)


def test_call_with_tools_uses_raised_deepseek_budget(monkeypatch):
    """The investigation-loop call site (fetch_file/list_directory/search_code)
    shares the same thinking-mode-truncation risk and needed the same fix."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    captured = {}

    async def fake_create_chat(client, **kwargs):
        captured.update(kwargs)
        msg = _FakeMessage(content="ok", tool_calls=[])
        return _FakeResponse([_FakeChoice(msg, finish_reason="stop")])

    monkeypatch.setattr(kc, "_create_chat", fake_create_chat)
    import asyncio
    asyncio.run(kc._call_with_tools([{"role": "user", "content": "x"}], [{"name": "t", "parameters": {}}], model="deepseek-v4-flash"))
    assert captured["max_tokens"] == kc.DEEPSEEK_MAX_OUTPUT_TOKENS
