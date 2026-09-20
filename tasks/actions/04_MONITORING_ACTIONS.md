# Monitoring & Security Actions

**Owner:** Aryan  
**Status:** Built  
**Priority:** Tier 2  

---

## Existing Actions

| Action ID | File | Risk Tier | Notes |
|---|---|---|---|
| `datadog-mute` | `datadog_mute.py` | SAFE | Mutes a monitor temporarily |
| `grafana-silence` | `grafana_silence.py` | SAFE | Silences an alert rule |
| `pagerduty-acknowledge` | `pagerduty_incident.py` | SAFE | Acknowledges an incident |
| `pagerduty-resolve` | `pagerduty_incident.py` | SAFE | Resolves an incident |
| `pagerduty-page` | `pagerduty_page.py` | APPROVAL | Creates a new incident |
| `snyk-ignore` | `snyk_ignore.py` | APPROVAL | Accepts a known vulnerability |
| `gitleaks-escalate` | `gitleaks_escalate.py` | SAFE | Opens PagerDuty incident (no secret text) |

---

## Tasks

### T1. Wire all monitoring actions into the watcher loop
- [ ] Watcher → Datadog monitor alert → brain diagnoses → recommends `datadog-mute` or investigate
- [ ] Watcher → Grafana alert → brain → recommends `grafana-silence` or investigate
- [ ] Watcher → PagerDuty incident → brain → recommends `pagerduty-acknowledge`

### T2. Ensure `verify()` on each monitoring action
- [ ] `datadog-mute.verify()` — confirms monitor is muted
- [ ] `grafana-silence.verify()` — confirms silence is active
- [ ] `pagerduty-page.verify()` — bounded retry (3 attempts, 2s/4s backoff) for propagation delay
- [ ] `snyk-ignore.verify()` — confirms issue marked as ignored
- [ ] `gitleaks-escalate.verify()` — confirms PagerDuty incident created

### T3. Security action safety
- [ ] `gitleaks-escalate` never includes secret text in PagerDuty incident
- [ ] `snyk-ignore` requires APPROVAL because accepting a vulnerability is a judgment call
- [ ] `pagerduty-page` APPROVAL tier enforced

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_monitoring_actions_verify` | `tests/test_actions.py` | Every action's verify() is non-trivial |
| `test_gitleaks_no_secret_leak` | `tests/test_actions.py` | Secret text never in incident body |
| `test_pd_page_retry` | `tests/test_pagerduty_connector.py` | Propagation delay retry works |
| `test_snyk_ignore_approval` | `tests/test_actions.py` | APPROVAL tier enforced |

---

## Acceptance Criteria

- [ ] All 7 monitoring/security actions wired into watcher loop
- [ ] `verify()` actually checks system state for each
- [ ] Secret safety preserved for gitleaks
