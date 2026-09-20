# PagerDuty Connector Rewrite — `connectors/pagerduty.py`

**Owner:** Anant  
**Status:** Complete  
**Priority:** Tier 2  
**Depends on:** `00_BASE_INTERFACE.md`, `02_DATADOG.md` (pattern proven)  

---

## Current State

`PagerDutyConnector(Connector)` is fully implemented with: `authenticate()`, `poll_state()`, `fetch_logs()`, `get_stats()`, `watch()`, `get_oncalls()`, `get_service_dependencies()`.
Write actions: `pagerduty-acknowledge`, `pagerduty-resolve`, `pagerduty-page`.
Phase 3 live-verification bugs fixed (dedup-key, cp1252 console, verify race).

---

## Tasks

### T1. Implement `watch(target) -> WatchHandle`
- [x] Poll incident state changes (triggered → acknowledged → resolved)
- [x] Target = service ID or `"all"`
- [x] Map incident urgency to WatchHandle severity

### T2. Rewrite `get_stats(target, since?) -> list[ConnectorEvent]`
- [x] Convert incident timeline to `ConnectorEvent` stream
- [x] Include acknowledgment, resolution, escalation events
- [x] Event types: `"incident_triggered"`, `"incident_acknowledged"`, `"incident_resolved"`, `"escalation"`

### T3. Wire `PagerDutyAlertAction` (outbound)
- [x] Implemented as `pagerduty_page.py` (`PagerdutyPageAction`) with `page_oncall` capability
- [x] Enriches plan with active on-call responders from `get_oncalls()`
- [x] Emits `ConnectorEvent` in execution detail for correlation

### T4. Preserve Phase 3 fixes
- [x] Dedup-key lookup via `incident_key` filter + alert `alert_key` fallback
- [x] cp1252 console safety (`_console_notify` sanitization)
- [x] Verify retry (3 attempts, 2s/4s backoff)

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_watch_returns_watch_handle` | `tests/test_pagerduty_connector.py` | Valid `WatchHandle` |
| `test_get_stats_service_mode_lists_incidents_and_change_events` | `tests/test_pagerduty_connector.py` | Incident timeline as `ConnectorEvent` |
| `test_pagerduty_page_execute` | `tests/test_actions.py` | Page creates trackable event in detail |
| `test_pagerduty_page_plan_surfaces_current_oncall` | `tests/test_actions.py` | On-call responders surfaced in plan impact |
| `test_find_incident_by_incident_key_null_field_matches_via_alert_key` | `tests/test_pagerduty_connector.py` | Phase 3 dedup-key fix preserved |
| `test_get_oncalls_returns_user_and_escalation_details` | `tests/test_pagerduty_connector.py` | On-call schedule query and user extraction |
| `test_get_service_dependencies_partitions_supporting_and_dependent` | `tests/test_pagerduty_connector.py` | Upstream/downstream service dependency mapping |

---

## Acceptance Criteria

- [x] `watch()` + `get_stats()` functional
- [x] All 48 connector tests + 23 action tests pass (71 total)
- [x] Phase 3 fixes preserved
- [x] CI green
