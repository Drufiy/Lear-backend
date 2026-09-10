# Task 02 — Datadog Connector Rewrite (Pilot)

**Priority:** Phase 2 — first connector to prove the full autonomous loop  
**Owner:** Anant (real execution) · Aradhya (NLP integration)  
**Spec ref:** CONNECTOR_REWRITE_SPEC §6 M2–M4  
**Depends on:** `01_BASE_INTERFACE.md`  
**Current file:** [`prash/connectors/datadog.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/connectors/datadog.py) (170 lines)  
**Existing tests:** [`tests/test_datadog_connector.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tests/test_datadog_connector.py)  
**Existing fixture:** [`scripts/testing/break_datadog.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/scripts/testing/break_datadog.py)  
**Existing action:** [`prash/actions/datadog_mute.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/actions/datadog_mute.py)  

---

## Goal — The Full Autonomous Loop for Datadog

```
Datadog monitor fires → watch() detects state change → get_stats() pulls timeline →
Brain diagnoses root cause → Action executed (mute/alert) → verify() confirms →
Notification sent → loop continues watching
```

---

## Current State Audit

| Capability | Status | Notes |
|---|---|---|
| `authenticate()` | ✅ Done | `/v1/validate` API key check |
| `locate()` | ✅ Done | Monitor ID or name search |
| `fetch_logs()` | ✅ Done | `/v2/logs/events/search` |
| `poll_state()` | ✅ Done | Maps `overall_state` → `ConnectorState` |
| `mute_monitor()` | ✅ Done | Wired via `datadog_mute` Action |
| `watch()` | ❌ Missing | No monitoring/polling capability |
| `get_stats()` | ❌ Missing | No time-series `ConnectorEvent` emission |
| `alert()` | ❌ Missing | No outbound alert Action |
| Watcher integration | ❌ Missing | Not in `watcher.py` |

---

## Tasks

### Phase A — API Scope Audit (M2)

- [ ] **Document required Datadog API scopes** for `watch()`, `get_stats()`, and `alert()`
  - `watch()`: Monitor search/get endpoints (existing scopes suffice)
  - `get_stats()`: Events API v2 (`/v2/events`), Metrics API (`/v1/query`), Monitors API
  - `alert()`: Monitors API create/update, or Events API v2 post
- [ ] **Decide alert risk tier:** Is `datadog_alert` APPROVAL or SAFE?
  - Default: APPROVAL (outbound, not cleanly reversible)
  - Argument for SAFE: Datadog alerts are internal/mutable — but creating a monitor alert is visible to the whole team
  - **Decision:** Log reasoning in CONNECTOR_REWRITE_SPEC §8

### Phase B — Implement `watch()` (M4)

- [ ] **Implement `DatadogConnector.watch(target)`**
  - `target` = monitor ID or name
  - Internally: poll `/v1/monitor/{id}` at the watcher interval
  - Detect state transitions: OK→Alert, OK→Warn, Alert→OK
  - Return a `WatchHandle` that the shared watcher loop can call
- [ ] **Add `"watch"` to `read_capabilities`**
- [ ] **Handle multi-monitor watching** — support watching multiple monitors simultaneously
- [ ] **Implement exponential backoff** on Datadog API rate limits (429s)

### Phase C — Implement `get_stats()` (M4)

- [ ] **Implement `DatadogConnector.get_stats(target, since)`**
  - Pull from multiple Datadog sources:
    - Monitor state changes (via `/v1/monitor/{id}/` history)
    - Events API v2 (`/v2/events`) — deploy events, alerting events
    - Optionally: metric query results (`/v1/query`) for context
  - Normalize every entry into `ConnectorEvent`:
    ```python
    ConnectorEvent(
        timestamp=event_time,         # UTC
        connector="datadog",
        event_type="monitor_alert",   # or "metric_spike", "deploy_event"
        summary="Monitor 'CPU High' entered Alert state",
        raw={...full Datadog payload...}
    )
    ```
- [ ] **Add `"stats"` to `read_capabilities`**
- [ ] **Respect `since` parameter** — only return events after the given time
- [ ] **Sort events by timestamp** (ascending, oldest first)

### Phase D — Implement `datadog_alert` Action (M4)

- [ ] **Create `prash/actions/datadog_alert.py`**
  ```python
  class DatadogAlertAction(Action):
      spec = ActionSpec(
          id="datadog-alert",
          summary="Create or trigger a Datadog monitor alert",
          risk_tier=RiskTier.APPROVAL,
          reversible=False,
          capabilities=("alert",),
          approval_hint="This will create a visible alert in Datadog"
      )
  ```
- [ ] **Implement `plan()`** — describe what alert will be created
- [ ] **Implement `execute()`** — POST to Datadog Events API v2 or create a monitor alert
- [ ] **Implement `verify()`** — confirm the event/alert was created via GET
- [ ] **Register in `prash/actions/__init__.py`** and dispatcher

### Phase E — Connector Fine-Tuning

- [ ] **Rate limit handling:** Implement retry with exponential backoff for 429 responses
- [ ] **Regional support:** Ensure `DATADOG_SITE` works correctly for all regions (US1, US3, US5, EU, AP1)
- [ ] **Connection pooling:** Reuse HTTP connections across multiple API calls within a single poll cycle
- [ ] **Timeout tuning:** Review 30s timeout — too aggressive for large log searches, too generous for monitor checks
- [ ] **Error classification:** Differentiate transient errors (network, 500, 429) from permanent ones (401, 403, 404)
- [ ] **Credential rotation awareness:** Handle API key rotation gracefully (re-auth on 401)
- [ ] **Monitor group support:** Support Datadog monitor groups (multi-alert monitors with per-scope states)
- [ ] **Metric correlation:** When a monitor fires, auto-fetch the underlying metric data as context for the brain

### Phase F — Watcher Integration

- [ ] **Register Datadog in `watcher.py`** alongside Kubernetes
- [ ] **Implement `detect_changes()` for Datadog** — track monitor state transitions
- [ ] **Desktop + team notifications** on Datadog state changes
- [ ] **Configurable watch targets** — which monitors to watch (env var or config)

### Phase G — Brain Integration

- [ ] **Teach the diagnosis brain** about Datadog event types
- [ ] **Map Datadog alert patterns to fix suggestions:**
  - Monitor Alert → mute + investigate underlying metric
  - Metric spike → check correlated services
  - Downtime event → check for related deploys
- [ ] **NLP routing** — "watch this Datadog monitor" → `watch()`, "what happened on Datadog" → `get_stats()`

---

## Testing Methodology

### Unit Tests (`tests/test_datadog_connector.py` — extend)
- [ ] `test_watch_returns_watch_handle` — mock API, verify handle properties
- [ ] `test_watch_detects_state_transition` — OK→Alert triggers change
- [ ] `test_watch_no_duplicate_notification` — same state across polls = silent
- [ ] `test_get_stats_returns_connector_events` — verify shape and normalization
- [ ] `test_get_stats_respects_since_parameter` — only events after `since`
- [ ] `test_get_stats_sorts_by_timestamp` — ascending order
- [ ] `test_get_stats_empty_result` — no events returns empty list
- [ ] `test_alert_action_plan` — verify plan description
- [ ] `test_alert_action_execute` — mock API, verify POST
- [ ] `test_alert_action_verify` — mock API, confirm event exists
- [ ] `test_rate_limit_429_retry` — verify exponential backoff on 429
- [ ] `test_regional_site_urls` — US1, EU, US3, US5, AP1 base URLs
- [ ] `test_credential_rotation_reauth` — 401 triggers re-authentication

### Integration Tests (live, manual)
- [ ] `scripts/testing/break_datadog.py` — trigger a real monitor alert
- [ ] Verify `watch()` detects the alert within one poll cycle
- [ ] Verify `get_stats()` returns a `ConnectorEvent` for the alert
- [ ] Verify `datadog-alert` action creates a visible event in Datadog
- [ ] Verify end-to-end: break → watch → brain → action → verify → notify

### Fixture Tests
- [ ] **Single-connector fixture:** Use `break_datadog.py` to create a known bad state
- [ ] **Combined fixture (M6):** Datadog spike + k8s pod crash in same window → one correlated hypothesis

---

## Backward Compatibility

- [ ] `authenticate()` unchanged
- [ ] `locate()` unchanged
- [ ] `fetch_logs()` unchanged
- [ ] `poll_state()` unchanged
- [ ] `mute_monitor()` unchanged
- [ ] `datadog_mute` action still works
- [ ] All existing `test_datadog_connector.py` tests pass

---

## Definition of Done

- [ ] `watch()` polls Datadog monitors and detects state changes
- [ ] `get_stats()` returns normalized `ConnectorEvent`s from Datadog timeline
- [ ] `datadog-alert` Action creates Datadog events, gated at APPROVAL tier
- [ ] Watcher integration: `prash watch --provider datadog` works
- [ ] Brain can diagnose Datadog alerts and suggest fixes
- [ ] End-to-end loop: watch → diagnose → fix → verify → notify proven with `break_datadog.py`
- [ ] All existing functionality preserved
- [ ] Tests green on all platforms
