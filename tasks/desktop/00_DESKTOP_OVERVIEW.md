# Lear Desktop App — Feature Spec Overview

**Goal:** A consumer-centric desktop application that connects live to any backend service, feeds data into Lear's AI for analysis, and watches services in real-time — like Vercel for your entire infrastructure. The primary target is a **business demo** that proves Lear's value to prospective customers.

**Primary demo connector:** AWS EC2 (with architecture supporting all 13 connectors)

**Product name:** Lear (rebranded from "Prash" throughout all UI)

**Tech stack:** Tauri v2 (Rust backend) + React + TypeScript + Tailwind v4 + Framer Motion + FastAPI (Python API bridge)

**Last audit:** 2026-09-11

---

## Architecture

```
┌─────────────────────────────────────┐
│          Tauri Desktop App          │
│  ┌───────────────────────────────┐  │
│  │   React Frontend (Vite)      │  │
│  │   port :1420                  │  │
│  │   ┌─────────┐ ┌───────────┐  │  │
│  │   │ Widgets │ │  Chat UI  │  │  │
│  │   │ Sidebar │ │  Projects │  │  │
│  │   └────┬────┘ └─────┬─────┘  │  │
│  └────────┼─────────────┼────────┘  │
│           │  HTTP/WS    │           │
│  ┌────────▼─────────────▼────────┐  │
│  │   FastAPI Backend (Python)    │  │
│  │   port :8000                  │  │
│  │   ┌──────────────────────┐    │  │
│  │   │  Connector Registry  │    │  │
│  │   │  13 connectors       │    │  │
│  │   └──────────┬───────────┘    │  │
│  │              │                │  │
│  │   ┌──────────▼───────────┐    │  │
│  │   │  AI / Brain Module   │    │  │
│  │   └─────────────────────┘    │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
         │          │          │
    ┌────▼───┐ ┌────▼───┐ ┌───▼────┐
    │  AWS   │ │ GitHub │ │ K8s    │ ...
    │CloudAPI│ │  API   │ │  API   │
    └────────┘ └────────┘ └────────┘
```

---

## Feature Spec Index

### ✅ Completed → `tasks/desktop/completed/`

| # | Feature | Spec File | Priority |
|---|---|---|---|
| 01 | **Backend API Bridge** | [`01_BACKEND_API_BRIDGE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/completed/01_BACKEND_API_BRIDGE.md) | P0 |
| 02 | **Connector Registry** | [`02_CONNECTOR_REGISTRY.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/completed/02_CONNECTOR_REGISTRY.md) | P0 |
| 03 | **Design System & Theme** | [`03_DESIGN_SYSTEM.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/completed/03_DESIGN_SYSTEM.md) | P0 |
| 04 | **Onboarding Wizard** | [`04_ONBOARDING_WIZARD.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/completed/04_ONBOARDING_WIZARD.md) | P0 |
| 06 | **Sidebar & Navigation** | [`06_SIDEBAR_NAVIGATION.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/completed/06_SIDEBAR_NAVIGATION.md) | P0 |
| 07 | **Project System** | [`07_PROJECT_SYSTEM.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/completed/07_PROJECT_SYSTEM.md) | P0 |

### 🟡 In Progress → `tasks/desktop/`

| # | Feature | Spec File | Priority | Status |
|---|---|---|---|---|
| 05 | **Service Connection Flow** | [`05_SERVICE_CONNECTIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/05_SERVICE_CONNECTIONS.md) | P0 | Backend done, standalone form missing |
| 08 | **Dynamic Metric Widgets** | [`08_METRIC_WIDGETS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/08_METRIC_WIDGETS.md) | P0 | 5 widgets exist, NOT template-driven, synthetic data |
| 09 | **Watcher Status** | [`09_WATCHER_STATUS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/09_WATCHER_STATUS.md) | P0 | Hooks + panel exist, integration gaps |
| 10 | **Per-Service AI Chatbox** | [`10_AI_CHATBOX.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/10_AI_CHATBOX.md) | P0 | Chat works, execute is fake, greeting hardcoded |
| 11 | **Dashboard Overview** | [`11_DASHBOARD_OVERVIEW.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/11_DASHBOARD_OVERVIEW.md) | P1 | Basic view, missing "mission control" layout |
| 12 | **Integrations Management** | [`12_INTEGRATIONS_PAGE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/12_INTEGRATIONS_PAGE.md) | P1 | Mostly done, inline connect missing |
| 13 | **Activity & Event Log** | [`13_ACTIVITY_LOG.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/13_ACTIVITY_LOG.md) | P1 | Basic list, hardcoded filters |
| 14 | **Settings & Configuration** | [`14_SETTINGS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/14_SETTINGS.md) | P2 | UI exists, save is fake |
| 16 | **AI Widget Generation** | [`16_AI_WIDGET_GENERATION.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/16_AI_WIDGET_GENERATION.md) | P1 | Button exists, generated config not rendered |

### ❌ Not Started → `tasks/desktop/`

| # | Feature | Spec File | Priority | Status |
|---|---|---|---|---|
| 15 | **Notification System** | [`15_NOTIFICATIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/15_NOTIFICATIONS.md) | P2 | Wrong component exists (channels page, not toasts) |

---

## Critical Hardcoding Violations Found & Resolved (2026-09-11 Audit)

| Component | File | Line(s) | Violation | Status |
|---|---|---|---|---|
| ServiceWidget | `ServiceWidget.tsx` | 195-199 | Synthetic chart data when no real data available | ✅ RESOLVED (Real timeSeriesData only; empty state rendered) |
| ServiceWidget | `ServiceWidget.tsx` | 232-236 | Fabricated health check status grid items | ✅ RESOLVED (Derived dynamically from provider status API) |
| MetricCard | `ServiceWidget.tsx` | 213 | `change={2.4}` hardcoded trend value | ✅ RESOLVED (Calculated dynamically from real datapoints) |
| Chatbot | `Chatbot.tsx` | 86-99 | Execute action is fake (no API call) | ✅ RESOLVED (Calls `POST /api/chat/execute` with audit logging) |
| Chatbot | `Chatbot.tsx` | 29 | Static greeting text instead of real metrics | ✅ RESOLVED (Lear Copilot with real-time telemetry badge & context) |
| Projects | `Projects.tsx` | 71-76 | Hardcoded `i-0abc123` resource IDs | ✅ RESOLVED (Zero hardcoded IDs; clean empty states) |
| Sidebar | `Sidebar.tsx` | 89 | Hardcoded `['Production', 'Staging']` | ✅ RESOLVED (Derived dynamically from `activeProject?.environments`) |
| ActivityLog | `ActivityLog.tsx` | 29 | Hardcoded `['all', 'aws', 'github', 'datadog']` | ✅ RESOLVED (Derived dynamically from active connectors & events) |
| Settings | `Settings.tsx` | 9-11 | Save button is fake (no persistence) | ✅ RESOLVED (Persisted to `GET`/`POST /api/settings`, prash.yaml & .env) |
| Settings | `Settings.tsx` | 52-56 | Hardcoded model options | ✅ RESOLVED (Saved and loaded from server config) |
| Integrations | `Integrations.tsx` | 35 | Hardcoded "All 13" text | ✅ RESOLVED (Uses `connectors.length` dynamically) |

---

## Anti-Hardcoding Mandate

> **CRITICAL RULE:** Every piece of code built for the desktop app MUST be verified against hardcoding. No mock data, no placeholder values, no simulated responses in production code paths.

Every spec includes an **Anti-Hardcoding Test Suite** that specifically checks:

1. **Data Source Tests** — Every number, string, status shown in the UI traces to a real API call
2. **Connector Agnosticism Tests** — Widget code works for ANY connector, not just the one tested with
3. **Configuration Tests** — No API URLs, keys, regions, or resource IDs baked into source
4. **Fallback Transparency Tests** — If a fallback/default is used, the UI clearly says so (not silently faking data)
5. **Dynamic Rendering Tests** — UI adapts to the actual data shape, not a hardcoded layout

---

## Execution Order

```
Phase 1 — Foundation ✅ COMPLETE
  01_BACKEND_API_BRIDGE → 02_CONNECTOR_REGISTRY → 03_DESIGN_SYSTEM

Phase 2 — Core Experience (IN PROGRESS)
  04_ONBOARDING_WIZARD ✅ → 05_SERVICE_CONNECTIONS 🟡 → 06_SIDEBAR_NAVIGATION ✅

Phase 3 — The Demo (IN PROGRESS)
  07_PROJECT_SYSTEM ✅ → 08_METRIC_WIDGETS 🟡 → 09_WATCHER_STATUS 🟡 → 10_AI_CHATBOX 🟡

Phase 4 — Polish (IN PROGRESS)
  11_DASHBOARD_OVERVIEW 🟡 → 12_INTEGRATIONS_PAGE 🟡 → 13_ACTIVITY_LOG 🟡 → 14_SETTINGS 🟡 → 15_NOTIFICATIONS 🟡 → 16_AI_WIDGET_GENERATION 🟡
```

---

## Missing Files (per spec)

| File | Required By |
|---|---|
| `desktop/src/components/ConnectorForm.tsx` | Feature 05 |
| `desktop/src/hooks/useConnectorStatus.ts` | Feature 05 |
| `desktop/src/components/widgets/BarChart.tsx` | Feature 08 |
| `desktop/src/components/ChatMessage.tsx` | Feature 10 |
| `desktop/src/components/NotificationToast.tsx` | Feature 15 |
| `desktop/src/hooks/useNotifications.ts` | Feature 15 |
| `desktop/src/components/WidgetConfigurator.tsx` | Feature 16 |
| `prash/widget_generator.py` | Feature 16 |

---

## Cross-Cutting Concerns

- **Branding:** "Lear" everywhere, not "Prash" — update all user-facing text
- **Error handling:** Every API call has loading, error, and empty states — never a blank screen
- **Responsiveness:** Minimum window size 1024×600 for Tauri, fluid layout within
- **Accessibility:** Keyboard navigation, focus indicators, ARIA labels on interactive elements
- **Performance:** Metric polling intervals configurable, no memory leaks from abandoned intervals
- **Offline resilience:** App shows last-known-good data with "stale" indicator when backend is unreachable
