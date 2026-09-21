# Alert Actions (Per-Provider Outbound) — New

**Owner:** Anant  
**Status:** Partially built  
**Priority:** Tier 2  
**Depends on:** `00_BASE_INTERFACE.md` (the `alert()` pattern)  

---

## Goal

Every connector that can alert gets a gated `Action` subclass. These are the "notify" step in the autonomous loop: watch → diagnose → fix → verify → **notify**.

---

## Existing Alert Actions

| Action | File | Status |
|---|---|---|
| `datadog-alert` | `datadog_alert.py` | Built |
| `aws-alert` | `aws_alert.py` | Built |
| `gcp-alert` | `gcp_alert.py` | Built |
| `github-alert` | `github_alert.py` | Built |
| `gitlab-alert` | `gitlab_alert.py` | Built |
| `pagerduty-page` | `pagerduty_page.py` | Built (serves as alert for PagerDuty) |
| `gitleaks-escalate` | `gitleaks_escalate.py` | Built (escalates to PagerDuty) |

---

## Tasks

### T1. Audit all alert actions follow the `AlertAction` base pattern
- [ ] All inherit from `AlertActionBase` (or establish one in `alert_base.py`)
- [ ] All have consistent `ActionSpec` with `risk_tier=APPROVAL` by default
- [ ] All emit a `ConnectorEvent` on success (for correlation tracking)

### T2. Missing alert actions
- [ ] `grafana-alert` — POST to Grafana Alerting API
- [ ] `vercel-alert` — if Vercel has an alerting mechanism
- [ ] `snyk-alert` — vulnerability notification escalation
- [ ] `terraform-alert` — drift notification escalation
- [ ] `azure-alert` — Azure Monitor alert

### T3. Alert → Notification channel integration
- [ ] Alert actions can optionally trigger team notifications (Slack/Discord/Email/WhatsApp)
- [ ] Configurable: alert action fires → then also pushes to configured notification channels

### T4. Alert verification
- [ ] Each alert action's `verify()` confirms the alert was received (with retry for propagation delay)

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_alert_base_contract` | `tests/test_actions.py` | All alert actions follow base pattern |
| `test_alert_emits_event` | `tests/test_actions.py` | `ConnectorEvent` emitted on success |
| `test_alert_notification_chain` | `tests/test_notifications.py` | Alert → team notification works |
| `test_alert_verify_retry` | `tests/test_actions.py` | Propagation delay handled |

---

## Acceptance Criteria

- [ ] Every alertable connector has a corresponding alert action
- [ ] All alert actions emit `ConnectorEvent` for correlation
- [ ] Notification channel integration works
