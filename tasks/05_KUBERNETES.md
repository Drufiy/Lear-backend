# Task 05 — Kubernetes Connector Rewrite

**Priority:** Phase 3, after PagerDuty (upgrade to full watch/stats/alert)  
**Owner:** Decided at M0 (M1b — full convert vs thin adapter)  
**Spec ref:** CONNECTOR_REWRITE_SPEC §4d, §6 M1b  
**Depends on:** `01_BASE_INTERFACE.md`  
**Current file:** [`prash/connectors/kubernetes.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/connectors/kubernetes.py) (531 lines)  
**Existing tests:** [`tests/test_kubernetes_connector.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tests/test_kubernetes_connector.py), [`tests/test_kubernetes_connector_live.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tests/test_kubernetes_connector_live.py)  
**Existing testdata:** `connectors/testdata/broken-pod.yaml`  
**Existing actions:** [`restart_pod.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/actions/restart_pod.py), [`rollback.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/actions/rollback.py), [`scale.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/actions/scale.py)  

---

## ⚠️ Critical Architectural Decision Required (M0/M1b)

**Kubernetes is the odd one out:** it uses module-level functions (`get_pod_status()`, `get_pod_logs()`, etc.) instead of the `Connector` class pattern every other connector follows. The watcher (`watcher.py`) imports directly from these module-level functions.

**Options (decide at M0, record in CONNECTOR_REWRITE_SPEC §8):**

| Option | Pros | Cons |
|---|---|---|
| **Full convert to `KubernetesConnector(Connector)`** | Clean, consistent, natural `watch()`/`get_stats()` home | Largest refactor, touches watcher.py heavily |
| **Thin adapter wrapping existing functions** | Minimal disruption, existing code stays | Two interfaces to maintain, adapter adds indirection |

**Recommendation:** Full convert. The watcher refactor (M5) needs to happen anyway, and the adapter just delays the inevitable.

---

## Goal — The Full Autonomous Loop for Kubernetes

```
Pod crashes / OOMs / ImagePullBackOff → watch() detects (already in watcher.py, hardcoded) →
get_stats() pulls pod event timeline → Brain diagnoses → restart/rollback/scale →
verify() re-checks pod → notify → loop
```

**Note:** Kubernetes is unique — the watch/diagnose/fix loop already exists in a hardcoded form. This rewrite generalizes it to the shared interface.

---

## Current State Audit

| Capability | Status | Notes |
|---|---|---|
| `authenticate()` | ⚠️ Implicit | Uses kubeconfig, no `Connector.authenticate()` |
| `locate()` | ⚠️ Module-level | `get_pod_status()` takes name directly |
| `fetch_logs()` | ⚠️ Module-level | `get_pod_logs()` |
| `poll_state()` | ⚠️ Module-level | `get_pod_status()` → `PodStatus` (NOT `ResourceState`) |
| `restart_pod` | ✅ Done | SAFE tier Action |
| `rollback` | ✅ Done | APPROVAL tier Action |
| `scale` | ✅ Done | APPROVAL tier Action |
| Watcher | ✅ Done (hardcoded) | `watcher.py` imports k8s functions directly |
| `watch()` (interface) | ❌ Missing | Watcher exists but not via `Connector.watch()` |
| `get_stats()` | ❌ Missing | No `ConnectorEvent` emission |
| `alert()` | ❌ Missing | No k8s-native alerting action |

---

## Tasks

### Phase A — Convert to Connector Class (M1b)

- [ ] **Create `KubernetesConnector(Connector)` class** in `kubernetes.py`
  - Move module-level functions into class methods
  - `self.credentials` takes `KUBECONFIG`, `KUBE_CONTEXT`, `KUBE_NAMESPACE`
- [ ] **Implement `authenticate()`** — load kubeconfig, verify cluster access
- [ ] **Implement `locate(resource)`** — resolve pod/deployment/service name
- [ ] **Implement `fetch_logs(resource)`** — wrap `get_pod_logs()` → `list[str]`
- [ ] **Implement `poll_state(resource)`** — wrap `get_pod_status()` → `ResourceState`
  - Map `PodStatus.problem` → `ConnectorState`:
    - `CrashLoopBackOff` → `CRASH_LOOPING`
    - `OOMKilled` → `FAILED`
    - `ImagePullBackOff` → `FAILED`
    - `StuckPending` → `DEGRADED`
    - `None` + `Running` → `HEALTHY`
- [ ] **Keep module-level functions as thin wrappers** (backward compat for watcher.py during transition)
- [ ] **Update `read_capabilities`** = `("pod_status", "logs", "events")`
- [ ] **Update `write_capabilities`** = `("restart", "rollback", "scale")`

### Phase B — Implement `watch()`

- [ ] **Implement `KubernetesConnector.watch(target)`**
  - `target` = namespace/pod-name or namespace (watch all pods)
  - Use Kubernetes watch API (`client.CoreV1Api().list_namespaced_pod(watch=True)`) for real-time events
  - Fall back to polling if watch API disconnects
  - Detect the four problem states: CrashLoopBackOff, OOMKilled, ImagePullBackOff, StuckPending
  - Return `WatchHandle`
- [ ] **Add `"watch"` to `read_capabilities`**
- [ ] **Support namespace-wide watching** — all pods in a namespace
- [ ] **Support cluster-wide watching** — all namespaces (with optional label selectors)

### Phase C — Implement `get_stats()`

- [ ] **Implement `KubernetesConnector.get_stats(target, since)`**
  - Pull from:
    - Pod events (`client.CoreV1Api().list_namespaced_event()`)
    - Pod status history (restart timestamps, condition transition times)
    - Deployment rollout history
  - Normalize to `ConnectorEvent`:
    ```python
    ConnectorEvent(
        timestamp=event_last_timestamp,
        connector="kubernetes",
        event_type="pod_crash",  # or "oom_kill", "image_pull_fail", "deployment_rollout", "node_pressure"
        summary="Pod 'api-server-xyz' CrashLoopBackOff (restart_count=5) in namespace 'production'",
        raw={...full k8s event...}
    )
    ```
- [ ] **Include deployment events** — rollouts, scaling, config changes
- [ ] **Include node-level events** — node pressure, scheduling failures
- [ ] **Add `"stats"` to `read_capabilities`**

### Phase D — Implement `kubernetes-alert` Action

- [ ] **Create `prash/actions/kubernetes_alert.py`**
  - Kubernetes itself doesn't have native alerting, but Lear can:
    - Create a Kubernetes Event as an annotation
    - Send notifications via configured channels (this is really a Lear notification, not k8s-native)
  - **Decision:** Risk tier = SAFE (creating a k8s Event is internal, read-only, reversible)
- [ ] **Alternative approach:** Skip a k8s-specific alert action — k8s alerting is handled by Datadog/Grafana/PagerDuty watching k8s. The brain should route to those connectors for alerting.
- [ ] **Decision: document which approach in §8**

### Phase E — Connector Fine-Tuning

- [ ] **Multi-cluster support:** Support `KUBE_CONTEXT` switching between clusters
- [ ] **Label selector filtering:** Watch only pods matching specific labels (e.g., `app=api-server`)
- [ ] **Resource type expansion:** Beyond pods — Deployments, StatefulSets, DaemonSets, Jobs
- [ ] **Event deduplication:** K8s events are noisy — deduplicate by `reason + involvedObject`
- [ ] **Container-level granularity:** Multi-container pods — identify which container crashed
- [ ] **Init container handling:** Distinguish init container failures from main container failures
- [ ] **Resource quota awareness:** Detect when failures are caused by resource quota exhaustion
- [ ] **Node affinity/anti-affinity issues:** Detect scheduling failures due to topology constraints
- [ ] **PVC mount failures:** Detect persistent volume claim mount issues
- [ ] **ConfigMap/Secret mount failures:** Detect missing or invalid mounted configs

### Phase F — Watcher Refactor (M5 — Aradhya)

- [ ] **Refactor `watcher.py`** to use `KubernetesConnector.watch()`/`get_stats()` instead of importing module-level functions directly
- [ ] **Ensure `prash watch` still works** identically for k8s (backward compat §4e)
- [ ] **`prash watch` now accepts `--provider kubernetes`** explicitly
- [ ] **Combined watch:** `prash watch` without `--provider` polls ALL configured connectors

### Phase G — Brain Integration

- [ ] **Brain already understands k8s** — this is the core use case (PRASH_V2 §0b)
- [ ] **Ensure brain receives `ConnectorEvent`s** instead of raw `PodStatus` objects
- [ ] **Correlation:** k8s events + Datadog metrics + deployment history = richer diagnosis
- [ ] **Fix verification:** After restart/rollback/scale, brain verifies via `poll_state()` → `get_stats()`

---

## Testing Methodology

### Unit Tests (`tests/test_kubernetes_connector.py` — extend)
- [ ] `test_connector_class_authenticate` — kubeconfig loading
- [ ] `test_connector_class_locate` — pod/deployment resolution
- [ ] `test_connector_class_poll_state` — PodStatus → ResourceState mapping
- [ ] `test_connector_class_fetch_logs` — log retrieval
- [ ] `test_watch_detects_crash_loop`
- [ ] `test_watch_detects_oom_kill`
- [ ] `test_watch_detects_image_pull_backoff`
- [ ] `test_watch_detects_stuck_pending`
- [ ] `test_watch_namespace_wide`
- [ ] `test_get_stats_returns_pod_events_as_connector_events`
- [ ] `test_get_stats_includes_deployment_events`
- [ ] `test_get_stats_respects_since`
- [ ] `test_backward_compat_module_functions` — old functions still callable
- [ ] `test_multi_container_pod_identification`

### Integration Tests (live)
- [ ] `connectors/testdata/broken-pod.yaml` — apply broken pod to kind cluster
- [ ] `prash watch --provider kubernetes` detects the broken pod
- [ ] `prash fix <namespace>/<pod>` diagnoses and restarts
- [ ] Verify pod recovers post-restart
- [ ] End-to-end loop works identically to current behavior

### Backward Compatibility (CRITICAL)
- [ ] `from prash.connectors.kubernetes import get_pod_status` still works
- [ ] `from prash.connectors.kubernetes import get_pod_logs` still works
- [ ] `from prash.connectors.kubernetes import PodStatus` still works
- [ ] `watcher.py` works unchanged during transition period
- [ ] `restart_pod`, `rollback`, `scale` actions unchanged
- [ ] All existing k8s tests pass

---

## Definition of Done

- [ ] `KubernetesConnector(Connector)` class fully implements the ABC
- [ ] `watch()` detects all four problem states via the Connector interface
- [ ] `get_stats()` returns normalized `ConnectorEvent`s from k8s events
- [ ] Watcher refactored to use Connector interface (M5)
- [ ] Module-level functions preserved as backward-compat wrappers
- [ ] All existing k8s functionality preserved (restart, rollback, scale)
- [ ] Combined fixture (M6): k8s pod crash + Datadog spike → one correlated hypothesis
- [ ] Tests green on all platforms
