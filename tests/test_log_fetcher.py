"""_preprocess_logs' include_raw_tail flag (PRASH_V2.md §10, 2026-08-18).

Bug: diagnose_multi_failure splits preprocessed logs on === headers and
diagnoses each section as an independent failure. The RAW TAIL safety-net
section that _preprocess_logs always appended was misread as a second
failure, so a single real CI failure was reported as "2 of 2 diagnosed"
with a phantom failure and a bogus file-conflict warning. Fixed by making
multi-diagnosis callers opt out of the tail via include_raw_tail=False.
"""
from __future__ import annotations

from prash.brain.log_fetcher import _preprocess_logs
from prash.brain.multi_diagnosis import _split_by_job_sections


def test_include_raw_tail_default_true_appends_tail_section():
    logs = "=== job.txt ===\nsome error happened here\n"
    result = _preprocess_logs(logs)
    assert "=== RAW TAIL (last 40 lines) ===" in result


def test_include_raw_tail_false_omits_tail_section():
    logs = "=== job.txt ===\nsome error happened here\n"
    result = _preprocess_logs(logs, include_raw_tail=False)
    assert "RAW TAIL" not in result


def test_single_failure_preprocessed_without_tail_splits_to_one_section():
    """The actual regression: a single failing job must not become two
    sections (the real one + a phantom "RAW TAIL" one) once fed to the
    multi-diagnosis splitter."""
    logs = "=== test-job (failed) ===\nModuleNotFoundError: no module named 'x'\n"
    preprocessed = _preprocess_logs(logs, include_raw_tail=False)
    sections = _split_by_job_sections(preprocessed)
    assert len(sections) == 1
