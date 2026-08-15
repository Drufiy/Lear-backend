"""Track D days 4-5: the schema extension for Kubernetes/runtime failures.

See prash/brain/schemas.py's module docstring for why this was added
(v1's Diagnosis had no way to express "a running service is unhealthy") and
PRASH_V2.md §9 for why the minimal option (one category + one field) was
chosen over redesigning fix_type.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from prash.brain.schemas import Diagnosis, DiagnosisOption


def _base(**overrides) -> dict:
    base = {
        "problem_summary": "Pod api-7f9d is crash-looping in namespace production",
        "root_cause": "Container exits immediately on startup because a required config file is missing from the image, causing repeated CrashLoopBackOff restarts.",
        "fix_description": "Restart the pod to clear the current crash state; the underlying image issue still needs a rebuild.",
        "fix_type": "manual_required",
        "confidence": 0.7,
        "category": "runtime",
        "files_changed": [],
    }
    base.update(overrides)
    return base


def test_runtime_category_accepted():
    d = Diagnosis(**_base())
    assert d.category == "runtime"


def test_recommended_action_accepts_known_actions():
    d = Diagnosis(**_base(recommended_action="restart_pod"))
    assert d.recommended_action == "restart_pod"


def test_recommended_action_defaults_to_none():
    d = Diagnosis(**_base())
    assert d.recommended_action is None


def test_recommended_action_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Diagnosis(**_base(recommended_action="delete_everything"))


def test_recommended_action_normalizes_string_null_to_none():
    """Real bug caught by the eval harness (2026-08-09, Track D days 6-8):
    models routinely emit the literal string "null" in tool-call JSON
    instead of an actual JSON null, which Pydantic rejects outright since
    it isn't one of the three literal action values. Hit via both Kimi and
    DeepSeek, and it broke unrelated CI cases too, not just runtime ones."""
    for raw in ("null", "NULL", "none", "None", ""):
        d = Diagnosis(**_base(recommended_action=raw))
        assert d.recommended_action is None, f"{raw!r} did not normalize to None"


def test_category_aliases_map_onto_runtime():
    """k8s/kubernetes/infra/pod are common model-output variants that should
    still land on the one real category, matching the existing alias pattern
    for env/ci/etc."""
    for alias in ("k8s", "kubernetes", "infra", "pod"):
        d = Diagnosis(**_base(category=alias))
        assert d.category == "runtime", f"alias {alias!r} did not normalize to runtime"


def test_runtime_with_no_files_stays_manual_required():
    """No files_changed for a runtime diagnosis is the normal case (the fix
    is an action, not a diff) -- coerce_fix_type must not fight that."""
    d = Diagnosis(**_base(fix_type="review_recommended", files_changed=[]))
    assert d.fix_type == "manual_required"


def test_existing_categories_still_work_unchanged():
    """Non-regression: the pre-existing categories/fix_type matrix from v1
    must behave identically after the extension."""
    d = Diagnosis(**_base(
        category="dependency",
        fix_type="safe_auto_apply",
        files_changed=[{"path": "requirements.txt", "new_content": "requests==2.31.0\n", "explanation": "pin requests"}],
    ))
    assert d.category == "dependency"
    assert d.fix_type == "safe_auto_apply"


# ── options: the "ask, don't quit" ranked menu (PRASH_V2.md §9, 2026-08-15) ─

def test_options_defaults_to_none():
    d = Diagnosis(**_base())
    assert d.options is None


def test_options_accepted_with_two_entries_and_one_default():
    d = Diagnosis(**_base(options=[
        DiagnosisOption(action="restart_pod", rationale="Empty logs, no clear scheduling failure — plausibly just wedged.", is_default=True),
        DiagnosisOption(action=None, rationale="Could also be a genuinely slow first-time image pull; restarting risks losing that progress.", is_default=False),
    ]))
    assert len(d.options) == 2
    assert d.options[0].is_default is True


def test_options_rejects_a_single_entry():
    """A 1-option 'menu' isn't a menu -- that's just recommended_action.
    Forcing this at the schema level backs up the prompt instruction not to
    use options as a way to avoid committing to a confident single call."""
    with pytest.raises(ValidationError, match="at least 2 entries"):
        Diagnosis(**_base(options=[
            DiagnosisOption(action="restart_pod", rationale="Only one candidate here, which defeats the point of a menu.", is_default=True),
        ]))


def test_options_rejects_zero_or_multiple_defaults():
    with pytest.raises(ValidationError, match="exactly one option must be marked is_default"):
        Diagnosis(**_base(options=[
            DiagnosisOption(action="restart_pod", rationale="First candidate action with no default marked at all.", is_default=False),
            DiagnosisOption(action="rollback", rationale="Second candidate action, also not marked as the default pick.", is_default=False),
        ]))
    with pytest.raises(ValidationError, match="exactly one option must be marked is_default"):
        Diagnosis(**_base(options=[
            DiagnosisOption(action="restart_pod", rationale="First candidate action, marked as a default pick here.", is_default=True),
            DiagnosisOption(action="rollback", rationale="Second candidate action, also marked default by mistake.", is_default=True),
        ]))


def test_options_auto_derives_recommended_action_from_the_default_pick():
    """Backward compatibility: every existing call site (the whole CLI and
    dispatcher today) reads recommended_action alone, until Track A's
    rendering+dispatch side of the options flow lands. A model that only
    fills in `options` must not go silently quiet for those call sites --
    recommended_action is derived from whichever option is marked default."""
    d = Diagnosis(**_base(options=[
        DiagnosisOption(action="rollback", rationale="The last deploy introduced this and rolling back is the safer of the two plausible calls.", is_default=True),
        DiagnosisOption(action="restart_pod", rationale="Could also just be a transient wedge, but less likely given the deploy timing.", is_default=False),
    ]))
    assert d.recommended_action == "rollback"


def test_options_does_not_override_an_explicitly_set_recommended_action():
    """If a model (incorrectly, against prompt instructions) fills in both
    fields, the explicit recommended_action wins rather than being
    silently overwritten by the derived value -- least surprise."""
    d = Diagnosis(**_base(
        recommended_action="restart_pod",
        options=[
            DiagnosisOption(action="rollback", rationale="This option's action differs from the explicitly set recommended_action above.", is_default=True),
            DiagnosisOption(action="restart_pod", rationale="This is the second of two options, deliberately not marked default here.", is_default=False),
        ],
    ))
    assert d.recommended_action == "restart_pod"


def test_options_normalizes_string_null_and_empty_list_to_none():
    """Same cross-model quirk as recommended_action's own normalization
    test above, plus the empty-array case for this field specifically."""
    for raw in ("null", "NULL", "none", "", []):
        d = Diagnosis(**_base(options=raw))
        assert d.options is None, f"{raw!r} did not normalize to None"


def test_options_action_can_be_null_for_escalate_to_human():
    """One of the ranked choices being 'no automated action, a human should
    look at this' is a legitimate, honest option in the menu, not just a
    fallback for when the menu doesn't apply."""
    d = Diagnosis(**_base(options=[
        DiagnosisOption(action=None, rationale="The evidence doesn't clearly support either automated action being safe to try here.", is_default=True),
        DiagnosisOption(action="restart_pod", rationale="A less-favored but still plausible second candidate, if a human wants to take the risk.", is_default=False),
    ]))
    assert d.options[0].action is None
    assert d.recommended_action is None
