# Kubernetes Connector Rewrite — `connectors/kubernetes.py`

**Owner:** Aradhya  
**Status:** Not started  
**Priority:** Tier 1  
**Depends on:** `00_BASE_INTERFACE.md`  
**Blocks:** Watcher multi-provider refactor, Correlation module  

---

## Current State

`kubernetes.py` is the **odd one out** — it uses module-level functions (`get_pod_status()`, `get_pod_logs()`, etc.) instead of a `KubernetesConnector(Connector)` class. This is the only connector that doesn't follow the ABC pattern. It must be refactored to a class to participate in `watch()`/`get_stats()`.

### Existing module-level functions to wrap:
- `get_pod_status(namespace, pod_name)` → `poll_state(target)`
- `get_pod_logs(namespace, pod_name, ...)` → `fetch_logs(target, ...)`
- `get_pod_events(namespace, pod_name)` → internal to `get_stats()`
- `restart_pod(namespace, pod_name)` → stays in `restart_pod` action
- `get_previous_revision(namespace, pod_name)` → `get_previous_revision(target)`
- `scale_deployment(namespace, name, replicas)` → stays in `scale` action
- `get_deployment_replicas(namespace, name)` → utility
- `get_configmap(namespace, name)` / `update_configmap(...)` → stays in `edit_config` action
- `get_secret_keys(namespace, name)` / `update_secret(...)` → stays in `edit_config` action
- `exec_in_pod(namespace, pod, ...)` → stays in `exec` action
- `stream_pod_logs(namespace, pod)` → `stream_logs(target)` or stays as utility

---

## Tasks

### T1. Refactor to `KubernetesConnector(Connector)` class
- [ ] Create `class KubernetesConnector(Connector)` with `__init__(self, kubeconfig: str | None = None)`
- [ ] Implement `authenticate()` — load kubeconfig, create k8s client
- [ ] Implement `locate(target: str)` — parse `namespace/pod_name` format
- [ ] Move `get_pod_status` → `poll_state(target) -> ResourceState`
- [ ] Move `get_pod_logs` → `fetch_logs(target, since?) -> str`
- [ ] Set `read_capabilities` and `write_capabilities` correctly
- [ ] Keep module-level functions as **thin wrappers** around the class methods for backward compat (deprecation path, not instant removal)

### T2. Implement `watch(target) -> WatchHandle`
- [ ] Return a `WatchHandle` configured for the given `namespace/pod`
- [ ] Detection states: `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, stuck Pending >2min
- [ ] Handle feeds into `watcher.py`'s shared loop via the standardized interface

### T3. Implement `get_stats(target, since?) -> list[ConnectorEvent]`
- [ ] Convert pod events (`get_pod_events`) to `ConnectorEvent` format
- [ ] Include restart counts, state transitions, warning events
- [ ] Respect `since` parameter for time-series windowing
- [ ] Each event has: `timestamp`, `connector="kubernetes"`, `event_type`, `summary`, `raw`

### T4. Update all consumers of module-level functions
- [ ] `prash/fix.py` — update `format_k8s_context`, `cmd_fix_k8s`
- [ ] `prash/watcher.py` — update `run_watch_loop` to use connector class
- [ ] `prash/cli.py` — update `cmd_investigate`, `cmd_logs`
- [ ] `prash/actions/restart_pod.py` — use connector instance
- [ ] `prash/actions/scale.py` — use connector instance
- [ ] `prash/actions/edit_config.py` — use connector instance
- [ ] `prash/actions/exec_command.py` — use connector instance
- [ ] `prash/actions/rollback.py` — use connector instance
- [ ] `prash/brain/diagnosis_agent.py` — `format_k8s_context`

### T5. Update `connector_registry.py` entry
- [ ] Register `KubernetesConnector` with correct metadata, auth fields, widget templates
- [ ] Ensure `lazy_instance` caching works with the new class

### T6. Preserve backward-compatible module-level aliases
- [ ] `get_pod_status = KubernetesConnector._default_instance().poll_state` (or similar delegation)
- [ ] Ensure `test_kubernetes_connector.py` and `test_kubernetes_connector_live.py` still pass

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_k8s_connector_instantiates` | `tests/test_kubernetes_connector.py` | Class can be created with mock kubeconfig |
| `test_k8s_authenticate` | `tests/test_kubernetes_connector.py` | Loads kubeconfig, creates client |
| `test_k8s_poll_state` | `tests/test_kubernetes_connector.py` | Returns `ResourceState` for a pod |
| `test_k8s_fetch_logs` | `tests/test_kubernetes_connector.py` | Returns decoded log text (not `b'...'`) |
| `test_k8s_watch_returns_handle` | `tests/test_kubernetes_connector.py` | `watch()` returns a valid `WatchHandle` |
| `test_k8s_get_stats_returns_events` | `tests/test_kubernetes_connector.py` | Events are `ConnectorEvent` shaped |
| `test_k8s_get_stats_since_filter` | `tests/test_kubernetes_connector.py` | Only returns events after `since` |
| `test_k8s_backward_compat_functions` | `tests/test_kubernetes_connector.py` | Module-level aliases still work |
| `test_k8s_live_watch_crashloop` | `tests/test_kubernetes_connector_live.py` | Live `kind` cluster detects CrashLoopBackOff |
| `test_k8s_live_get_stats` | `tests/test_kubernetes_connector_live.py` | Live `kind` cluster returns real events |

---

## Acceptance Criteria

- [ ] `KubernetesConnector` is a proper `Connector` subclass
- [ ] `watch()` and `get_stats()` return correct types
- [ ] All 20+ existing mocked k8s tests pass
- [ ] All 7 live `kind` tests pass
- [ ] Watcher still detects CrashLoopBackOff/OOMKilled/ImagePullBackOff
- [ ] `prash fix namespace/pod` still works end to end
- [ ] CI green on all 3 OSes
