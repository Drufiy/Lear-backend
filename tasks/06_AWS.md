# Task 06 — AWS Connector Rewrite

**Priority:** Phase 3, after Kubernetes  
**Owner:** Anant  
**Spec ref:** CONNECTOR_REWRITE_SPEC §6 Phase 3  
**Depends on:** `01_BASE_INTERFACE.md`  
**Current file:** [`prash/connectors/aws.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/connectors/aws.py) (334 lines)  
**Existing tests:** [`tests/test_aws_connector.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tests/test_aws_connector.py)  
**Existing fixture:** [`scripts/testing/break_aws.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/scripts/testing/break_aws.py)  
**Existing actions:** [`execute_aws.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/actions/execute_aws.py)  

---

## Goal — The Full Autonomous Loop for AWS

```
EC2 instance degraded/stopped → watch() detects instance state change →
get_stats() pulls CloudWatch metrics + instance events →
Brain diagnoses (high CPU? disk full? OOM?) → execute command / restart →
verify() re-checks instance → notify → loop
```

---

## Current State Audit

| Capability | Status | Notes |
|---|---|---|
| `authenticate()` | ✅ Done | STS `get_caller_identity()`, cached per instance |
| `locate()` | ✅ Done | EC2 instance by name tag or ID |
| `fetch_logs()` | ✅ Done | CloudWatch Logs or SSM output |
| `poll_state()` | ✅ Done | EC2 instance state → `ConnectorState` |
| `execute_command()` | ✅ Done | SSM → SSH fallback (with `SSMFailedNeedsSSH`) |
| `watch()` | ❌ Missing | |
| `get_stats()` | ❌ Missing | |
| `alert()` | ❌ Missing | |

**Key design:** AWS has the richest monitoring surface — CloudWatch Metrics, CloudWatch Alarms, EC2 status checks, CloudTrail events. The rewrite should tap into all of these.

---

## Tasks

### Phase A — API Scope & IAM Audit

- [ ] **Document required IAM permissions** for each new capability:
  - `watch()`: `ec2:DescribeInstances`, `ec2:DescribeInstanceStatus`, `cloudwatch:DescribeAlarms`
  - `get_stats()`: `cloudwatch:GetMetricData`, `cloudtrail:LookupEvents`, `ec2:DescribeInstanceStatus`
  - `alert()`: `sns:Publish` or `cloudwatch:PutMetricAlarm`
- [ ] **Decide alert mechanism:**
  - Option A: Publish to SNS topic → APPROVAL (outbound, wakes people)
  - Option B: Create CloudWatch Alarm → APPROVAL (creates infrastructure)
  - Option C: Both, selected by user preference
  - **Recommendation:** SNS publish for immediate paging, CloudWatch alarm for persistent monitoring
- [ ] **Check boto3 dependency** — already optional-import guarded with `_HAS_BOTO3`

### Phase B — Implement `watch()`

- [ ] **Implement `AWSConnector.watch(target)`**
  - `target` = instance ID or name tag
  - Poll EC2 instance state: `running`, `stopped`, `terminated`, `pending`, `shutting-down`
  - Poll EC2 status checks: `instance-status`, `system-status` (impaired/ok/initializing)
  - Poll CloudWatch Alarms associated with the instance
  - Detect transitions: running→stopped, ok→impaired, alarm→ok
- [ ] **Return `WatchHandle`** with stop/is_active
- [ ] **Add `"watch"` to `read_capabilities`**
- [ ] **Multi-instance watching** — support watching multiple instances simultaneously

### Phase C — Implement `get_stats()`

- [ ] **Implement `AWSConnector.get_stats(target, since)`**
  - Pull from multiple AWS sources:
    - **EC2 instance state changes** (via `DescribeInstanceStatus`)
    - **CloudWatch metrics**: CPUUtilization, NetworkIn/Out, DiskReadOps, StatusCheckFailed
    - **CloudTrail events**: instance launches, terminations, security group changes
    - **CloudWatch Alarms**: alarm state changes
  - Normalize to `ConnectorEvent`:
    ```python
    ConnectorEvent(
        timestamp=event_time,
        connector="aws",
        event_type="instance_stopped",  # or "cpu_spike", "status_check_failed", "security_group_change"
        summary="Instance i-0abc123 stopped unexpectedly in us-east-1",
        raw={...full AWS event...}
    )
    ```
- [ ] **Add `"stats"` to `read_capabilities`**
- [ ] **Metric aggregation:** For CloudWatch metrics, aggregate into meaningful events (e.g., CPU > 90% for 5 min = "cpu_spike")
- [ ] **CloudTrail integration:** Recent API calls that affected the instance (who did what)

### Phase D — Implement `aws-alert` Action

- [ ] **Create `prash/actions/aws_alert.py`**
  ```python
  class AWSAlertAction(Action):
      spec = ActionSpec(
          id="aws-alert",
          summary="Publish an alert via AWS SNS or create a CloudWatch Alarm",
          risk_tier=RiskTier.APPROVAL,
          reversible=False,
          capabilities=("alert",),
          approval_hint="This will publish a message to an SNS topic"
      )
  ```
- [ ] **`execute()`** — `sns:Publish` to configured SNS topic ARN
- [ ] **`verify()`** — check SNS publish response for `MessageId`
- [ ] **Require `AWS_SNS_TOPIC_ARN`** — new credential for alert target
- [ ] **Register** in dispatcher

### Phase E — Connector Fine-Tuning

- [ ] **Region-aware multi-instance:** Support instances across multiple AWS regions
- [ ] **ASG (Auto Scaling Group) awareness:** Detect ASG scaling events as context
- [ ] **ECS/EKS integration stub:** Prepare for future container service monitoring (beyond EC2)
- [ ] **SSM fallback resilience:** Improve SSH fallback flow — detect `.pem` file availability proactively
- [ ] **Cost awareness:** CloudWatch API calls cost money — optimize polling frequency and metric queries
- [ ] **Credential chain flexibility:** Support IAM roles, instance profiles, SSO (beyond access key/secret)
- [ ] **VPC/subnet context:** Include networking context in diagnosis (security groups, NACLs)
- [ ] **EBS volume monitoring:** Disk I/O and volume health as diagnosis context
- [ ] **Spot instance handling:** Spot interruptions as a distinct event type

### Phase F — Watcher & Brain Integration

- [ ] **Register AWS in `watcher.py`** — `prash watch --provider aws`
- [ ] **Brain mapping:**
  - Instance stopped → check CloudTrail (who stopped it?), check ASG (expected scaling?)
  - CPU spike → check application logs via SSM, suggest scaling or restart
  - Status check failed → hardware issue → suggest replacement instance
  - Security group change → correlate with access patterns
- [ ] **Fix loop:** Execute command via SSM → verify instance recovers → notify

---

## Testing Methodology

### Unit Tests (`tests/test_aws_connector.py` — extend)
- [ ] `test_watch_detects_instance_stopped` — mock EC2 describe
- [ ] `test_watch_detects_status_check_failed` — impaired status
- [ ] `test_watch_detects_cloudwatch_alarm` — alarm state change
- [ ] `test_get_stats_includes_instance_events`
- [ ] `test_get_stats_includes_cloudwatch_metrics` — CPU/disk/network
- [ ] `test_get_stats_includes_cloudtrail_events`
- [ ] `test_get_stats_respects_since`
- [ ] `test_alert_action_publishes_sns`
- [ ] `test_alert_action_requires_topic_arn`
- [ ] `test_multi_region_support`
- [ ] `test_credential_caching` — STS not called on every method

### Integration Tests
- [ ] `scripts/testing/break_aws.py` — stop/degrade an EC2 instance
- [ ] End-to-end: instance stops → watch → brain → SSM execute → verify → notify

### Backward Compatibility
- [ ] `authenticate()` caching unchanged
- [ ] `execute_command()` SSM → SSH fallback unchanged
- [ ] `SSMFailedNeedsSSH` exception unchanged
- [ ] `execute-aws` action unchanged
- [ ] All existing tests pass

---

## Definition of Done

- [ ] `watch()` detects EC2 instance state changes and status check failures
- [ ] `get_stats()` returns `ConnectorEvent`s from CloudWatch + CloudTrail + EC2 events
- [ ] `aws-alert` Action publishes to SNS, gated at APPROVAL
- [ ] Watcher integration works (`prash watch --provider aws`)
- [ ] Brain diagnoses AWS issues with CloudWatch/CloudTrail context
- [ ] Autonomous loop: watch → diagnose → execute → verify → notify
- [ ] All existing tests green
