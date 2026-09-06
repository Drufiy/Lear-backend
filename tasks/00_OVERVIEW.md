# Connector Rewrite — Task Overview

**Goal:** Fully autonomous **watch → diagnose → fix → verify → notify** loop for every connector in the Lear system.

**Source of truth:** [`CONNECTOR_REWRITE_SPEC.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/CONNECTOR_REWRITE_SPEC.md) · [`PRASH_V2.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/PRASH_V2.md)

---

## The Autonomous Loop (every connector must complete this)

```
┌─────────┐     ┌───────────┐     ┌──────┐     ┌────────┐     ┌────────┐
│  WATCH  │ ──▶ │ DIAGNOSE  │ ──▶ │ FIX  │ ──▶ │ VERIFY │ ──▶ │ NOTIFY │
│ watch() │     │ get_stats │     │Action│     │verify()│     │ alert  │
│ polls   │     │ brain     │     │ exec │     │re-check│     │ Action │
└─────────┘     └───────────┘     └──────┘     └────────┘     └────────┘
     ▲                                                              │
     └──────────────────── loop back ◀─────────────────────────────┘
```

Every connector rewrite must implement **all five stages** to close the loop.

---

## Shared Interface Contract (from §4 of CONNECTOR_REWRITE_SPEC)

### Read layer additions to `Connector` ABC (`connectors/base.py`)

| Method | Purpose | Returns |
|---|---|---|
| `watch(target)` | Begin monitoring a target; feeds the shared watcher loop | `WatchHandle` |
| `get_stats(target, since?)` | Time-series of normalized events for a target | `list[ConnectorEvent]` |

### `ConnectorEvent` — the cross-provider join shape

```python
class ConnectorEvent(TypedDict):
    timestamp: datetime    # UTC
    connector: str         # e.g. "datadog", "kubernetes"
    event_type: str        # e.g. "metric_spike", "pod_crash"
    summary: str           # one human-readable line
    raw: dict              # untouched provider payload
```

### Write layer — `alert()` as a gated Action per provider

Each provider that can alert gets a new `Action` subclass (e.g. `DatadogAlertAction`, `PagerDutyPageAction`) with `risk_tier=APPROVAL` by default.

---

## Connector Priority Order

From CONNECTOR_REWRITE_SPEC §6 Phase 3, worst-covered surfaces first:

| # | Connector | Task File | Current State |
|---|---|---|---|
| 0 | **Base Interface** | [`01_BASE_INTERFACE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/01_BASE_INTERFACE.md) | `watch()`/`get_stats()` not yet on ABC |
| 1 | **Datadog** (pilot) | [`02_DATADOG.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/02_DATADOG.md) | Read+mute exists, no watch/stats/alert |
| 2 | **Grafana** | [`03_GRAFANA.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/03_GRAFANA.md) | Read+silence exists, no watch/stats/alert |
| 3 | **PagerDuty** | [`04_PAGERDUTY.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/04_PAGERDUTY.md) | Read+ack/resolve exists, no watch/stats/alert |
| 4 | **Kubernetes** | [`05_KUBERNETES.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/05_KUBERNETES.md) | Module-level functions, not Connector class |
| 5 | **AWS** | [`06_AWS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/06_AWS.md) | Instance status + execute, no watch/stats/alert |
| 6 | **GCP** | [`07_GCP.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/07_GCP.md) | Instance status + execute, no watch/stats/alert |
| 7 | **Azure** | [`08_AZURE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/08_AZURE.md) | Instance status + execute, no watch/stats/alert |
| 8 | **GitHub** | [`09_GITHUB.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/09_GITHUB.md) | Workflow logs + PR, no watch/stats/alert |
| 9 | **GitLab** | [`10_GITLAB.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/10_GITLAB.md) | Pipeline logs + MR, no watch/stats/alert |
| 10 | **Vercel** | [`11_VERCEL.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/11_VERCEL.md) | Build logs + deploy/rollback, no watch/stats/alert |
| 11 | **Snyk** | [`12_SNYK.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/12_SNYK.md) | Project state, no watch/stats/alert |
| 12 | **Gitleaks** | [`13_GITLEAKS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/13_GITLEAKS.md) | Local scan, no watch/stats/alert |
| 13 | **Terraform** | [`14_TERRAFORM.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/14_TERRAFORM.md) | State + drift, no watch/stats/alert |

---

## Cross-Cutting Concerns

- **Backward compatibility:** No connector loses existing capabilities (§4e)
- **Every milestone ships with tests** — unit tests + fixture scripts
- **Watcher refactor** (Aradhya's M5): `watcher.py` must poll via connector `watch()`/`get_stats()` instead of hardcoded k8s
- **Correlation** (M6): `ConnectorEvent`s from multiple connectors merge on one timeline
- **CI green** on Linux/Windows/macOS at all times
