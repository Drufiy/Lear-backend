# Multi-Diagnosis — `brain/multi_diagnosis.py`

**Owner:** Aradhya  
**Status:** Built  
**Priority:** Tier 2  

---

## Current State

`diagnose_multi_failure()` decomposes N independent CI failures, attempts each, reports "fixed X of N." `MultiFailureResult.combined_files_changed()` deduplicates across failures for combined PRs.

---

## Tasks

### T1. Extend to non-CI multi-failure scenarios
- [ ] Multiple K8s pods failing in the same namespace
- [ ] Multiple Datadog monitors firing simultaneously
- [ ] Mixed: K8s pod crash + CI failure + Datadog alert (same root cause)

### T2. Root cause deduplication
- [ ] Detect when N failures share one root cause (e.g., database down → 5 pods crash)
- [ ] Group related failures before presenting to user
- [ ] "3 services affected by 1 root cause" not "3 separate problems"

### T3. Honest reporting
- [ ] "Fixed X of N" strictly means action was taken and verified, not just proposed
- [ ] Partial success reported clearly: "fixed 2, 1 needs manual intervention, 1 unknown"
- [ ] `fixed_count` counts verified fixes, not proposals

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_multi_k8s_failures` | `tests/test_brain_multi_diagnosis.py` | Multiple pods handled |
| `test_shared_root_cause` | `tests/test_brain_multi_diagnosis.py` | Deduplication works |
| `test_honest_fixed_count` | `tests/test_brain_multi_diagnosis.py` | Count reflects reality |
| `test_mixed_connector_multi` | `tests/test_brain_multi_diagnosis.py` | K8s + CI + Datadog |

---

## Acceptance Criteria

- [ ] Multi-diagnosis works across connector types
- [ ] Root cause deduplication when applicable
- [ ] "Fixed X of N" is honest
