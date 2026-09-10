"""Grounds a fix-apply edit that failed to match the real file (dogfooding
finding #4, 2026-09-09).

Live case that surfaced this: red CI on main from two missing dependencies
(`dotenv`, `fastapi`). The CI diagnosis path correctly identified the root
cause in all 3 job diagnoses, but none of them ever called `fetch_file` on
`.github/workflows/ci.yml` before proposing an edit to it — "add a pip
install line" felt obvious enough that the model skipped verification and
reconstructed a plausible-looking but non-existent version of the file from
training-prior CI-YAML patterns (e.g. `- name: Run tests\n  run: pytest`,
which doesn't exist anywhere in the real file) instead of the repo's actual
content. `FileChange.apply()`'s exact/tolerant match correctly refused
rather than corrupting the file — the whitespace-tolerant fallback added for
finding #3 is deliberately narrow (trailing whitespace, CRLF, a uniform
indent shift) and does NOT rescue fabricated content, by design — but that
just converts a silent bug into a loud one with no PR opened.

This module closes the gap on the other side: when apply() rejects an edit,
hand the model the file's REAL current content and ask it to produce a
corrected edit — a single, cheap, tightly-scoped call, not a re-diagnosis.
Bounded to one repair attempt per file; if the repair still doesn't apply,
the caller drops the file from files_changed rather than looping or forcing
a write.
"""
from __future__ import annotations

import logging

from .kimi_client import call_with_tool
from .schemas import FileChange, FileEdit

logger = logging.getLogger(__name__)

_REPAIR_TOOL_SCHEMA = {
    "name": "propose_corrected_edits",
    "description": "Corrected search/replace edits against the file's real, current content.",
    "parameters": {
        "type": "object",
        "properties": {
            "edits": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "old_content": {
                            "type": "string",
                            "description": "Exact text to find, copied VERBATIM from the real file content shown above — must appear exactly once.",
                        },
                        "new_content": {"type": "string", "description": "Replacement text."},
                    },
                    "required": ["old_content", "new_content"],
                },
            },
        },
        "required": ["edits"],
    },
}

_SYSTEM_PROMPT = (
    "Your previous proposed edit for a file did not apply: the old_content you gave doesn't "
    "appear in the file's real current content — it was paraphrased or invented rather than "
    "copied verbatim. You are being shown the file's ACTUAL current content below. Produce a "
    "corrected set of edits that achieves the same fix, with old_content copied EXACTLY from "
    "the real content shown and appearing exactly once in it. Keep edits minimal and targeted."
)


async def repair_edit(
    fc: FileChange,
    real_content: str,
    fix_intent: str,
    run_id: str | None = None,
) -> FileChange | None:
    """Ask the model to correct `fc`'s edits against `real_content`. Returns a
    new, already-validated FileChange on success, or None if the repair
    couldn't produce something that actually applies — callers should drop
    the file from files_changed in that case, not retry further."""
    failed_edits = "\n\n".join(
        f"--- failed edit {i} ---\nold_content (did not match): {e.old_content!r}\nnew_content: {e.new_content!r}"
        for i, e in enumerate(fc.edits, 1)
    )
    user_prompt = (
        f"FILE: {fc.path}\n\n"
        f"WHAT THIS FIX IS SUPPOSED TO DO:\n{fix_intent}\n\n"
        f"YOUR FAILED EDIT(S):\n{failed_edits}\n\n"
        f"THE FILE'S REAL CURRENT CONTENT:\n=== {fc.path} ===\n{real_content}\n=== end {fc.path} ===\n"
    )
    try:
        args = await call_with_tool(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tool_schema=_REPAIR_TOOL_SCHEMA,
            run_id=run_id,
            call_type="edit_repair",
        )
    except Exception as exc:  # noqa: BLE001 — a failed repair call falls back to dropping the file, not crashing the run
        logger.warning(f"Edit repair call failed for {fc.path}: {exc}")
        return None

    raw_edits = args.get("edits") or []
    try:
        edits = [FileEdit(old_content=e["old_content"], new_content=e["new_content"]) for e in raw_edits]
        candidate = fc.model_copy(update={"edits": edits, "new_content": None})
        candidate.apply(real_content)  # re-validate against the SAME real content; raises if still wrong
    except Exception as exc:  # noqa: BLE001 — still broken after a grounded retry; give up on this file, don't loop
        logger.warning(f"Edit repair for {fc.path} still did not apply: {exc}")
        return None

    logger.info(f"Edit repair succeeded for {fc.path} (run {run_id})")
    return candidate
