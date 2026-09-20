# Kubernetes Actions — `actions/restart_pod.py`, `scale.py`, `exec_command.py`, `edit_config.py`, `rollback.py`, `apply_ci_fix.py`

**Owner:** Aryan (action contract) / Aradhya (connector methods)  
**Status:** Built, needs loop closure  
**Priority:** Tier 1  

---

## Existing Actions (all built and tested)

| Action ID | File | Risk Tier | Status |
|---|---|---|---|
| `restart-pod` | `restart_pod.py` | SAFE | ✅ Live-verified |
| `rollback` | `rollback.py` | APPROVAL | ✅ Wired to `get_previous_revision()` |
| `scale` | `scale.py` | APPROVAL | ✅ Live-verified (1→3, 3→0) |
| `exec` | `exec_command.py` | APPROVAL | ✅ Live-verified (zero + non-zero exit) |
| `edit-configmap` | `edit_config.py` | APPROVAL | ✅ Live-verified |
| `edit-secret` | `edit_config.py` | APPROVAL | ✅ Secret values never in console/audit |
| `apply-manifest-fix` | `apply_ci_fix.py` | SAFE | ✅ Live-verified (real PR #6) |

---

## Tasks (Loop Closure)

### T1. Verify all actions work with new `KubernetesConnector` class
- [ ] `restart_pod.py` — use connector instance instead of module-level function
- [ ] `scale.py` — `scale_deployment()` and `get_deployment_replicas()` via connector
- [ ] `exec_command.py` — `exec_in_pod()` via connector, pod-existence pre-check preserved
- [ ] `edit_config.py` — ConfigMap/Secret CRUD via connector
- [ ] `rollback.py` — `get_previous_revision()` via connector
- [ ] `apply_ci_fix.py` — `apply-manifest-fix` path still works through GitHub connector

### T2. Ensure `verify()` uses new `ConnectorEvent` where applicable
- [ ] `restart_pod.verify()` — can use `get_stats()` to confirm restart event
- [ ] `scale.verify()` — confirm replicas via connector
- [ ] `rollback.verify()` — confirm revision change via connector

### T3. Watcher-triggered action dispatch
- [ ] When watcher detects a problem → diagnosis → recommended action flows through the full pipeline
- [ ] Permission system applies (auto-safe for restart, approval for scale/rollback/exec)
- [ ] Circuit breaker checked before execution

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_restart_uses_connector_class` | `tests/test_actions.py` | Calls connector instance, not module function |
| `test_scale_uses_connector_class` | `tests/test_actions.py` | Same |
| `test_exec_pod_precheck_preserved` | `tests/test_actions.py` | Nonexistent pod fails before exec |
| `test_secret_never_in_audit` | `tests/test_actions.py` | Secret values don't appear in audit log |
| `test_manifest_fix_real_pr` | `tests/test_fix.py` | `apply-manifest-fix` creates real PR |
| `test_watcher_to_action_pipeline` | `tests/test_watcher.py` | Watch → diagnose → dispatch → verify |

---

## Acceptance Criteria

- [ ] All 7 K8s actions work with `KubernetesConnector` class
- [ ] Full watcher → action loop proven
- [ ] Secret safety preserved
- [ ] All 66+ action tests pass
