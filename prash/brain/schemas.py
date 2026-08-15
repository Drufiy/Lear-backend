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
}


class FileChange(BaseModel):
    path: str = Field(..., description="File path relative to repo root")
    new_content: str | None = Field(default=None, description="Complete new file content")
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
        if len(v.strip()) == 0:
            return None
        return v

    @model_validator(mode="after")
    def require_content(self) -> "FileChange":
        if not self.new_content:
            raise ValueError("new_content must be provided")
        return self


class DiagnosisOption(BaseModel):
    """One candidate in a ranked menu of options, for genuinely ambiguous
    runtime cases. Added 2026-08-15 (PRASH_V2.md §9, "ask, don't quit"):
    when the brain can't confidently commit to one action, it should present
    ranked choices with reasoning instead of either guessing or dead-ending
    on recommended_action=None."""

    action: Literal["restart_pod", "rollback", "scale"] | None = Field(
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


class Diagnosis(BaseModel):
    problem_summary: str = Field(..., min_length=10, max_length=500)
    root_cause: str = Field(..., min_length=20, max_length=2000)
    fix_description: str = Field(..., min_length=20, max_length=2000)
    fix_type: Literal["safe_auto_apply", "review_recommended", "manual_required"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_flaky_test: bool = Field(default=False)
    files_changed: list[FileChange] = Field(default_factory=list)
    category: Literal["code", "workflow_config", "dependency", "environment", "flaky_test", "runtime", "unknown"]

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
    recommended_action: Literal["restart_pod", "rollback", "scale"] | None = Field(
        default=None,
        description=(
            "Only populated when category='runtime'. The infrastructure action that "
            "addresses this failure — restart_pod for CrashLoopBackOff/OOMKilled/stuck "
            "pods, rollback for a bad deployment, scale for capacity problems. None if "
            "no action can be determined from the available logs/events. This is a "
            "recommendation for the dispatcher, not an instruction to execute — it still "
            "goes through the normal permission/approval pipeline (PRASH_V2.md §5). "
            "Leave unset (null) when `options` is populated instead — see below."
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
