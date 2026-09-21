# Cloud Execution Actions — `execute_aws.py`, `execute_azure.py`, `execute_gcp.py`

**Owner:** Anant  
**Status:** Built  
**Priority:** Tier 2  

---

## Existing Actions (all APPROVAL tier)

| Action ID | File | Fallback Chain |
|---|---|---|
| `execute-aws` | `execute_aws.py` | SSM → SSH (`.pem` file prompt) |
| `execute-azure` | `execute_azure.py` | SDK → `az` CLI → SSH |
| `execute-gcp` | `execute_gcp.py` | SDK → `gcloud` CLI → SSH |

---

## Tasks

### T1. Verify fallback chains intact after connector rewrite
- [ ] SSM → SSH for AWS (catches `SSMFailedNeedsSSH`)
- [ ] Azure SDK → `az` CLI → SSH
- [ ] GCP SDK → `gcloud` → SSH
- [ ] All three prompt for `.pem` file interactively when SSH fallback is needed

### T2. Wire into watcher-triggered pipeline
- [ ] When cloud connector `watch()` detects issue → brain diagnoses → recommends `execute-*`
- [ ] APPROVAL tier enforced (never auto-executed)

### T3. Audit trail for remote execution
- [ ] Every command execution logged with: instance ID, command, exit code, truncated output
- [ ] Output capped at 20K chars (same as exec_in_pod)

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_aws_execute_ssm` | `tests/test_actions.py` | SSM execution path |
| `test_aws_execute_ssh_fallback` | `tests/test_actions.py` | SSH fallback on SSM failure |
| `test_azure_execute_fallback` | `tests/test_actions.py` | SDK → CLI → SSH chain |
| `test_gcp_execute_fallback` | `tests/test_actions.py` | Same |
| `test_cloud_exec_audit` | `tests/test_audit.py` | Execution logged with details |

---

## Acceptance Criteria

- [ ] All three fallback chains work after connector rewrite
- [ ] APPROVAL tier enforced
- [ ] Audit trail complete
