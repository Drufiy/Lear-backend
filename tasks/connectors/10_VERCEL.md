# Vercel Connector Rewrite — `connectors/vercel.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 3  
**Depends on:** `00_BASE_INTERFACE.md`  

---

## Current State

`VercelConnector(Connector)` exists: `authenticate()`, `poll_state()`, `fetch_logs()`. Write actions: `vercel-redeploy` (SAFE), `vercel-rollback` (APPROVAL). Was the original template for the connector pattern from v1.

**Missing:** `watch()`, `get_stats()`.

---

## Tasks

### T1. `watch(target)` — poll deployment status
- [ ] Detect: deployment failed, build error, domain issue

### T2. `get_stats(target, since?)` — deployments → `ConnectorEvent`
- [ ] Deployment status changes, build times, errors

### T3. Preserve redeploy/rollback actions

---

## Tests & Acceptance Criteria

- [ ] `watch()` + `get_stats()` return correct types
- [ ] Existing `vercel-redeploy`/`vercel-rollback` unchanged
- [ ] All existing tests pass
