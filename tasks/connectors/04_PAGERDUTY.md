# PagerDuty Connector Rewrite — `connectors/pagerduty.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 2  
**Depends on:** `00_BASE_INTERFACE.md`, `02_DATADOG.md` (pattern proven)  

---

## Current State

`PagerDutyConnector(Connector)` exists with: `authenticate()`, `poll_state()`, `fetch_logs()`, `get_stats()` (partial). Write actions: `pagerduty-acknowledge`, `pagerduty-resolve`, `pagerduty-page`. Phase 3 live-verification bugs already fixed (dedup-key, cp1252 console, verify race).

**Missing:** `watch()`, proper `ConnectorEvent` output, `pagerduty-alert` action for outbound alerting.

---

## Tasks

### T1. Implement `watch(target) -> WatchHandle`
- [ ] Poll incident state changes (triggered → acknowledged → resolved)
- [ ] Target = service ID or `"all"`
- [ ] Map incident urgency to WatchHandle severity

### T2. Rewrite `get_stats(target, since?) -> list[ConnectorEvent]`
- [ ] Convert incident timeline to `ConnectorEvent` stream
- [ ] Include acknowledgment, resolution, escalation events
- [ ] Event types: `"incident_triggered"`, `"incident_acknowledged"`, `"incident_resolved"`, `"escalation"`

### T3. Wire `PagerDutyAlertAction` (outbound)
- [ ] Already exists as `pagerduty_page.py` — verify it follows the `alert()` pattern
- [ ] Ensure it emits `ConnectorEvent` on success for correlation

### T4. Preserve Phase 3 fixes
- [ ] Dedup-key lookup via `incident_key` filter + alert `alert_key` fallback
- [ ] cp1252 console safety (`_console_notify` sanitization)
- [ ] Verify retry (3 attempts, 2s/4s backoff)

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_pd_watch_returns_handle` | `tests/test_pagerduty_connector.py` | Valid `WatchHandle` |
| `test_pd_get_stats_events` | `tests/test_pagerduty_connector.py` | Incident timeline as `ConnectorEvent` |
| `test_pd_alert_emits_event` | `tests/test_actions.py` | Page creates trackable event |
| `test_pd_dedup_key_regression` | `tests/test_pagerduty_connector.py` | Phase 3 fix not regressed |
| `test_pd_console_encoding` | `tests/test_pagerduty_connector.py` | cp1252 safety maintained |

---

## Acceptance Criteria

- [ ] `watch()` + `get_stats()` functional
- [ ] All 29+ existing PagerDuty tests pass
- [ ] Phase 3 fixes preserved
- [ ] CI green
