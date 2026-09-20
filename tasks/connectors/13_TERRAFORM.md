# Terraform Connector Rewrite — `connectors/terraform.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 3  
**Depends on:** `00_BASE_INTERFACE.md`  

---

## Current State

`TerraformConnector(Connector)` exists: monitors `.tfstate`, drift detection locally, stubs for Terraform Cloud. Write actions: `terraform-init` (SAFE), `terraform-apply` (APPROVAL — dynamic risk tier). Brain knows `infra_as_code` category.

**Missing:** `watch()`, `get_stats()`.

---

## Tasks

### T1. `watch(target)` — periodic drift detection
- [ ] Target = terraform working directory
- [ ] Run `terraform plan` on schedule, detect drift
- [ ] Gracefully handle missing `.tfstate` (existing behavior: safe degradation)

### T2. `get_stats(target, since?)` — drift events → `ConnectorEvent`
- [ ] Event types: `"drift_detected"`, `"plan_failed"`, `"apply_succeeded"`

### T3. Preserve graceful degradation
- [ ] Missing `.tfstate` → degradation message, no crash
- [ ] `terraform-apply` stays APPROVAL tier

---

## Tests & Acceptance Criteria

- [ ] `watch()` + `get_stats()` functional
- [ ] Missing `.tfstate` doesn't crash watcher
- [ ] All existing tests pass
