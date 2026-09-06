# Task 07 — GCP Connector Rewrite

**Priority:** Phase 3, after AWS  
**Owner:** Anant  
**Spec ref:** CONNECTOR_REWRITE_SPEC §6 Phase 3  
**Depends on:** `01_BASE_INTERFACE.md`  
**Current file:** [`prash/connectors/gcp.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/connectors/gcp.py) (252 lines)  
**Existing tests:** [`tests/test_gcp_connector.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tests/test_gcp_connector.py)  
**Existing fixture:** [`scripts/testing/break_gcp.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/scripts/testing/break_gcp.py) — **does not exist yet, must be created**  
**Existing actions:** [`execute_gcp.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/actions/execute_gcp.py)  

---

## Goal — The Full Autonomous Loop for GCP

```
GCE instance degraded/stopped → watch() detects instance state →
get_stats() pulls Cloud Monitoring metrics + activity logs →
Brain diagnoses → execute command (gcloud/SSH) → verify() re-checks →
notify → loop
```

---

## Current State Audit

| Capability | Status | Notes |
|---|---|---|
| `authenticate()` | ✅ Done | Service account file or ADC, cached |
| `locate()` | ✅ Done | Instance by name, auto-discovers zone |
| `fetch_logs()` | ✅ Done | Serial port output or gcloud logs |
| `poll_state()` | ✅ Done | Instance status → `ConnectorState` |
| `execute_command()` | ✅ Done | gcloud CLI → SSH fallback (`GCPRunCommandFailedNeedsSSH`) |
| `watch()` | ❌ Missing | |
| `get_stats()` | ❌ Missing | |
| `alert()` | ❌ Missing | |
| Break fixture | ❌ Missing | No `break_gcp.py` exists |

**Key design notes:**
- GCP uses `google-api-python-client` SDK with optional `gcloud` CLI fallback
- Zone discovery is auto-cached per instance (`_zone_cache`)
- Auth supports both service account JSON and Application Default Credentials (ADC)

---

## Tasks

### Phase A — API Scope & IAM Audit

- [ ] **Document required GCP IAM roles** for each new capability:
  - `watch()`: `compute.instances.get`, `compute.instances.list`, `monitoring.timeSeries.list`
  - `get_stats()`: `monitoring.timeSeries.list`, `logging.logEntries.list`
  - `alert()`: `monitoring.alertPolicies.create` or `pubsub.topics.publish`
- [ ] **Decide alert mechanism:**
  - Option A: Publish to Pub/Sub topic → APPROVAL
  - Option B: Create Cloud Monitoring alert policy → APPROVAL
  - **Recommendation:** Pub/Sub for immediate notification, Cloud Monitoring for persistent
- [ ] **Check SDK availability** — already guarded with `_HAS_GCP` flag

### Phase B — Implement `watch()`

- [ ] **Implement `GCPConnector.watch(target)`**
  - `target` = instance name (zone auto-discovered from cache)
  - Poll Compute Engine instance state: `RUNNING`, `STOPPED`, `TERMINATED`, `SUSPENDED`, `STAGING`
  - Poll instance guest attributes / serial port for crash signals
  - Detect transitions: RUNNING→STOPPED, RUNNING→TERMINATED
- [ ] **Return `WatchHandle`**
- [ ] **Multi-zone/multi-instance support**
- [ ] **Add `"watch"` to `read_capabilities`**

### Phase C — Implement `get_stats()`

- [ ] **Implement `GCPConnector.get_stats(target, since)`**
  - Pull from:
    - **Compute Engine instance status** changes
    - **Cloud Monitoring metrics**: `compute.googleapis.com/instance/cpu/utilization`, `disk/read_bytes_count`, `network/received_bytes_count`
    - **Cloud Audit Logs**: instance start/stop/delete operations via `logging.logEntries.list`
    - **Cloud Logging**: application logs (if available)
  - Normalize to `ConnectorEvent`:
    ```python
    ConnectorEvent(
        timestamp=event_time,
        connector="gcp",
        event_type="instance_stopped",  # or "cpu_spike", "disk_full", "audit_operation"
        summary="Instance 'web-server-1' stopped in zone us-central1-a",
        raw={...full GCP event...}
    )
    ```
- [ ] **Add `"stats"` to `read_capabilities`**
- [ ] **Handle `gcloud` CLI fallback** for metrics when SDK unavailable

### Phase D — Implement `gcp-alert` Action

- [ ] **Create `prash/actions/gcp_alert.py`**
  ```python
  class GCPAlertAction(Action):
      spec = ActionSpec(
          id="gcp-alert",
          summary="Publish an alert via GCP Pub/Sub or create a Cloud Monitoring alert",
          risk_tier=RiskTier.APPROVAL,
          reversible=False,
          capabilities=("alert",),
      )
  ```
- [ ] **`execute()`** — Publish message to configured Pub/Sub topic
- [ ] **`verify()`** — Check Pub/Sub publish response
- [ ] **Require `GCP_PUBSUB_TOPIC`** — new credential for alert target
- [ ] **Register** in dispatcher

### Phase E — Connector Fine-Tuning

- [ ] **Multi-project support:** Some teams have workloads across GCP projects
- [ ] **Zone auto-discovery improvement:** Current `_zone_cache` is per-instance — make it proactive via `aggregatedList`
- [ ] **Managed Instance Group (MIG) awareness:** Detect auto-scaling events
- [ ] **Cloud Run integration stub:** Prepare for Cloud Run service monitoring (not just GCE)
- [ ] **GKE integration:** If the cluster is GKE, correlate with Kubernetes connector
- [ ] **CLI fallback robustness:** `gcloud` commands vary by version — pin minimum version or detect capabilities
- [ ] **Service account key rotation:** Handle credential refresh for long-running watches
- [ ] **Preemptible/Spot VM handling:** Preemption events as a distinct `event_type`
- [ ] **Network interface monitoring:** Detect connectivity issues via instance network status

### Phase F — Create Missing Fixture

- [ ] **Create `scripts/testing/break_gcp.py`**
  - Stop a GCE instance to simulate failure
  - Trigger a resource quota limit
  - Create a known-bad configuration (missing metadata)
  - Must be safe to run and clean up after itself

### Phase G — Watcher & Brain Integration

- [ ] **Register GCP in `watcher.py`** — `prash watch --provider gcp`
- [ ] **Brain mapping:**
  - Instance stopped → check Cloud Audit Logs (who stopped it? scheduled maintenance?)
  - CPU spike → check application logs, suggest scaling or exec diagnostic command
  - Preemption event → suggest migration to on-demand or different machine type
- [ ] **Fix loop:** Execute via gcloud/SSH → verify instance recovers → notify

---

## Testing Methodology

### Unit Tests (`tests/test_gcp_connector.py` — extend)
- [ ] `test_watch_detects_instance_stopped` — mock Compute API
- [ ] `test_watch_detects_instance_terminated`
- [ ] `test_get_stats_includes_instance_events`
- [ ] `test_get_stats_includes_monitoring_metrics`
- [ ] `test_get_stats_includes_audit_logs`
- [ ] `test_get_stats_respects_since`
- [ ] `test_alert_action_publishes_pubsub`
- [ ] `test_zone_cache_persistence` — zone discovered once, reused
- [ ] `test_sdk_fallback_to_gcloud_cli`
- [ ] `test_adc_and_service_account_auth` — both paths work

### Integration Tests
- [ ] `scripts/testing/break_gcp.py` — degrade a GCE instance
- [ ] End-to-end: instance stops → watch → brain → gcloud exec → verify → notify

### Backward Compatibility
- [ ] `authenticate()` unchanged (cached)
- [ ] `execute_command()` gcloud → SSH fallback unchanged
- [ ] `GCPRunCommandFailedNeedsSSH` unchanged
- [ ] `execute-gcp` action unchanged
- [ ] All existing tests pass

---

## Definition of Done

- [ ] `watch()` detects GCE instance state changes
- [ ] `get_stats()` returns `ConnectorEvent`s from Cloud Monitoring + Audit Logs
- [ ] `gcp-alert` Action publishes to Pub/Sub, gated at APPROVAL
- [ ] `break_gcp.py` fixture created and working
- [ ] Watcher integration works
- [ ] Brain diagnoses GCP issues with monitoring/audit context
- [ ] Autonomous loop proven end-to-end
- [ ] All existing tests green
