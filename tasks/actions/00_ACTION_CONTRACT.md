# Action Contract Hardening — `actions/contract.py`

**Owner:** Aryan  
**Status:** Ongoing  
**Priority:** Tier 1  

---

## Goal

Ensure the `Action` interface (`ActionSpec`, `plan()`, `execute()`, `verify()`) is robust, well-typed, and consistent across all 29 action files.

---

## Tasks

### T1. Audit `ActionSpec` consistency across all actions
- [ ] Every action has: `id`, `summary`, `risk_tier`, `reversible`, `capabilities`, `approval_hint`
- [ ] Risk tier assignments match the documented rules:
  - **SAFE:** Reversible, low-blast-radius (restart, mute, redeploy, escalate)
  - **APPROVAL:** Consequential claims (rollback, scale, apply, ignore vulnerability, exec)
  - **NEVER:** Anything that destroys data (none exist yet, by design)
- [ ] `capabilities` field accurately reflects what connectors the action needs

### T2. Verify `verify()` on every action
- [ ] Every action's `verify()` actually re-checks the system, not just returns `True`
- [ ] Actions with no meaningful verification should return `UNKNOWN`, not fake `SUCCEEDED`
- [ ] `restart_pod.verify()` — reads real `PodStatus` fields
- [ ] `rollback.verify()` — checks revision changed
- [ ] `scale.verify()` — confirms actual replica count
- [ ] `apply-ci-fix.verify()` — confirms PR was created
- [ ] `execute-aws/azure/gcp.verify()` — confirms command ran

### T3. `_ApplyFixBase` file-fidelity mechanism
- [ ] `FileChange.apply(original_content)` is the single reconciliation path
- [ ] `edits: list[FileEdit]` for existing files, `new_content` for new files only
- [ ] Exactly one of `edits`/`new_content` must be set (validation enforced)
- [ ] `FileEdit.old_content` must match file exactly and uniquely

### T4. Cross-action audit trail completeness
- [ ] Every action logs: action_id, risk_tier, target, was_approved, outcome, timestamp
- [ ] Options-based selections also log: "user selected option 2 of 3 (restart_pod)"
- [ ] Dry-run executions logged as `dry_run=True`

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_all_actions_have_spec` | `tests/test_actions.py` | Every registered action has valid `ActionSpec` |
| `test_risk_tier_assignments` | `tests/test_actions.py` | SAFE/APPROVAL/NEVER correctly assigned |
| `test_verify_not_trivial` | `tests/test_actions.py` | No action returns hardcoded True from verify |
| `test_file_change_apply_edits` | `tests/test_brain_schemas.py` | `FileChange.apply()` works for edits |
| `test_file_change_apply_new_content` | `tests/test_brain_schemas.py` | `FileChange.apply()` works for new files |
| `test_file_change_validation` | `tests/test_brain_schemas.py` | Can't set both edits and new_content |
| `test_audit_trail_completeness` | `tests/test_audit.py` | Every action type produces audit entry |

---

## Acceptance Criteria

- [ ] All 29 actions pass contract validation
- [ ] No action has a trivial `verify()`
- [ ] File-fidelity edits mechanism solid
- [ ] Audit trail is complete for every action type
