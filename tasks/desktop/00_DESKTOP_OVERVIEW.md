# Lear Desktop App — Feature Spec Overview

**Goal:** A consumer-centric desktop application that connects live to any backend service, feeds data into Lear's AI for analysis, and watches services in real-time — like Vercel for your entire infrastructure. The primary target is a **business demo** that proves Lear's value to prospective customers.

**Primary demo connector:** AWS EC2 (with architecture supporting all 13 connectors)

**Product name:** Lear (rebranded from "Prash" throughout all UI)

**Tech stack:** Tauri v2 (Rust backend) + React + TypeScript + Tailwind v4 + Framer Motion + FastAPI (Python API bridge)

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

Every feature is a separate document with: product spec, detailed task lists, and testing methodology.

| # | Feature | Spec File | Priority | Status |
|---|---|---|---|---|
| 01 | **Backend API Bridge** | [`01_BACKEND_API_BRIDGE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/01_BACKEND_API_BRIDGE.md) | P0 — everything depends on this | `[ ]` |
| 02 | **Connector Registry & Auto-Discovery** | [`02_CONNECTOR_REGISTRY.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/02_CONNECTOR_REGISTRY.md) | P0 — drives wizard, widgets, chat | `[ ]` |
| 03 | **Design System & Theme** | [`03_DESIGN_SYSTEM.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/03_DESIGN_SYSTEM.md) | P0 — visual foundation | `[ ]` |
| 04 | **Onboarding Wizard** | [`04_ONBOARDING_WIZARD.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/04_ONBOARDING_WIZARD.md) | P0 — first-run experience | `[ ]` |
| 05 | **Service Connection Flow** | [`05_SERVICE_CONNECTIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/05_SERVICE_CONNECTIONS.md) | P0 — credential validation | `[ ]` |
| 06 | **Sidebar & Navigation** | [`06_SIDEBAR_NAVIGATION.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/06_SIDEBAR_NAVIGATION.md) | P0 — app structure | `[ ]` |
| 07 | **Project System** | [`07_PROJECT_SYSTEM.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/07_PROJECT_SYSTEM.md) | P0 — organizational model | `[ ]` |
| 08 | **Dynamic Metric Widgets** | [`08_METRIC_WIDGETS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/08_METRIC_WIDGETS.md) | P0 — the killer demo feature | `[ ]` |
| 09 | **Watcher Status & Live Monitoring** | [`09_WATCHER_STATUS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/09_WATCHER_STATUS.md) | P0 — real-time updates | `[ ]` |
| 10 | **Per-Service AI Chatbox** | [`10_AI_CHATBOX.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/10_AI_CHATBOX.md) | P0 — AI-powered interaction | `[ ]` |
| 11 | **Dashboard Overview** | [`11_DASHBOARD_OVERVIEW.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/11_DASHBOARD_OVERVIEW.md) | P1 — top-level summary view | `[ ]` |
| 12 | **Integrations Management** | [`12_INTEGRATIONS_PAGE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/12_INTEGRATIONS_PAGE.md) | P1 — post-setup management | `[ ]` |
| 13 | **Activity & Event Log** | [`13_ACTIVITY_LOG.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/13_ACTIVITY_LOG.md) | P1 — audit trail UI | `[ ]` |
| 14 | **Settings & Configuration** | [`14_SETTINGS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/14_SETTINGS.md) | P2 — preferences | `[ ]` |
| 15 | **Notification System** | [`15_NOTIFICATIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/15_NOTIFICATIONS.md) | P2 — in-app alerts | `[ ]` |
| 16 | **AI Widget Generation** | [`16_AI_WIDGET_GENERATION.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/desktop/16_AI_WIDGET_GENERATION.md) | P1 — AI creates custom widget configs | `[ ]` |

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
Phase 1 — Foundation (no UI visible yet)
  01_BACKEND_API_BRIDGE → 02_CONNECTOR_REGISTRY → 03_DESIGN_SYSTEM

Phase 2 — Core Experience
  04_ONBOARDING_WIZARD → 05_SERVICE_CONNECTIONS → 06_SIDEBAR_NAVIGATION

Phase 3 — The Demo
  07_PROJECT_SYSTEM → 08_METRIC_WIDGETS → 09_WATCHER_STATUS → 10_AI_CHATBOX

Phase 4 — Polish
  11_DASHBOARD_OVERVIEW → 12_INTEGRATIONS_PAGE → 13_ACTIVITY_LOG → 14_SETTINGS → 15_NOTIFICATIONS → 16_AI_WIDGET_GENERATION
```

---

## Cross-Cutting Concerns

- **Branding:** "Lear" everywhere, not "Prash" — update all user-facing text
- **Error handling:** Every API call has loading, error, and empty states — never a blank screen
- **Responsiveness:** Minimum window size 1024×600 for Tauri, fluid layout within
- **Accessibility:** Keyboard navigation, focus indicators, ARIA labels on interactive elements
- **Performance:** Metric polling intervals configurable, no memory leaks from abandoned intervals
- **Offline resilience:** App shows last-known-good data with "stale" indicator when backend is unreachable
