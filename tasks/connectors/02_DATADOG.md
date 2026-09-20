# Datadog Connector Rewrite (Pilot) — `connectors/datadog.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 1 (pilot connector — proves the pattern for all others)  
**Depends on:** `00_BASE_INTERFACE.md`  
**Blocks:** Grafana, PagerDuty, and all subsequent connector rewrites (pattern must work here first)  

---

## Current State

`DatadogConnector(Connector)` already exists as a class with:
- `authenticate()` — validates API/app keys
- `poll_state(target)` → `ResourceState` (monitor status)
- `fetch_logs(target)` → metric time-series
- `get_stats(target)` → partial implementation (monitor details + metrics)
- Write action: `datadog-mute` (SAFE tier)

**Missing:** `watch()`, proper `get_stats()` returning `ConnectorEvent`, `datadog-alert` action.

---

## Tasks

### T1. Implement `watch(target) -> WatchHandle`
- [ ] `target` is a monitor ID or `"all"` for all monitors
- [ ] Poll monitor status changes (OK → Alert, Alert → OK)
- [ ] Return `WatchHandle` with appropriate interval (default 30s)
- [ ] State transitions: monitor Alert/Warn → `degraded`, multi-alert → `error`

### T2. Rewrite `get_stats(target, since?) -> list[ConnectorEvent]`
- [ ] Convert monitor state changes to `ConnectorEvent` format
- [ ] Convert metric anomalies to events
- [ ] Include: `event_type` values like `"monitor_alert"`, `"monitor_recovery"`, `"metric_spike"`
- [ ] Normalize timestamps to UTC
- [ ] Preserve `raw` payload for correlation module

### T3. Wire `DatadogAlertAction` (new alert action)
- [ ] Create `prash/actions/datadog_alert.py` (already exists as `datadog_alert.py`)
- [ ] `ActionSpec(id="datadog-alert", risk_tier=APPROVAL)`
- [ ] `plan()` — describe what alert will be created
- [ ] `execute()` — POST to Datadog Events API
- [ ] `verify()` — confirm event appears in Datadog

### T4. Brain context integration
- [ ] Ensure `format_datadog_context()` works with new `get_stats()` output
- [ ] Add worked examples to diagnosis prompt for Datadog-sourced incidents
- [ ] Test that diagnosis brain can propose `datadog-mute` or `datadog-alert` from Datadog context

### T5. Desktop API integration
- [ ] Verify `/api/connectors/datadog/stats` returns `ConnectorEvent[]`
- [ ] Verify `/api/connectors/datadog/watch` creates a `WatchHandle`
- [ ] Verify WebSocket `/ws/events` broadcasts Datadog events

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_datadog_watch_returns_handle` | `tests/test_datadog_connector.py` | `watch()` returns valid `WatchHandle` |
| `test_datadog_watch_detects_alert` | `tests/test_datadog_connector.py` | Monitor OK→Alert produces event |
| `test_datadog_get_stats_event_shape` | `tests/test_datadog_connector.py` | Events match `ConnectorEvent` schema |
| `test_datadog_get_stats_since_filter` | `tests/test_datadog_connector.py` | Time filtering works |
| `test_datadog_alert_action_plan` | `tests/test_actions.py` | Alert action produces correct plan |
| `test_datadog_alert_action_execute` | `tests/test_actions.py` | Alert POSTs to Events API |
| `test_datadog_alert_action_verify` | `tests/test_actions.py` | Verification confirms event exists |
| `test_datadog_brain_context` | `tests/test_brain_datadog_context.py` | Brain receives Datadog events correctly |
| `test_datadog_existing_mute_unbroken` | `tests/test_datadog_connector.py` | Existing `datadog-mute` still works |

---

## Acceptance Criteria

- [ ] `watch()` returns `WatchHandle`, polls monitor status
- [ ] `get_stats()` returns `list[ConnectorEvent]`
- [ ] `datadog-alert` action goes through full permission/circuit-breaker/audit pipeline
- [ ] All existing Datadog tests pass (28+ tests in `test_datadog_connector.py`)
- [ ] Pattern is validated: same approach works for Grafana/PagerDuty
- [ ] CI green on all 3 OSes
