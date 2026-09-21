# GitLab Connector Rewrite — `connectors/gitlab.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 3  
**Depends on:** `00_BASE_INTERFACE.md`  

---

## Current State

`GitLabConnector(Connector)` exists: `authenticate()`, `poll_state()`, `fetch_logs()`, pipeline/MR support. Write action: `apply-gitlab-ci-fix`. Live-verified against a real project (2026-08-18).

**Missing:** `watch()`, `get_stats()`.

---

## Tasks

### T1. `watch(target)` — poll pipeline status
### T2. `get_stats(target, since?)` — pipelines → `ConnectorEvent`
### T3. Wire `GitLabAlertAction`
### T4. Preserve CI fix path (phantom multi-diagnosis bug fixed 2026-08-18)

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_gitlab_watch` | `tests/test_gitlab_connector.py` | Valid `WatchHandle` |
| `test_gitlab_get_stats` | `tests/test_gitlab_connector.py` | Pipeline events |
| `test_gitlab_ci_fix_unbroken` | `tests/test_gitlab_connector.py` | Fix path works |

---

## Acceptance Criteria

- [ ] Full loop closure
- [ ] All existing tests pass
