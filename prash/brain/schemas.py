"""Ported from prash-backend/app/agent/schemas.py (2026-08-09, Track D days 4-5),
extended with a "runtime" category and a recommended_action field.

The extension: v1's Diagnosis is entirely code-diff-shaped (fix_type +
files_changed) -- there was no way to represent "a running service is
unhealthy" (PRASH_V2.md \xa79, second review pass). A crash-looping pod's
fix isn't a file diff, it's an action (restart, rollback), so this adds
the minimal surface for that rather than redesigning fix_type itself:
- category gains "runtime"
- recommended_action carries which action to propose, mirroring the
  action ids Track C already built (restart_pod, rollback)

fix_type naturally resolves to manual_required for category="runtime"
via the existing coerce_fix_type validator (no files_changed => no code
fix) -- the CLI/dispatcher reads recommended_action instead when
deciding what to propose for a runtime diagnosis. Not schema-enforced
that recommended_action is only set for category="runtime", matching
how required_secrets is scoped to category="environment" by convention
and prompt instruction, not a hard validator, in v1 too.
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_CATEGORY_ALIASES = {
    "env_config": "environment", "env": "environment", "secrets": "environment",
    "import_error": "dependency", "imports": "dependency", "deps": "dependency",
    "database_migration": "code", "db_migration": "code",
    "ci": "workflow_config", "ci_config": "workflow_config", "workflow": "workflow_config",
    "flaky": "flaky_test", "test": "code",
    "k8s": "runtime", "kubernetes": "runtime", "infra": "runtime", "pod": "runtime",
    "terraform": "infra_as_code", "iac": "infra_as_code",
    "datadog": "monitoring", "monitor": "monitoring", "monitoring": "monitoring",
    "monitor_alert": "monitoring", "observability": "monitoring",
    "pagerduty": "monitoring", "pd": "monitoring", "incident": "monitoring",
    "incident_page": "monitoring",
}


class FileEdit(BaseModel):
    """One exact-match search/replace edit against a file's current content.

    Added 2026-08-17 (PRASH_V2.md §9) after live stress-testing found that
    whole-file regeneration (the original, and until now only, FileChange
    shape) silently drops content the model doesn't fully attend to — two
    separate live PRs each contained a correct fix PLUS unrelated deleted
    comment lines, with the model's own explanation claiming "everything
    else is untouched" when the diff proved otherwise. There was no
    mechanism to catch this: new_content was trusted as the complete file
    and written straight to a blob.

    old_content must match the current file exactly and uniquely — the same
    contract Prash's own coding-agent Edit tool uses, deliberately, since
    that's a pattern models are already well-trained to produce reliably.
    This is NOT the same as a traditional unified diff (line numbers +
    context, tried previously and abandoned — see the "patch" field warning
    this replaces in diagnosis_agent.py's prompt — fragile against whitespace
    drift). An exact substring match has no line numbers to get wrong: it
    either matches or it doesn't, and a failed match fails loudly (see
    FileChange.apply()) instead of silently corrupting the file.
    """

    old_content: str = Field(..., description="Exact existing text to find — must appear exactly once in the current file")
    new_content: str = Field(..., description="Text to replace it with")

    # Note: the match is exact first, but FileChange.apply() falls back to a
    # whitespace-tolerant, still-unique line match when the exact one fails —
    # see _apply_edit_tolerant(). old_content should still be copied verbatim;
    # the fallback only rescues the common LLM slip of getting indentation or
    # trailing whitespace slightly wrong on an otherwise-correct block.

    @field_validator("old_content")
    @classmethod
    def validate_old_content(cls, v):
        if not v:
            raise ValueError("old_content must not be empty")
        return v

    @field_validator("new_content")
    @classmethod
    def validate_edit_new_content(cls, v):
        if len(v) > 200_000:
            raise ValueError("edit new_content exceeds 200KB — likely hallucinated")
        return v


# ── Whitespace-tolerant edit application (2026-09-07) ────────────────────────
# A live CI-fix apply failed purely on whitespace drift: the model's
# old_content was the right block of prash/tui.py but its leading indentation
# didn't match the real (deeply class-nested) file byte-for-byte, so the exact
# substring match found nothing and the fix — and the PR — never happened. The
# diagnosis was correct; only the mechanical apply lost.
#
# These helpers give FileChange.apply() a fallback that tolerates the two
# whitespace slips models actually make on multi-line blocks — trailing
# whitespace / CRLF, and a uniform indent shift — WITHOUT weakening the core
# safety guarantee. Every tier still demands a single, unambiguous line-window
# match and splices the ORIGINAL file's own bytes for the surround, so content
# the model never mentioned still cannot be silently lost or rewritten. Partial
# intra-line substring edits are left to the exact path; the fallback is
# line-oriented on purpose.


def _leading_ws(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _match_line_window(orig_lines: list[str], old_lines: list[str], keyfn) -> int | None:
    """Start index of the sole run of ``orig_lines`` whose ``keyfn``-mapped
    values equal the ``keyfn``-mapped ``old_lines``. Returns None for zero
    matches or more than one — an ambiguous match is refused, never guessed."""
    m = len(old_lines)
    if m == 0 or m > len(orig_lines):
        return None
    old_key = [keyfn(line) for line in old_lines]
    found: int | None = None
    for i in range(len(orig_lines) - m + 1):
        if [keyfn(orig_lines[i + j]) for j in range(m)] == old_key:
            if found is not None:
                return None  # more than one candidate window — ambiguous
            found = i
    return found


def _uniform_indent_delta(orig_block: list[str], old_lines: list[str]) -> tuple[str, str] | None:
    """If ``orig_block`` is ``old_lines`` shifted by one uniform leading-indent
    string, return ``(mode, delta)`` where mode is ``"add"`` (the file has an
    extra ``delta`` prefix the model omitted) or ``"remove"`` (the model added
    an extra ``delta`` prefix). Returns None if the shift isn't uniform across
    every non-blank line, i.e. the indentation difference isn't a clean shift
    we can safely reproduce on the replacement text."""
    mode: str | None = None
    delta: str | None = None
    for orig, old in zip(orig_block, old_lines):
        if not old.strip():  # blank lines may differ freely; carry no indent info
            continue
        io, idd = _leading_ws(orig), _leading_ws(old)
        if io == idd:
            pair_mode, pair_delta = "add", ""
        elif len(io) > len(idd) and io.endswith(idd):
            pair_mode, pair_delta = "add", io[: len(io) - len(idd)]
        elif len(idd) > len(io) and idd.endswith(io):
            pair_mode, pair_delta = "remove", idd[: len(idd) - len(io)]
        else:
            return None  # indentation chars differ in a way that isn't a shift
        if delta is None:
            mode, delta = pair_mode, pair_delta
        elif (pair_mode, pair_delta) != (mode, delta) and pair_delta != "":
            # A zero-delta line ("" either mode) is consistent with any shift;
            # a non-zero one that disagrees means the shift isn't uniform.
            return None
    if delta is None:  # every line was blank — nothing to anchor a shift on
        return None
    return (mode or "add", delta)


def _reindent(text: str, delta: tuple[str, str]) -> str:
    mode, prefix = delta
    if not prefix:
        return text
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if not stripped.rstrip("\r\n"):  # blank line — leave untouched
            out.append(line)
        elif mode == "add":
            out.append(prefix + line)
        else:  # remove
            out.append(line[len(prefix):] if line.startswith(prefix) else line)
    return "".join(out)


def _splice(orig_lines: list[str], start: int, count: int, replacement: str) -> str:
    """Replace ``orig_lines[start:start+count]`` with ``replacement``, keeping
    every other original line (and its exact bytes) intact. The replacement
    adopts the replaced block's own end-of-line style, so splicing into a CRLF
    file doesn't leave a lone LF hunk behind."""
    before = "".join(orig_lines[:start])
    after = "".join(orig_lines[start + count:])
    last = orig_lines[start + count - 1]
    eol = "\r\n" if last.endswith("\r\n") else "\n" if last.endswith("\n") else ""
    rep = replacement
    if rep:  # normalize the replacement to the block's EOL and boundary
        rep = rep.replace("\r\n", "\n")
        had_trailing = rep.endswith("\n")
        if eol != "\n":
            rep = rep.replace("\n", eol)
        if eol and not had_trailing:
            rep += eol
        elif not eol and had_trailing:
            rep = rep.rstrip("\r\n")
    # rep == "" is a deletion: the block's lines vanish; before + after joins.
    return before + rep + after


def _apply_edit_tolerant(content: str, edit: "FileEdit") -> str | None:
    """Whitespace-tolerant fallback for a failed exact match. Returns the new
    file content, or None if no safe, unique match exists (the caller then
    raises the normal not-found error). Never guesses — see the module comment
    above these helpers."""
    orig_lines = content.splitlines(keepends=True)
    old_lines = edit.old_content.splitlines()
    if not old_lines:
        return None

    # Tier 1 fallback: tolerate trailing whitespace and CRLF/LF only. Leading
    # indentation still has to match, so the replacement splices in verbatim.
    i = _match_line_window(orig_lines, old_lines, lambda line: line.rstrip())
    if i is not None:
        return _splice(orig_lines, i, len(old_lines), edit.new_content)

    # Tier 2 fallback: tolerate a single uniform indent shift of the whole
    # block. Reindent the replacement by the same shift so it lands correctly
    # nested where the real file expects it.
    i = _match_line_window(orig_lines, old_lines, lambda line: line.strip())
    if i is not None:
        delta = _uniform_indent_delta(orig_lines[i : i + len(old_lines)], old_lines)
        if delta is not None:
            return _splice(orig_lines, i, len(old_lines), _reindent(edit.new_content, delta))
    return None


class FileChange(BaseModel):
    path: str = Field(..., description="File path relative to repo root")
    edits: list[FileEdit] = Field(
        default_factory=list,
        description="Exact-match search/replace edits against the file's EXISTING content. Use this to change a file that already exists.",
    )
    new_content: str | None = Field(
        default=None,
        description="Complete content for a brand-NEW file only. Do not use this to edit a file that already exists — use `edits` instead.",
    )
    create_empty: bool = Field(
        default=False,
        description=(
            "Set True ONLY when this new file's correct content genuinely is "
            "empty — e.g. a Python package __init__.py marker, a .gitkeep "
            "placeholder, or py.typed. Leave False for everything else; this "
            "is not a way to skip writing real content."
        ),
    )
    explanation: str = Field(..., description="What changed and why")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v):
        if v.startswith("/") or ".." in v:
            raise ValueError("Path must be relative and must not contain '..'")
        return v

    @field_validator("new_content")
    @classmethod
    def validate_content(cls, v):
        if v is None:
            return v
        if len(v) > 200_000:
            raise ValueError("new_content exceeds 200KB — likely hallucinated")
        return v

    @model_validator(mode="after")
    def require_edits_or_new_content(self) -> "FileChange":
        # An empty/whitespace-only new_content is ambiguous on its own: it's
        # usually the model giving up on a file it couldn't actually fix (the
        # historical failure mode this validator guards against), but for a
        # deliberately-empty new file (create_empty=True) it's the correct,
        # literal content. Normalize to "" only in the latter case so the
        # ambiguous default (create_empty=False + blank content) still fails
        # validation exactly as before instead of silently doing nothing.
        blank_new_content = self.new_content is None or len(self.new_content.strip()) == 0
        if self.create_empty and blank_new_content:
            self.new_content = ""
        elif blank_new_content:
            self.new_content = None

        if self.edits and self.new_content is not None:
            raise ValueError("FileChange must use either `edits` (existing file) or `new_content` (new file), not both")
        if not self.edits and self.new_content is None:
            raise ValueError("FileChange must provide either `edits` or `new_content` (or set create_empty=True for an intentionally empty new file)")
        return self

    def apply(self, original_content: str | None) -> str:
        """Return the file's new content after this change.

        new_content changes ignore original_content entirely (this is a new
        file, or an intentional full replacement). edits changes apply each
        edit in turn against original_content, requiring an exact, unique
        match — the whole point being that anything the model didn't
        explicitly mention in an edit is structurally impossible to lose,
        unlike regenerating the entire file and hoping nothing fell out.
        """
        if self.new_content is not None:
            return self.new_content
        content = original_content or ""
        for i, edit in enumerate(self.edits, start=1):
            count = content.count(edit.old_content)
            if count == 0:
                # Exact match missed — try the whitespace-tolerant fallback
                # before giving up. It still requires a single unambiguous
                # line-window match, so this rescues indentation/EOL drift
                # without ever guessing at an ambiguous target.
                spliced = _apply_edit_tolerant(content, edit)
                if spliced is not None:
                    content = spliced
                    continue
                raise ValueError(
                    f"edit {i} for {self.path} did not apply: old_content not found in the current file content"
                )
            if count > 1:
                raise ValueError(
                    f"edit {i} for {self.path} did not apply: old_content matches {count} times, expected exactly 1 — it must be unique"
                )
            content = content.replace(edit.old_content, edit.new_content, 1)
        return content


class DiagnosisOption(BaseModel):
    """One candidate in a ranked menu of options, for genuinely ambiguous
    runtime cases. Added 2026-08-15 (PRASH_V2.md §9, "ask, don't quit"):
    when the brain can't confidently commit to one action, it should present
    ranked choices with reasoning instead of either guessing or dead-ending
    on recommended_action=None."""

    action: Literal["restart_pod", "rollback", "scale", "edit_configmap", "terraform_init", "terraform_apply", "mute_monitor", "acknowledge_incident"] | None = Field(
        default=None,
        description=(
            "The action id for this option, or null for 'take no automated "
            "action, escalate to a human' as an explicit ranked choice."
        ),
    )
    rationale: str = Field(..., min_length=10, max_length=500, description="Why this specific option, given this specific evidence.")
    is_default: bool = Field(
        default=False,
        description="True for exactly one option in the list: what the brain would pick if forced to choose one.",
    )
    config_patch: dict[str, str] | None = Field(
        default=None,
        description="Only populated when action='edit_configmap'. Same shape as Diagnosis.config_patch.",
    )
    config_patch_target: str | None = Field(
        default=None,
        description="Only populated when action='edit_configmap'. Same shape as Diagnosis.config_patch_target.",
    )


class Diagnosis(BaseModel):
    problem_summary: str = Field(..., min_length=10, max_length=500)
    root_cause: str = Field(..., min_length=20, max_length=2000)
    fix_description: str = Field(..., min_length=20, max_length=2000)
    fix_type: Literal["safe_auto_apply", "review_recommended", "manual_required"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_flaky_test: bool = Field(default=False)
    files_changed: list[FileChange] = Field(default_factory=list)
    category: Literal["code", "workflow_config", "dependency", "environment", "flaky_test", "runtime", "infra_as_code", "monitoring", "unknown"]

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
            return _CATEGORY_ALIASES.get(v, v)
        return v
    logs_truncated_warning: bool = Field(default=False)
    speculative: bool = Field(default=False, description="True when confidence is low but a best-guess PR is still created for review")
    required_secrets: list[str] = Field(
        default_factory=list,
        description="Exact names of missing secrets/env vars that must be added to fix this failure (e.g. STRIPE_KEY, DATABASE_URL). Only populated when category='environment'.",
    )
    recommended_action: Literal["restart_pod", "rollback", "scale", "edit_configmap", "terraform_init", "terraform_apply", "mute_monitor", "acknowledge_incident"] | None = Field(
        default=None,
        description=(
            "Only populated when category='runtime' or 'monitoring'. The infrastructure action "
            "that addresses this failure — restart_pod for CrashLoopBackOff/OOMKilled/stuck "
            "pods, rollback for a bad deployment, scale for capacity problems, mute_monitor "
            "for a firing Datadog monitor, acknowledge_incident for a PagerDuty incident "
            "(both are paging stopgaps, never the fix for the underlying problem). None if "
            "no action can be determined from the available logs/events. This is a "
            "recommendation for the dispatcher, not an instruction to execute — it still "
            "goes through the normal permission/approval pipeline (PRASH_V2.md §5). "
            "Leave unset (null) when `options` is populated instead — see below."
        ),
    )
    config_patch: dict[str, str] | None = Field(
        default=None,
        description=(
            "Only populated when recommended_action='edit_configmap'. Maps "
            "key -> corrected_value for the ConfigMap merge-patch, e.g. "
            "{'DATABASE_HOST': 'postgres'}. Every key must be one you can name "
            "with high confidence from the pod's own logs (e.g. the app logs the "
            "wrong host/port it tried and the correct key name) — never guess a "
            "value that isn't evidenced in logs/events."
        ),
    )
    config_patch_target: str | None = Field(
        default=None,
        description=(
            "Only populated when recommended_action='edit_configmap'. The "
            "ConfigMap's own name (not the pod's), e.g. 'checkout-api-config'. "
            "Namespace is inherited from the pod's own namespace."
        ),
    )
    options: list[DiagnosisOption] | None = Field(
        default=None,
        description=(
            "A ranked menu of 2+ candidate actions with rationale, for genuinely "
            "ambiguous runtime cases only — where more than one action is plausible "
            "and you cannot honestly commit to a single confident recommendation. "
            "Leave null and use recommended_action alone for confident single-action "
            "cases; do not use options as a way to avoid committing when you actually "
            "know the answer (PRASH_V2.md §9, 2026-08-14)."
        ),
    )

    @field_validator("recommended_action", mode="before")
    @classmethod
    def _normalize_recommended_action(cls, v):
        """Models routinely emit the literal string "null" (or "none"/"") in
        tool-call JSON instead of an actual JSON null for a nullable field --
        a known cross-model quirk, not unique to one provider (hit this via
        both Kimi and DeepSeek in eval runs). Without this, Pydantic rejects
        the string outright since it isn't one of the three literal values,
        which silently failed 2 hand-authored k8s cases AND 3 unrelated CI
        cases in the same eval run -- caught by the harness, not assumed."""
        if isinstance(v, str) and v.strip().lower() in ("null", "none", ""):
            return None
        return v

    @field_validator("options", mode="before")
    @classmethod
    def _normalize_options(cls, v):
        """Same cross-model quirk as recommended_action above (a literal
        string "null"/"none" instead of a real JSON null), plus models
        sometimes emit an empty array instead of omitting an unused
        optional field -- both mean "no menu here", same as recommended_action
        alone being used."""
        if isinstance(v, str) and v.strip().lower() in ("null", "none", ""):
            return None
        if isinstance(v, list) and len(v) == 0:
            return None
        return v

    @model_validator(mode="after")
    def validate_options_menu(self) -> "Diagnosis":
        """A menu needs at least 2 real choices (a 1-option 'menu' should
        just be recommended_action) and exactly one default pick -- and,
        for every existing call site that only ever reads recommended_action
        (the whole CLI/dispatcher today, until Track A's rendering+dispatch
        side of the options flow lands), recommended_action is auto-derived
        from the default option so today's behavior degrades gracefully
        instead of silently going quiet. See PRASH_V2.md §9, 2026-08-15."""
        if self.options is None:
            return self
        if len(self.options) < 2:
            raise ValueError("options must have at least 2 entries — use recommended_action alone for a single confident choice")
        defaults = [o for o in self.options if o.is_default]
        if len(defaults) != 1:
            raise ValueError(f"exactly one option must be marked is_default, found {len(defaults)}")
        if self.recommended_action is None:
            self.recommended_action = defaults[0].action
        return self

    @model_validator(mode="after")
    def coerce_fix_type(self) -> "Diagnosis":
        """
        Auto-coerce inconsistent fix_type / files_changed combinations instead
        of hard-failing validation and killing the entire pipeline run.

        Rules:
        - safe_auto_apply or review_recommended with NO files → downgrade to manual_required
          (model said it would fix but produced nothing — treat as "can't fix")
        - manual_required WITH files → upgrade to review_recommended
          (model said it couldn't fix but produced a fix anyway — surface it for review)
        """
        has_files = bool(self.files_changed)
        if self.fix_type in ("safe_auto_apply", "review_recommended") and not has_files:
            self.fix_type = "manual_required"
        elif self.fix_type == "manual_required" and has_files:
            self.fix_type = "review_recommended"
        return self
