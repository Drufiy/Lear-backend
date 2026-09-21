# Lear — Master Task Breakdown

**Source of truth:** [`PRASH_V2.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/PRASH_V2.md) · [`CHANGELOG.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/CHANGELOG.md) · [`CONNECTOR_REWRITE_SPEC.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/CONNECTOR_REWRITE_SPEC.md)

---

## Module Map

| Module | Subfolder | Files | Status |
|---|---|---|---|
| **Connectors (Read Layer)** | `connectors/` | 14 connector task files + base interface | Rewrite in progress |
| **Actions (Write Layer)** | `actions/` | 7 action group task files | Built, needs loop closure |
| **Brain (Diagnosis Engine)** | `brain/` | 5 task files | Core working, depth expansion |
| **CLI & Interface** | `cli/` | 4 task files | REPL done, TUI hardening |
| **Watcher & Monitoring** | `watcher/` | 3 task files | K8s working, multi-source next |
| **Desktop App** | `desktop/` | Existing `00_DESKTOP_OVERVIEW.md` | v2.0 shipped |
| **Infrastructure & DevOps** | `infra/` | 3 task files | CI, deployment, hosting |
| **Cross-Cutting** | `cross-cutting/` | 4 task files | Audit, permissions, circuit breaker |

---

## Task Files Index

### `connectors/` — Read Layer & Connector Rewrite
- [`00_BASE_INTERFACE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/00_BASE_INTERFACE.md) — ABC additions: `watch()`, `get_stats()`, `ConnectorEvent`
- [`01_KUBERNETES.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/01_KUBERNETES.md) — Refactor to class, full loop closure
- [`02_DATADOG.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/02_DATADOG.md) — Pilot: watch/stats/alert
- [`03_GRAFANA.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/03_GRAFANA.md) — Watch/stats/alert
- [`04_PAGERDUTY.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/04_PAGERDUTY.md) — Watch/stats/alert
- [`05_AWS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/05_AWS.md) — Watch/stats/alert
- [`06_GCP.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/06_GCP.md) — Watch/stats/alert
- [`07_AZURE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/07_AZURE.md) — Watch/stats/alert
- [`08_GITHUB.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/08_GITHUB.md) — Watch/stats/alert
- [`09_GITLAB.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/09_GITLAB.md) — Watch/stats/alert
- [`10_VERCEL.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/10_VERCEL.md) — Watch/stats/alert
- [`11_SNYK.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/11_SNYK.md) — Watch/stats/alert
- [`12_GITLEAKS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/12_GITLEAKS.md) — Watch/stats/alert
- [`13_TERRAFORM.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/connectors/13_TERRAFORM.md) — Watch/stats/alert

### `actions/` — Write Layer & Action Loop Closure
- [`00_ACTION_CONTRACT.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/actions/00_ACTION_CONTRACT.md) — Action contract hardening
- [`01_KUBERNETES_ACTIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/actions/01_KUBERNETES_ACTIONS.md) — restart, scale, exec, edit-configmap, edit-secret, rollback, apply-manifest-fix
- [`02_CI_ACTIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/actions/02_CI_ACTIONS.md) — apply-ci-fix, apply-gitlab-ci-fix, open-pr, request-secret
- [`03_CLOUD_ACTIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/actions/03_CLOUD_ACTIONS.md) — execute-aws, execute-azure, execute-gcp
- [`04_MONITORING_ACTIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/actions/04_MONITORING_ACTIONS.md) — datadog-mute, grafana-silence, pagerduty-ack/resolve/page, snyk-ignore, gitleaks-escalate
- [`05_INFRA_ACTIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/actions/05_INFRA_ACTIONS.md) — terraform-init, terraform-apply, vercel-deploy/rollback
- [`06_ALERT_ACTIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/actions/06_ALERT_ACTIONS.md) — New alert actions (per-provider outbound alerts)

### `brain/` — Diagnosis Engine
- [`00_BRAIN_OVERVIEW.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/brain/00_BRAIN_OVERVIEW.md) — Architecture & diagnosis pipeline overview
- [`01_DIAGNOSIS_AGENT.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/brain/01_DIAGNOSIS_AGENT.md) — Prompt engineering, domain expansion
- [`02_MULTI_DIAGNOSIS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/brain/02_MULTI_DIAGNOSIS.md) — Multi-failure decomposition & fix
- [`03_CORRELATION.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/brain/03_CORRELATION.md) — Cross-connector event correlation
- [`04_SCHEMAS_AND_MODELS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/brain/04_SCHEMAS_AND_MODELS.md) — Diagnosis schema, FileChange/FileEdit, model client

### `cli/` — CLI, REPL, & Interface
- [`00_CLI_OVERVIEW.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cli/00_CLI_OVERVIEW.md) — CLI architecture overview
- [`01_CLI_COMMANDS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cli/01_CLI_COMMANDS.md) — All CLI subcommands
- [`02_REPL_AND_INTENT.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cli/02_REPL_AND_INTENT.md) — Interactive REPL & free-text intent parsing
- [`03_TUI_AND_UI.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cli/03_TUI_AND_UI.md) — Rich TUI, fix rendering, options display

### `watcher/` — Background Monitoring
- [`00_WATCHER_OVERVIEW.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/watcher/00_WATCHER_OVERVIEW.md) — Watcher architecture
- [`01_WATCHER_CORE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/watcher/01_WATCHER_CORE.md) — Poll loop, multi-provider refactor, notifications
- [`02_NOTIFICATIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/watcher/02_NOTIFICATIONS.md) — Slack, Discord, Email, WhatsApp, PagerDuty channels

### `infra/` — Infrastructure & Deployment
- [`00_CI_CD.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/infra/00_CI_CD.md) — GitHub Actions, cross-platform CI
- [`01_HOSTING.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/infra/01_HOSTING.md) — Autopilot deployment strategy
- [`02_PACKAGING.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/infra/02_PACKAGING.md) — pip/npm packaging, `prash setup` wizard

### `cross-cutting/` — Shared Systems
- [`00_PERMISSIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cross-cutting/00_PERMISSIONS.md) — Permission engine, 5-mode system
- [`01_AUDIT_LOG.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cross-cutting/01_AUDIT_LOG.md) — Audit trail, provenance tracking
- [`02_CIRCUIT_BREAKER.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cross-cutting/02_CIRCUIT_BREAKER.md) — Rate limiting, escalation
- [`03_CREDENTIALS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/cross-cutting/03_CREDENTIALS.md) — Local credential management, .env handling

### `desktop/` — Desktop App (Tauri)
- Existing: [`00_DESKTOP_OVERVIEW.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/00_DESKTOP_OVERVIEW.md)

---

## Priority Tiers (cut from bottom, never top)

**Tier 1 — The autonomous loop must work for at least one connector.**
Base interface · K8s connector rewrite · Datadog pilot · Brain domain expansion · Watcher multi-provider refactor · Correlation module

**Tier 2 — Known-valuable, loop survives without them.**
Remaining connector rewrites (Grafana, PagerDuty, AWS, GCP) · New alert actions · REPL intent depth · Desktop API hardening

**Tier 3 — Drop first.**
Azure/GitHub/GitLab/Vercel/Snyk/Gitleaks/Terraform connector rewrites · Hosting/deployment automation · Advanced correlation features
