# GCP Connector Rewrite — `connectors/gcp.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 3  
**Depends on:** `00_BASE_INTERFACE.md`, `05_AWS.md` (same pattern)  

---

## Current State

`GCPConnector(Connector)` mirrors AWS pattern: `authenticate()`, `poll_state()`, `fetch_logs()`, `execute_command()` (SDK → `gcloud` CLI → SSH fallback). Write action: `execute-gcp` (APPROVAL).

**Missing:** `watch()`, `get_stats()` as `ConnectorEvent`, `gcp-alert` action.

---

## Tasks

### T1. Implement `watch(target) -> WatchHandle`
- [ ] Target = Compute Engine instance name/ID
- [ ] Poll instance state + Cloud Monitoring metrics
- [ ] Detect: instance terminated, high CPU, disk pressure

### T2. Rewrite `get_stats(target, since?) -> list[ConnectorEvent]`
- [ ] Cloud Monitoring → `ConnectorEvent` stream
- [ ] Event types: `"instance_state_change"`, `"metric_anomaly"`

### T3. Wire `GCPAlertAction`
- [ ] `gcp-alert` action via Cloud Monitoring / Cloud Functions
- [ ] APPROVAL tier

### T4. Preserve SDK → CLI → SSH fallback chain

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_gcp_watch` | `tests/test_gcp_connector.py` | Valid `WatchHandle` |
| `test_gcp_get_stats` | `tests/test_gcp_connector.py` | `ConnectorEvent` shape |
| `test_gcp_fallback` | `tests/test_gcp_connector.py` | SDK → CLI → SSH preserved |

---

## Acceptance Criteria

- [ ] `watch()` + `get_stats()` functional
- [ ] All existing GCP tests pass
- [ ] CI green
