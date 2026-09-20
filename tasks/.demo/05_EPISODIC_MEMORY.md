# Demo Episodic Memory — "I've Seen This Before"

**Owner:** Aradhya (memory) / Anant (integration)  
**Time to complete:** ~2 hours  
**Priority:** HIGH — this directly addresses the AWS engineer's key feedback  

---

## Why This Matters for the Demo

The AWS engineer explicitly called out **episodic memory** as critical: "if an agent resolved an incident before and the environment is unchanged, it should replay the same steps rather than re-derive a solution." This is one of the sharpest things we can show an investor.

**Demo flow:**
1. Break `checkout-api` (ConfigMap) → Prash diagnoses from scratch → fixes it
2. Break `checkout-api` the SAME WAY → Prash says "I've seen this before" → replays the fix instantly

---

## Current State

`RepoMemory` in [`brain/repo_memory.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/brain/repo_memory.py) already has the data model:
- `similar_fixes: list[dict]` — previous verified fixes
- `repeated_error_signatures: list[dict]` — error patterns seen before
- `as_prompt_context()` → formats for the diagnosis brain prompt

**Problem:** The builder (`build_repo_memory()`) was Supabase-backed in v1. v2 has no database. The dataclass and formatter exist, but there's no way to populate them locally.

---

## Tasks

### T1. Build local JSON-backed memory store

Create `prash/brain/local_memory.py`:

```python
"""Local JSON-backed episodic memory for Lear.

Stores verified fixes and error signatures in .prash/memory.json.
No database dependency — works entirely from the local filesystem.
"""
import json
import os
from pathlib import Path
from typing import Optional
from .repo_memory import RepoMemory

MEMORY_PATH = Path(os.environ.get("PRASH_MEMORY_PATH", ".prash/memory.json"))

def load_memory(repo_id: str = "default") -> RepoMemory:
    """Load episodic memory from local JSON store."""
    if not MEMORY_PATH.exists():
        return RepoMemory(repo_id=repo_id)
    data = json.loads(MEMORY_PATH.read_text())
    return RepoMemory(
        repo_id=repo_id,
        similar_fixes=data.get("similar_fixes", []),
        repeated_error_signatures=data.get("repeated_error_signatures", []),
        category_outcomes=data.get("category_outcomes", {}),
    )

def save_fix(diagnosis_summary: dict, verified: bool = True) -> None:
    """Append a verified fix to the local memory store."""
    data = {}
    if MEMORY_PATH.exists():
        data = json.loads(MEMORY_PATH.read_text())
    
    fixes = data.setdefault("similar_fixes", [])
    fixes.append(diagnosis_summary)
    
    # Also update error signature tracking
    signatures = data.setdefault("repeated_error_signatures", [])
    sig = diagnosis_summary.get("error_signature")
    if sig:
        existing = next((s for s in signatures if s["error_signature"] == sig), None)
        if existing:
            existing["count"] += 1
            existing["last_category"] = diagnosis_summary.get("category")
            existing["last_status"] = "verified" if verified else "unverified"
        else:
            signatures.append({
                "error_signature": sig,
                "count": 1,
                "last_category": diagnosis_summary.get("category"),
                "last_status": "verified" if verified else "unverified",
            })
    
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(data, indent=2, default=str))
```

- [x] `load_memory()` returns `RepoMemory` from local JSON
- [x] `save_fix()` appends verified fixes
- [x] Stores in `.prash/memory.json` (gitignored)

### T2. Wire memory into the diagnosis pipeline

In `prash/fix.py` — when running `prash fix`:
- [x] Load `repo_memory = local_memory.load_memory()`
- [x] Pass to `diagnose_failure(..., repo_memory=repo_memory)`
- [x] After a verified fix, call `local_memory.save_fix(diagnosis_dict)`

The brain already handles `repo_memory` — it's a fully optional parameter in `diagnose_failure()`. When non-empty, `RepoMemory.as_prompt_context()` injects the "REPO MEMORY" section into the system prompt.

### T3. Pre-seed memory for the demo

Created `scripts/demo/seed-memory.sh` and `scripts/demo/seed-memory.ps1`:
- [x] Script creates `.prash/memory.json` with a realistic previous fix
- [x] When the same failure is injected, the brain sees "Previous verified fix with 92% confidence"
- [x] `scripts/demo/reset-memory.ps1` provided for easy demo resets

### T4. Demo flow validation

1. **First run (no memory):** Clear `.prash/memory.json`, inject failure, run `prash fix` — brain diagnoses from scratch
2. **After fix:** `save_fix()` automatically stores the verified fix
3. **Second run (with memory):** Inject the SAME failure, run `prash fix` — brain shows "REPO MEMORY" section, says "This matches a previous verified fix", proposes the same action with higher confidence

- [x] Diagnosis prompt includes "REPO MEMORY" section on second run
- [x] Brain explicitly references the previous fix in its explanation
- [x] Fix confidence is higher on second run (or at minimum, same)

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_local_memory_save_load` | `tests/test_brain_local_memory.py` | JSON round-trip works |
| `test_memory_injected_into_prompt` | `tests/test_brain_local_memory.py` | `as_prompt_context()` non-empty with seeded data |
| `test_save_fix_updates_signatures` | `tests/test_brain_local_memory.py` | Signature count increments |
| `test_save_fix_updates_category_outcomes` | `tests/test_brain_local_memory.py` | Verified rate calculation |
| `test_save_fix_with_diagnosis_model` | `tests/test_brain_local_memory.py` | Pydantic Diagnosis extraction |
| `test_diagnose_k8s_pod_loads_and_passes_repo_memory` | `tests/test_brain_local_memory.py` | Pipeline integration |

---

## Acceptance Criteria

- [x] `load_memory()` works from local JSON
- [x] `save_fix()` persists after verified fix
- [x] Brain shows "I've seen this before" on second identical failure
- [x] Demo: first fix ~30s diagnosis, second fix ~5s diagnosis (replay)
