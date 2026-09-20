# Snyk Connector Rewrite — `connectors/snyk.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 3  
**Depends on:** `00_BASE_INTERFACE.md`  

---

## Current State

`SnykConnector(Connector)` exists: `authenticate()`, `poll_state()`, `fetch_logs()`. Write action: `snyk-ignore` (APPROVAL — accepting a vulnerability is a judgment call). Deliberately built as a different integration shape from Gitleaks/Dependabot.

**Missing:** `watch()`, `get_stats()`.

---

## Tasks

### T1. `watch(target)` — poll project vulnerability state
### T2. `get_stats(target, since?)` — vulnerabilities → `ConnectorEvent`
- [ ] Event types: `"new_vulnerability"`, `"vulnerability_fixed"`, `"severity_upgrade"`
### T3. Preserve `snyk-ignore` APPROVAL tier logic

---

## Tests & Acceptance Criteria

- [ ] `watch()` + `get_stats()` functional
- [ ] `snyk-ignore` unchanged (APPROVAL tier)
- [ ] All existing tests pass
