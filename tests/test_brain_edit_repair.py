"""prash/brain/edit_repair.py — dogfooding finding #4 (2026-09-09).

repair_edit() is the grounded-retry: given a FileChange whose old_content
didn't match the real file, ask the model once more with the real content
attached, and only accept the result if it actually applies.
"""
from __future__ import annotations

import asyncio

import prash.brain.edit_repair as edit_repair_mod
from prash.brain.schemas import FileChange, FileEdit


def _broken_fc():
    return FileChange(
        path="ci.yml",
        edits=[FileEdit(old_content="run: pytest", new_content="run: pip install fastapi\nrun: pytest")],
        explanation="install missing dependency",
    )


def test_repair_edit_returns_corrected_file_change_on_success(monkeypatch):
    real = "steps:\n  - name: Tests\n    run: pytest -q\n"

    async def fake_call_with_tool(*, system_prompt, user_prompt, tool_schema, run_id=None, call_type=None):
        assert "ci.yml" in user_prompt
        assert real in user_prompt
        return {"edits": [{"old_content": "run: pytest -q", "new_content": "run: pip install fastapi\n    run: pytest -q"}]}

    monkeypatch.setattr(edit_repair_mod, "call_with_tool", fake_call_with_tool)

    result = asyncio.run(edit_repair_mod.repair_edit(_broken_fc(), real, "add missing fastapi dependency"))
    assert result is not None
    assert result.path == "ci.yml"
    applied = result.apply(real)
    assert "pip install fastapi" in applied


def test_repair_edit_returns_none_when_corrected_edit_still_does_not_apply(monkeypatch):
    real = "steps:\n  - name: Tests\n    run: pytest -q\n"

    async def fake_call_with_tool(**kwargs):
        # Model repairs again with content that STILL isn't in the real file.
        return {"edits": [{"old_content": "this text is not in the file either", "new_content": "x"}]}

    monkeypatch.setattr(edit_repair_mod, "call_with_tool", fake_call_with_tool)

    result = asyncio.run(edit_repair_mod.repair_edit(_broken_fc(), real, "add missing fastapi dependency"))
    assert result is None


def test_repair_edit_returns_none_when_call_with_tool_raises(monkeypatch):
    async def fake_call_with_tool(**kwargs):
        raise RuntimeError("both providers exhausted")

    monkeypatch.setattr(edit_repair_mod, "call_with_tool", fake_call_with_tool)

    result = asyncio.run(edit_repair_mod.repair_edit(_broken_fc(), "real content", "fix it"))
    assert result is None


def test_repair_tool_schema_is_flat_not_openai_wrapped():
    """Real bug caught live (2026-09-09): call_with_tool's callees read
    tool_schema["name"] directly (kimi_client.py's tool_choice construction) —
    wrapping it OpenAI-Chat-Completions-style as {"type": "function",
    "function": {...}} makes that a KeyError, and DeepSeek's API separately
    rejects the resulting double-wrapped tools[0] with 'missing field name'.
    The schema must be the flat {name, description, parameters} shape, same
    as DIAGNOSIS_TOOL in diagnosis_agent.py."""
    schema = edit_repair_mod._REPAIR_TOOL_SCHEMA
    assert schema["name"] == "propose_corrected_edits"
    assert "parameters" in schema
    assert "type" not in schema  # would indicate the wrong (OpenAI-tools-array) wrapping
    assert "function" not in schema


def test_repair_edit_returns_none_on_malformed_tool_response(monkeypatch):
    async def fake_call_with_tool(**kwargs):
        return {"edits": [{"old_content": ""}]}  # missing new_content, empty old_content

    monkeypatch.setattr(edit_repair_mod, "call_with_tool", fake_call_with_tool)

    result = asyncio.run(edit_repair_mod.repair_edit(_broken_fc(), "real content", "fix it"))
    assert result is None
