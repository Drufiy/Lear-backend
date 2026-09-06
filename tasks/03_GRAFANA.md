# Task 03 — Grafana Connector Rewrite

**Priority:** Phase 3, first after Datadog pilot  
**Owner:** Anant (real execution) · Aradhya (NLP + correlation)  
**Spec ref:** CONNECTOR_REWRITE_SPEC §6 Phase 3  
**Depends on:** `01_BASE_INTERFACE.md`, `02_DATADOG.md` (pattern established)  
**Current file:** [`prash/connectors/grafana.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/connectors/grafana.py) (167 lines)  
**Existing tests:** [`tests/test_grafana_connector.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tests/test_grafana_connector.py)  
**Existing fixture:** [`scripts/testing/break_grafana.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/scripts/testing/break_grafana.py)  
**Existing action:** [`prash/actions/grafana_silence.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/actions/grafana_silence.py)  

---

## Goal — The Full Autonomous Loop for Grafana

```
Grafana alert fires → watch() detects alert state → get_stats() pulls alert/annotation timeline →
Brain diagnoses root cause → Action (silence/alert) → verify() confirms → notify → loop
```

---

## Current State Audit

| Capability | Status | Notes |
|---|---|---|
| `authenticate()` | ✅ Done | Bearer token against Grafana URL |
| `locate()` | ✅ Done | Alert rule by UID or title |
| `fetch_logs()` | ✅ Done | Annotations timeline (not Loki) |
| `poll_state()` | ✅ Done | Alert state from Alertmanager API |
| `silence_alert()` | ✅ Done | Wired via `grafana_silence` Action |
| `watch()` | ❌ Missing | |
| `get_stats()` | ❌ Missing | |
| `alert()` | ❌ Missing | |

---

## Tasks

### Phase A — API Scope & Architecture Audit

- [ ] **Document Grafana API endpoints** for watch/stats/alert:
  - Alertmanager alerts: `/api/alertmanager/grafana/api/v2/alerts`
  - Alert rule provisioning: `/api/v1/provisioning/alert-rules`
  - Annotations: `/api/annotations`
  - Alert notifications: `/api/v1/provisioning/contact-points`
- [ ] **Address known limitation:** `locate()` lists ALL alert rules (no server-side filter) — consider caching for watch
- [ ] **Decide alert risk tier:** Grafana alert via contact point is outbound → APPROVAL
- [ ] **Self-hosted vs Cloud:** Ensure `GRAFANA_URL` flexibility handles both

### Phase B — Implement `watch()`

- [ ] **Implement `GrafanaConnector.watch(target)`**
  - Poll Alertmanager alerts endpoint for state changes
  - Track transitions: inactive→active (firing), active→suppressed (silenced), active→inactive (resolved)
  - Return `WatchHandle` with stop/is_active
- [ ] **Cache alert rule list** — don't re-list all rules every poll cycle
- [ ] **Handle Grafana HA setups** — multiple Grafana instances with same backend
- [ ] **Add `"watch"` to `read_capabilities`**

### Phase C — Implement `get_stats()`

- [ ] **Implement `GrafanaConnector.get_stats(target, since)`**
  - Pull from:
    - Alert state history (Alertmanager alerts with `startsAt`/`endsAt`)
    - Annotations timeline (`/api/annotations`) — deploy markers, state changes
  - Normalize to `ConnectorEvent`:
    ```python
    ConnectorEvent(
        timestamp=alert_starts_at,
        connector="grafana",
        event_type="alert_firing",  # or "alert_resolved", "annotation", "silence_created"
        summary="Alert 'High CPU' firing in folder 'Production'",
        raw={...full Grafana alert payload...}
    )
    ```
- [ ] **Add `"stats"` to `read_capabilities`**
- [ ] **Include Grafana annotation tags** as event context

### Phase D — Implement `grafana_alert` Action

- [ ] **Create `prash/actions/grafana_alert.py`**
  ```python
  class GrafanaAlertAction(Action):
      spec = ActionSpec(
          id="grafana-alert",
          summary="Create a Grafana annotation or trigger a contact point notification",
          risk_tier=RiskTier.APPROVAL,
          reversible=True,  # annotations can be deleted
          capabilities=("alert",),
      )
  ```
- [ ] **`execute()`** — POST annotation to Grafana (`/api/annotations`)
- [ ] **`verify()`** — GET annotation back to confirm creation
- [ ] **Register** in actions `__init__.py` and dispatcher

### Phase E — Connector Fine-Tuning

- [ ] **Self-hosted URL validation:** Validate `GRAFANA_URL` format on init (strip trailing slash, ensure scheme)
- [ ] **Auth method flexibility:** Support both API keys and service account tokens (same header, different lifetimes)
- [ ] **Loki integration stub:** Prepare for future Loki log search (datasource discovery, LogQL queries)
- [ ] **Dashboard link generation:** When an alert fires, include a direct link to the related dashboard
- [ ] **Org-scoped isolation:** Respect `X-Grafana-Org-Id` header for multi-org setups
- [ ] **Rate limiting:** Grafana has no formal rate limits, but self-hosted instances may — add configurable backoff
- [ ] **Error classification:** Distinguish auth errors (401/403) from connectivity issues

### Phase F — Watcher & Brain Integration

- [ ] **Register Grafana in `watcher.py`** — `prash watch --provider grafana`
- [ ] **Desktop + team notifications** on Grafana alert state changes
- [ ] **Brain mapping:**
  - Grafana alert firing → check underlying data source, suggest silence + investigate
  - Annotation pattern → correlate with deploys/changes

---

## Testing Methodology

### Unit Tests (`tests/test_grafana_connector.py` — extend)
- [ ] `test_watch_detects_alert_firing` — inactive→active transition
- [ ] `test_watch_detects_alert_resolved` — active→inactive transition
- [ ] `test_watch_handles_silenced_alerts` — suppressed state tracking
- [ ] `test_get_stats_returns_events_from_annotations`
- [ ] `test_get_stats_returns_events_from_alerts`
- [ ] `test_get_stats_respects_since_parameter`
- [ ] `test_alert_action_creates_annotation`
- [ ] `test_alert_action_verifies_annotation`
- [ ] `test_self_hosted_url_handling` — various URL formats
- [ ] `test_multi_org_header` — org-scoped requests

### Integration Tests
- [ ] `scripts/testing/break_grafana.py` — trigger a real alert rule
- [ ] End-to-end: fire alert → watch detects → brain diagnoses → silence action → verify → notify

### Backward Compatibility
- [ ] All existing `test_grafana_connector.py` tests pass
- [ ] `grafana_silence` action unchanged
- [ ] `fetch_logs()` (annotations) unchanged
- [ ] `poll_state()` unchanged

---

## Definition of Done

- [ ] `watch()` detects Grafana alert state transitions
- [ ] `get_stats()` returns normalized `ConnectorEvent`s from Grafana timeline
- [ ] `grafana-alert` Action creates annotations, gated at APPROVAL
- [ ] Watcher integration works
- [ ] Brain handles Grafana alert patterns
- [ ] Autonomous loop proven with `break_grafana.py`
- [ ] All existing tests green
