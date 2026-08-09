"""Track D days 4-5: the schema extension for Kubernetes/runtime failures.

See prash/brain/schemas.py's module docstring for why this was added
(v1's Diagnosis had no way to express "a running service is unhealthy") and
PRASH_V2.md §9 for why the minimal option (one category + one field) was
chosen over redesigning fix_type.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from prash.brain.schemas import Diagnosis


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
