# AWS Connector Rewrite — `connectors/aws.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 2  
**Depends on:** `00_BASE_INTERFACE.md`  

---

## Current State

`AWSConnector(Connector)` exists with: `authenticate()` (cached STS), `poll_state()`, `fetch_logs()`, `execute_command()` (SSM + SSH fallback), CloudWatch metrics (`CPUUtilization`, `DiskReadOps`, etc.), `get_stats()` (partial). Write actions: `execute-aws` (APPROVAL). Watcher loop: `run_aws_watch_loop`. Brain integration: `format_aws_context`, `diagnose_aws_instance`.

**Missing:** Proper `watch()` returning `WatchHandle`, `get_stats()` as `ConnectorEvent`, `aws-alert` action.

---

## Tasks

### T1. Implement `watch(target) -> WatchHandle`
- [ ] Target = EC2 instance ID
- [ ] Poll instance state + CloudWatch alarms
- [ ] Detect: instance stopped, status check failed, high CPU, CloudWatch alarm firing
- [ ] Replace `run_aws_watch_loop` with the generic connector `watch()` pattern

### T2. Rewrite `get_stats(target, since?) -> list[ConnectorEvent]`
- [ ] Convert CloudWatch metrics to `ConnectorEvent` stream
- [ ] Convert CloudWatch alarms to events
- [ ] Event types: `"instance_state_change"`, `"metric_spike"`, `"alarm_firing"`, `"status_check_failed"`

### T3. Wire `AWSAlertAction`
- [ ] Already exists as `aws_alert.py` — verify shape
- [ ] Ensure CloudWatch Events or SNS integration

### T4. Preserve SSM/SSH fallback
- [ ] `execute_command` SSM → SSH fallback chain unchanged
- [ ] `SSMFailedNeedsSSH` exception still works for REPL integration

### T5. Preserve cached authentication
- [ ] `authenticate()` caches per instance (not re-hitting STS every call)

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_aws_watch_returns_handle` | `tests/test_aws_connector.py` | Valid `WatchHandle` |
| `test_aws_get_stats_cloudwatch` | `tests/test_aws_connector.py` | CloudWatch → `ConnectorEvent` |
| `test_aws_alert_action` | `tests/test_actions.py` | Alert action pipeline |
| `test_aws_cached_auth` | `tests/test_aws_connector.py` | STS not called redundantly |
| `test_aws_ssm_fallback_preserved` | `tests/test_aws_connector.py` | SSH fallback still works |

---

## Acceptance Criteria

- [ ] `watch()` + `get_stats()` + alert functional
- [ ] All 20+ existing AWS tests pass
- [ ] SSM/SSH fallback intact
- [ ] `run_aws_watch_loop` replaced by generic `watch()` pattern
- [ ] CI green
