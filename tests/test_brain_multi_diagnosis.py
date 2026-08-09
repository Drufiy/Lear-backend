"""Track D tier 2: the multi-failure fix (PRASH_V2.md §6/§9).

_split_by_job_sections() is pure and tested directly. diagnose_multi_failure()
is tested with diagnose_failure() mocked -- the orchestration (split, diagnose
each independently, aggregate, count fixed/unresolved, merge files) is what's
under test, not the model call itself.
"""
from __future__ import annotations

import asyncio

import prash.brain.multi_diagnosis as md_mod
from prash.brain.multi_diagnosis import (
    MultiFailureResult,
    _split_by_job_sections,
    diagnose_multi_failure,
)
from prash.brain.schemas import Diagnosis, FileChange


def _diagnosis(problem="something failed in this job", fixed=True, path="a.py", category="code") -> Diagnosis:
    return Diagnosis(
        problem_summary=problem,
        root_cause="root cause text long enough to pass validation minimums here",
        fix_description="fix description text long enough to pass validation minimums",
        fix_type="review_recommended" if fixed else "manual_required",
        confidence=0.8,
        category=category,
        files_changed=[FileChange(path=path, new_content="content", explanation="fix")] if fixed else [],
    )


# ── _split_by_job_sections: pure log-splitting logic ────────────────────────

def test_splits_nested_matrix_style_headers_by_job_prefix():
    logs = (
        "=== backend/1_Set up job.txt ===\nsetup ok\n"
        "=== backend/2_Run ruff.txt ===\nF401 unused import\n"
        "=== frontend/1_Set up job.txt ===\nsetup ok\n"
        "=== frontend/2_Run biome.txt ===\nlint errors\n"
    )
    sections = _split_by_job_sections(logs)
    assert set(sections.keys()) == {"backend", "frontend"}
    assert "F401" in sections["backend"]
    assert "biome" in sections["frontend"]


def test_splits_flat_numbered_job_files():
    logs = "=== 0_Backend.txt ===\nruff error\n=== 1_Frontend.txt ===\nbiome error\n"
    sections = _split_by_job_sections(logs)
    assert set(sections.keys()) == {"Backend", "Frontend"}


def test_no_headers_returns_single_section():
    logs = "just some plain log text, no === markers ==="
    sections = _split_by_job_sections(logs)
    assert sections == {"": logs}


# ── diagnose_multi_failure: orchestration, diagnose_failure mocked ─────────

def test_single_job_falls_back_to_one_diagnosis(monkeypatch):
    async def fake_diagnose(**kwargs):
        return _diagnosis()

    monkeypatch.setattr(md_mod, "diagnose_failure", fake_diagnose)
    result = asyncio.run(diagnose_multi_failure(
        logs="=== only_job.txt ===\nsome error",
        repo_full_name="acme/repo", commit_message="msg", workflow_name="CI",
    ))
    assert result.total_count == 1
    assert result.fixed_count == 1


def test_agentcore_shaped_case_reports_partial_success(monkeypatch):
    """The actual 'done when' bar from PRASH_V2.md §6: N independent
    failures, not all fixable, must report a real partial success (e.g.
    3 of 4) instead of one manual_required covering nothing."""
    logs = (
        "=== backend/1_Run ruff.txt ===\nF401 unused import\n"
        "=== contracts/1_Check drift.txt ===\nschema drift detected\n"
        "=== frontend/1_Run biome.txt ===\n49 lint errors\n"
        "=== mobile/1_Parity check.txt ===\nparity mismatch, ambiguous cause\n"
    )

    async def fake_diagnose(logs, **kwargs):
        # 3 of the 4 job logs are clearly fixable; the mobile one isn't.
        if "parity mismatch" in logs:
            return _diagnosis(problem="mobile parity ambiguous", fixed=False, category="unknown")
        if "F401" in logs:
            return _diagnosis(problem="backend ruff F401", fixed=True, path="backend/mod.py")
        if "drift" in logs:
            return _diagnosis(problem="contracts drift", fixed=True, path="contracts/schema.json")
        return _diagnosis(problem="frontend biome errors", fixed=True, path="frontend/app.tsx")

    monkeypatch.setattr(md_mod, "diagnose_failure", fake_diagnose)
    result = asyncio.run(diagnose_multi_failure(
        logs=logs, repo_full_name="acme/agentcore", commit_message="msg", workflow_name="CI",
    ))

    assert result.total_count == 4
    assert result.fixed_count == 3
    assert result.summary() == "Fixed 3 of 4 independent failures"
    assert len(result.unresolved_summaries()) == 1
    assert "parity" in result.unresolved_summaries()[0]
    combined_paths = {fc.path for fc in result.combined_files_changed()}
    assert combined_paths == {"backend/mod.py", "contracts/schema.json", "frontend/app.tsx"}


def test_one_sub_diagnosis_erroring_does_not_sink_the_others(monkeypatch):
    logs = "=== a.txt ===\nerror a\n=== b.txt ===\nerror b\n"

    async def fake_diagnose(logs, **kwargs):
        if "error a" in logs:
            raise RuntimeError("model call failed for job a")
        return _diagnosis(problem="job b failed with a real error", fixed=True, path="b.py")

    monkeypatch.setattr(md_mod, "diagnose_failure", fake_diagnose)
    result = asyncio.run(diagnose_multi_failure(
        logs=logs, repo_full_name="acme/repo", commit_message="msg", workflow_name="CI",
    ))
    assert result.total_count == 1  # only job b produced a diagnosis
    assert result.fixed_count == 1


def test_combined_files_changed_dedupes_conflicting_paths(monkeypatch):
    logs = "=== a.txt ===\nerror a\n=== b.txt ===\nerror b\n"

    async def fake_diagnose(logs, **kwargs):
        # Both "independent" failures touch the same file -- a real conflict.
        return _diagnosis(problem="conflicting failure touching shared file", fixed=True, path="shared.py")

    monkeypatch.setattr(md_mod, "diagnose_failure", fake_diagnose)
    result = asyncio.run(diagnose_multi_failure(
        logs=logs, repo_full_name="acme/repo", commit_message="msg", workflow_name="CI",
    ))
    assert len(result.combined_files_changed()) == 1  # deduped, not two conflicting edits to the same path


def test_failing_job_names_filters_out_passing_jobs(monkeypatch):
    """Only diagnose jobs actually known to have failed -- no point spending
    a model call on a job that passed, matching log_fetcher.py's existing
    failing-job-awareness (_fetch_failing_job_names)."""
    logs = "=== backend.txt ===\nerror\n=== frontend.txt ===\nall tests passed\n"
    seen_logs = []

    async def fake_diagnose(logs, **kwargs):
        seen_logs.append(logs)
        return _diagnosis()

    monkeypatch.setattr(md_mod, "diagnose_failure", fake_diagnose)
    asyncio.run(diagnose_multi_failure(
        logs=logs, repo_full_name="acme/repo", commit_message="msg", workflow_name="CI",
        failing_job_names={"backend"},
    ))
    assert len(seen_logs) == 1
    assert "error" in seen_logs[0]


def test_concurrency_bounded_to_max_concurrency(monkeypatch):
    """Found live (2026-08-09): a bare asyncio.gather across all sub-
    diagnoses hit a real Kimi rate limit ('max organization concurrency: 3')
    on a 4-job case. Locks in that the semaphore actually bounds how many
    diagnose_failure calls are in flight at once, not just that it exists."""
    logs = "".join(f"=== job{i}.txt ===\nerror {i}\n" for i in range(6))
    in_flight = 0
    max_seen = 0

    async def fake_diagnose(logs, **kwargs):
        nonlocal in_flight, max_seen
        in_flight += 1
        max_seen = max(max_seen, in_flight)
        await asyncio.sleep(0.01)  # force overlap so concurrency is actually exercised
        in_flight -= 1
        return _diagnosis()

    monkeypatch.setattr(md_mod, "diagnose_failure", fake_diagnose)
    result = asyncio.run(diagnose_multi_failure(
        logs=logs, repo_full_name="acme/repo", commit_message="msg", workflow_name="CI",
        max_concurrency=2,
    ))
    assert max_seen <= 2
    assert result.total_count == 6


def test_multi_failure_result_properties_on_empty_diagnoses():
    result = MultiFailureResult(diagnoses=[])
    assert result.total_count == 0
    assert result.fixed_count == 0
    assert result.combined_files_changed() == []
