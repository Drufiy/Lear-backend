# Task 04 — PagerDuty Connector Rewrite

**Priority:** Phase 3, after Grafana  
**Owner:** Anant (real execution) · Aradhya (NLP + correlation)  
**Spec ref:** CONNECTOR_REWRITE_SPEC §6 Phase 3  
**Depends on:** `01_BASE_INTERFACE.md`  
**Current file:** [`prash/connectors/pagerduty.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/connectors/pagerduty.py) (184 lines)  
**Existing tests:** [`tests/test_pagerduty_connector.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tests/test_pagerduty_connector.py)  
**Existing fixture:** [`scripts/testing/break_pagerduty.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/scripts/testing/break_pagerduty.py)  
**Existing action:** [`prash/actions/pagerduty_incident.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/actions/pagerduty_incident.py)  

---

## Goal — The Full Autonomous Loop for PagerDuty

```
PagerDuty incident triggers → watch() detects new/changed incidents →
get_stats() pulls incident timeline → Brain diagnoses → Action (ack/resolve/page) →
verify() confirms incident state → notify team → loop
```

---

## Current State Audit

| Capability | Status | Notes |
|---|---|---|
| `authenticate()` | ✅ Done | REST API key against `/abilities` |
| `locate()` | ✅ Done | Service by name or ID |
| `fetch_logs()` | ✅ Done | Incident log entries |
| `poll_state()` | ✅ Done | Triggered/acknowledged incidents |
| `acknowledge_incident()` | ✅ Done | Via `pagerduty_incident` Action |
| `resolve_incident()` | ✅ Done | Via `pagerduty_incident` Action |
| `trigger_event()` | ✅ Done | Events API v2 (routing key) |
| `watch()` | ❌ Missing | |
| `get_stats()` | ❌ Missing | |
| `page` (outbound) Action | ❌ Missing | |

**Key architectural note:** PagerDuty has TWO auth models — REST API (API key for read/ack/resolve) and Events API v2 (routing key for trigger/page). The `page` action must use the Events API v2, not the REST API.

---

## Tasks

### Phase A — API Scope & Auth Audit

- [ ] **Document the dual auth model clearly:**
  - REST API key (`PAGERDUTY_API_KEY`): read incidents, ack, resolve
  - Events API v2 routing key (`PAGERDUTY_ROUTING_KEY`): trigger new incidents
  - `PAGERDUTY_FROM_EMAIL`: required for REST API writes (ack/resolve)
- [ ] **Decide `pagerduty-page` risk tier:**
  - Default: APPROVAL (pages a human, not reversible, outbound)
  - This is NOT like muting — it actively wakes someone up
  - **Decision: APPROVAL, no argument for SAFE here**

### Phase B — Implement `watch()`

- [ ] **Implement `PagerDutyConnector.watch(target)`**
  - `target` = service name or ID
  - Poll `/incidents?service_ids[]={id}&statuses[]=triggered&statuses[]=acknowledged`
  - Detect: new incident triggered, incident acknowledged, incident resolved, incident escalated
  - Return `WatchHandle`
- [ ] **Track incident state transitions** — triggered→ack, ack→resolved, triggered→escalated
- [ ] **De-duplicate across polls** — same incident ID shouldn't re-notify unless state changes
- [ ] **Add `"watch"` to `read_capabilities`**

### Phase C — Implement `get_stats()`

- [ ] **Implement `PagerDutyConnector.get_stats(target, since)`**
  - Pull from:
    - Incidents for the service (with log entries): `/incidents/{id}/log_entries`
    - Change events: `/change_events`
    - Incident timeline
  - Normalize to `ConnectorEvent`:
    ```python
    ConnectorEvent(
        timestamp=incident_created_at,
        connector="pagerduty",
        event_type="incident_triggered",  # or "incident_acknowledged", "incident_resolved", "escalation"
        summary="Incident #1234: 'Database connection pool exhausted' on service 'API Backend'",
        raw={...full PagerDuty incident...}
    )
    ```
- [ ] **Include change events** in timeline (deploys, config changes linked to PD)
- [ ] **Add `"stats"` to `read_capabilities`**

### Phase D — Implement `pagerduty-page` Action

- [ ] **Create `prash/actions/pagerduty_page.py`**
  ```python
  class PagerDutyPageAction(Action):
      spec = ActionSpec(
          id="pagerduty-page",
          summary="Page an on-call responder via PagerDuty",
          risk_tier=RiskTier.APPROVAL,
          reversible=False,
          capabilities=("alert",),
          approval_hint="This will page the on-call engineer and wake them up"
      )
  ```
- [ ] **`execute()`** — POST to Events API v2 (`events.pagerduty.com/v2/enqueue`)
- [ ] **`verify()`** — check the `dedup_key` response, verify incident created via REST API
- [ ] **Require `PAGERDUTY_ROUTING_KEY`** — fail cleanly if missing
- [ ] **Register** in dispatcher

### Phase E — Connector Fine-Tuning

- [ ] **Pagination handling:** PagerDuty paginates incidents — implement cursor-based pagination
- [ ] **Urgency awareness:** Respect PagerDuty urgency levels (high/low) in `ConnectorEvent` context
- [ ] **Escalation policy context:** Include escalation policy info in `get_stats()` raw data
- [ ] **Service dependency mapping:** PagerDuty supports service dependencies — surface for correlation
- [ ] **On-call schedule awareness:** Know who's on-call before suggesting a page action
- [ ] **Rate limit handling:** PagerDuty has strict rate limits (900 req/min for REST API) — implement backoff
- [ ] **Event deduplication:** Use PagerDuty's `dedup_key` to prevent duplicate incident creation
- [ ] **Priority levels:** Map PagerDuty priority (P1–P5) to Lear severity

### Phase F — Watcher & Brain Integration

- [ ] **Register PagerDuty in `watcher.py`** — `prash watch --provider pagerduty`
- [ ] **Brain mapping:**
  - New triggered incident → investigate underlying cause across other connectors
  - Escalation event → increase urgency of diagnosis
  - Change event preceding incident → likely root cause (deploy?)
- [ ] **Correlation with other connectors:**
  - PagerDuty incident + k8s pod crash + recent deploy = one root cause
  - PagerDuty incident + Datadog metric spike = one root cause

---

## Testing Methodology

### Unit Tests (`tests/test_pagerduty_connector.py` — extend)
- [ ] `test_watch_detects_new_incident`
- [ ] `test_watch_detects_incident_acknowledged`
- [ ] `test_watch_detects_incident_resolved`
- [ ] `test_watch_no_duplicate_on_same_incident`
- [ ] `test_get_stats_includes_incidents_and_log_entries`
- [ ] `test_get_stats_includes_change_events`
- [ ] `test_get_stats_respects_since`
- [ ] `test_page_action_uses_events_api` — verify Events API v2, not REST
- [ ] `test_page_action_requires_routing_key`
- [ ] `test_page_action_verify_checks_incident`
- [ ] `test_dual_auth_model` — REST key vs routing key used correctly
- [ ] `test_pagination_handling` — paginated incident lists

### Integration Tests
- [ ] `scripts/testing/break_pagerduty.py` — trigger a real PagerDuty incident
- [ ] End-to-end: incident triggers → watch → brain → ack/resolve → verify → notify

### Backward Compatibility
- [ ] `acknowledge_incident()` unchanged
- [ ] `resolve_incident()` unchanged
- [ ] `trigger_event()` unchanged
- [ ] `pagerduty_incident` action still works
- [ ] All existing tests pass

---

## Definition of Done

- [ ] `watch()` detects PagerDuty incident state changes
- [ ] `get_stats()` returns normalized `ConnectorEvent`s with incident timeline
- [ ] `pagerduty-page` Action pages on-call via Events API, gated at APPROVAL
- [ ] Watcher integration works
- [ ] Brain diagnoses PagerDuty incidents and correlates with other signals
- [ ] Autonomous loop proven with `break_pagerduty.py`
- [ ] All existing tests green
