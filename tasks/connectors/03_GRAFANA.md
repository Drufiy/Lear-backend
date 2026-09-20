# Grafana Connector Rewrite — `connectors/grafana.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 2  
**Depends on:** `00_BASE_INTERFACE.md`, `02_DATADOG.md` (pattern proven)  

---

## Current State

`GrafanaConnector(Connector)` exists with: `authenticate()`, `poll_state()`, `fetch_logs()`, `get_stats()` (partial). Write action: `grafana-silence` (SAFE tier).

**Missing:** `watch()`, proper `ConnectorEvent` output, `grafana-alert` action.

---

## Tasks

### T1. Implement `watch(target) -> WatchHandle`
- [ ] Poll alert rule state changes (OK → Alerting → No Data)
- [ ] Target can be alert rule UID or `"all"`
- [ ] State transitions map to WatchHandle health

### T2. Rewrite `get_stats(target, since?) -> list[ConnectorEvent]`
- [ ] Convert alert annotations to `ConnectorEvent`
- [ ] Convert dashboard panel anomalies to events
- [ ] Event types: `"alert_firing"`, `"alert_resolved"`, `"panel_anomaly"`

### T3. Wire `GrafanaAlertAction`
- [ ] Create `prash/actions/grafana_alert.py` (or extend existing)
- [ ] `ActionSpec(id="grafana-alert", risk_tier=APPROVAL)`
- [ ] POST to Grafana Alerting API
- [ ] Verify alert appears

### T4. Brain context update
- [ ] Ensure `format_grafana_context()` feeds `ConnectorEvent` to diagnosis
- [ ] Verify brain can distinguish Grafana context from Datadog

### T5. Preserve existing functionality
- [ ] `grafana-silence` action unchanged
- [ ] All 22+ existing tests pass

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_grafana_watch_returns_handle` | `tests/test_grafana_connector.py` | Valid `WatchHandle` |
| `test_grafana_get_stats_events` | `tests/test_grafana_connector.py` | `ConnectorEvent` shape |
| `test_grafana_alert_action` | `tests/test_actions.py` | Alert action full pipeline |
| `test_grafana_silence_unbroken` | `tests/test_grafana_connector.py` | Existing silence works |

---

## Acceptance Criteria

- [ ] `watch()` + `get_stats()` + `grafana-alert` all functional
- [ ] All existing Grafana tests pass
- [ ] CI green
