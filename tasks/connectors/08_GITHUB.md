# GitHub Connector Rewrite — `connectors/github.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 3  
**Depends on:** `00_BASE_INTERFACE.md`  

---

## Current State

`GitHubConnector(Connector)` exists with: `authenticate()`, `poll_state()` (workflow status), `fetch_logs()` (run logs), `get_file_content()`, `create_pr()`, `find_deployment_manifest()`. Write actions: `apply-ci-fix` (SAFE), `open-pr` (SAFE), `request-secret` (SAFE).

**Missing:** `watch()`, `get_stats()` as `ConnectorEvent`.

---

## Tasks

### T1. `watch(target)` — poll workflow runs for failures
- [ ] Target = `owner/repo` or specific workflow
- [ ] Detect: new failed run, consistently failing workflow
- [ ] Event types: `"workflow_failed"`, `"workflow_recovered"`

### T2. `get_stats(target, since?)` — workflow runs → `ConnectorEvent`
- [ ] Convert recent workflow runs to event stream
- [ ] Include: run conclusion, duration, branch, commit SHA

### T3. Wire `GitHubAlertAction`
- [ ] Already exists as `github_alert.py` — verify `alert()` pattern

### T4. Preserve PR/fix pipeline
- [ ] `apply-ci-fix` still creates branches via Git Data API (no local clone)
- [ ] `find_deployment_manifest` via git tree API (not code search)
- [ ] `FileChange.apply(original_content)` edit mechanism unchanged

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_github_watch` | `tests/test_github_connector.py` | Valid `WatchHandle` |
| `test_github_get_stats` | `tests/test_github_connector.py` | Workflow runs as events |
| `test_github_ci_fix_unbroken` | `tests/test_fix.py` | Full CI fix pipeline works |

---

## Acceptance Criteria

- [ ] `watch()` + `get_stats()` functional
- [ ] CI fix pipeline unchanged
- [ ] All existing GitHub tests pass
