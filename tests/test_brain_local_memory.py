"""Unit tests for local episodic memory store (tasks/.demo/05_EPISODIC_MEMORY.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prash.brain.local_memory import clear_memory, load_memory, save_fix
from prash.brain.schemas import Diagnosis


def test_local_memory_save_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mem_file = tmp_path / "memory.json"
    monkeypatch.setenv("PRASH_MEMORY_PATH", str(mem_file))

    # Initial load on missing file returns empty RepoMemory
    empty_mem = load_memory("test-repo")
    assert empty_mem.is_empty()
    assert empty_mem.similar_fixes == []

    # Save a fix
    fix_data = {
        "category": "runtime",
        "confidence": 0.95,
        "problem_summary": "CrashLoopBackOff: postgres-wrong",
        "root_cause": "ConfigMap points to wrong host",
        "fix_description": "Patch ConfigMap DATABASE_HOST=postgres",
        "error_signature": "sig-cm-db",
    }
    save_fix(fix_data)

    # Load back
    loaded = load_memory("test-repo")
    assert not loaded.is_empty()
    assert len(loaded.similar_fixes) == 1
    assert loaded.similar_fixes[0]["problem_summary"] == "CrashLoopBackOff: postgres-wrong"
    assert loaded.similar_fixes[0]["confidence"] == 0.95


def test_memory_injected_into_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mem_file = tmp_path / "memory.json"
    monkeypatch.setenv("PRASH_MEMORY_PATH", str(mem_file))

    save_fix({
        "category": "runtime",
        "confidence": 0.92,
        "problem_summary": "checkout-api CrashLoopBackOff: database unreachable",
        "root_cause": "DATABASE_HOST is incorrect",
        "fix_description": "Set DATABASE_HOST=postgres",
        "files_changed": [{"path": "configmap/checkout-api-config", "key": "DATABASE_HOST", "new": "postgres"}],
        "error_signature": "sig-checkout-db",
    })

    memory = load_memory("lear-demo/checkout-api")
    prompt_context = memory.as_prompt_context()
    assert "REPO MEMORY" in prompt_context
    assert "checkout-api CrashLoopBackOff" in prompt_context
    assert "Set DATABASE_HOST=postgres" in prompt_context
    assert "confidence 92%" in prompt_context


def test_save_fix_updates_signatures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mem_file = tmp_path / "memory.json"
    monkeypatch.setenv("PRASH_MEMORY_PATH", str(mem_file))

    sig = "CrashLoopBackOff:checkout-api:configmap-database-host"

    save_fix({
        "category": "runtime",
        "problem_summary": "First failure",
        "error_signature": sig,
    }, verified=True)

    mem1 = load_memory("test-repo")
    assert len(mem1.repeated_error_signatures) == 1
    assert mem1.repeated_error_signatures[0]["error_signature"] == sig
    assert mem1.repeated_error_signatures[0]["count"] == 1
    assert mem1.repeated_error_signatures[0]["last_status"] == "verified"

    # Second fix with the same signature
    save_fix({
        "category": "runtime",
        "problem_summary": "Second failure",
        "error_signature": sig,
    }, verified=True)

    mem2 = load_memory("test-repo")
    assert len(mem2.repeated_error_signatures) == 1
    assert mem2.repeated_error_signatures[0]["count"] == 2


def test_save_fix_updates_category_outcomes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mem_file = tmp_path / "memory.json"
    monkeypatch.setenv("PRASH_MEMORY_PATH", str(mem_file))

    save_fix({"category": "runtime", "problem_summary": "test 1"}, verified=True)
    save_fix({"category": "runtime", "problem_summary": "test 2"}, verified=False)

    mem = load_memory("test-repo")
    outcomes = mem.category_outcomes.get("runtime")
    assert outcomes is not None
    assert outcomes["attempts"] == 2
    assert outcomes["verified"] == 1
    assert outcomes["exhausted"] == 1
    assert outcomes["verified_rate"] == 0.5


def test_save_fix_with_diagnosis_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mem_file = tmp_path / "memory.json"
    monkeypatch.setenv("PRASH_MEMORY_PATH", str(mem_file))

    diagnosis = Diagnosis(
        problem_summary="checkout-api CrashLoopBackOff: database host error",
        root_cause="ConfigMap checkout-api-config has invalid DATABASE_HOST",
        fix_description="Edit ConfigMap to set DATABASE_HOST=postgres",
        fix_type="safe_auto_apply",
        confidence=0.91,
        category="runtime",
        recommended_action="edit_configmap",
        config_patch={"DATABASE_HOST": "postgres"},
        config_patch_target="checkout-api-config",
    )

    save_fix(diagnosis, verified=True)

    mem = load_memory("test-repo")
    assert len(mem.similar_fixes) == 1
    entry = mem.similar_fixes[0]
    assert entry["category"] == "runtime"
    assert entry["confidence"] == 0.91
    assert entry["recommended_action"] == "edit_configmap"
    assert len(entry["files_changed"]) == 1
    assert entry["files_changed"][0]["path"] == "configmap/checkout-api-config"
    assert entry["files_changed"][0]["new"] == "postgres"


def test_clear_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mem_file = tmp_path / "memory.json"
    monkeypatch.setenv("PRASH_MEMORY_PATH", str(mem_file))

    save_fix({"category": "runtime", "problem_summary": "test"})
    assert mem_file.exists()

    clear_memory()
    assert not mem_file.exists()


@pytest.mark.anyio
async def test_diagnose_k8s_pod_loads_and_passes_repo_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mem_file = tmp_path / "memory.json"
    monkeypatch.setenv("PRASH_MEMORY_PATH", str(mem_file))

    # Pre-seed memory
    save_fix({
        "category": "runtime",
        "confidence": 0.92,
        "problem_summary": "Pre-existing ConfigMap fix",
        "root_cause": "Wrong host",
        "fix_description": "Patch DATABASE_HOST",
        "error_signature": "sig-1",
    })

    import prash.fix as fix_mod
    from prash.connectors.kubernetes import PodStatus

    monkeypatch.setattr(
        fix_mod,
        "get_pod_status",
        lambda ns, p: [PodStatus(name="checkout-api-1234", namespace=ns, phase="Running", problem="CrashLoopBackOff", restart_count=5, ready=False)],
    )
    monkeypatch.setattr(fix_mod, "get_pod_logs", lambda ns, p: "Database connection refused postgres-wrong:5432")
    monkeypatch.setattr(fix_mod, "get_pod_events", lambda ns, p: [])

    passed_kwargs = {}
    async def fake_diagnose_failure(**kwargs):
        passed_kwargs.update(kwargs)
        return Diagnosis(
            problem_summary="checkout-api CrashLoopBackOff: cannot reach db",
            root_cause="Host is wrong and cannot connect to postgres database",
            fix_description="Fix host by editing ConfigMap database host property",
            fix_type="safe_auto_apply",
            confidence=0.95,
            category="runtime",
        )

    monkeypatch.setattr(fix_mod, "diagnose_failure", fake_diagnose_failure)

    diag = await fix_mod.diagnose_k8s_pod("lear-demo", "checkout-api")
    assert passed_kwargs.get("repo_memory") is not None
    repo_mem = passed_kwargs["repo_memory"]
    assert not repo_mem.is_empty()
    assert len(repo_mem.similar_fixes) == 1
    assert repo_mem.similar_fixes[0]["problem_summary"] == "Pre-existing ConfigMap fix"

