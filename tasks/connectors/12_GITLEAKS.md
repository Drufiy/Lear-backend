# Gitleaks Connector Rewrite — `connectors/gitleaks.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 3  
**Depends on:** `00_BASE_INTERFACE.md`  

---

## Current State

`GitleaksConnector(Connector)` exists: local scan, `poll_state()`, `fetch_logs()`. Write action: `gitleaks-escalate` (SAFE — escalates to PagerDuty, never includes the actual secret text). Deliberately has NO cloud account to mutate — a leaked secret is fixed by rotating the credential, not by Gitleaks.

**Missing:** `watch()`, `get_stats()`.

---

## Tasks

### T1. `watch(target)` — periodic local scan
- [ ] Run gitleaks scan on schedule
- [ ] Detect: new secret leak found

### T2. `get_stats(target, since?)` — scan results → `ConnectorEvent`
- [ ] Event types: `"secret_leaked"`, `"scan_clean"`
- [ ] **CRITICAL:** Never include the actual secret text in events (existing safety property)

### T3. Preserve escalation model
- [ ] `gitleaks-escalate` opens PagerDuty incident via Events API
- [ ] Uses different PagerDuty auth model than `pagerduty-acknowledge`/`-resolve`

---

## Tests & Acceptance Criteria

- [ ] `watch()` + `get_stats()` functional
- [ ] Secret text NEVER appears in events, logs, or audit trail
- [ ] `gitleaks-escalate` → PagerDuty pipeline preserved
- [ ] All existing tests pass
