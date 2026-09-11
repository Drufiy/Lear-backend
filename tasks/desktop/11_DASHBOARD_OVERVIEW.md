# Feature 11 — Dashboard Overview 🟡 PARTIALLY DONE

**Priority:** P1 — top-level summary view  
**Status:** 🟡 **PARTIAL** — basic dashboard exists, spec's "mission control" layout missing  
**Depends on:** `07_PROJECT_SYSTEM.md` 🟡, `08_METRIC_WIDGETS.md` 🟡, `09_WATCHER_STATUS.md` 🟡  
**Blocks:** Nothing

---

## What's Done

- [x] `Dashboard.tsx` renders with project name + environment badge
- [x] Shows `WatcherPanel` with live state/count
- [x] Renders `ServiceWidget` per service in active environment
- [x] "Open Lear Copilot" button — opens global chat
- [x] Empty state — "No Services Configured" with CTA to connect
- [x] Service count in subtitle — "Live telemetry... for N services"

## What's Remaining

### Phase A — Dashboard Data (NOT STARTED)
- [ ] **A1. `GET /api/dashboard/summary`** — aggregate health across all connectors (healthy/warning/error/inactive counts)
- [ ] **A2. `GET /api/dashboard/activity`** — recent events from all watches
- [ ] **A3. Caching** — 10s cache to avoid hitting all connectors on every render

### Phase B — Dashboard UI (MOSTLY MISSING)
- [ ] **B2. System Health bar** — animated percentage bar with color segments
- [ ] **B3. Active Watches section** — render from `/api/watch/active` (current view shows services, not watches)
- [ ] **B4. Recent Activity feed** — cross-service event timeline
- [ ] **B5. Quick Actions** — contextual buttons (Open AI, View Activity, Watch Service, Create Project)
- [ ] **B6. Loading skeleton** — shimmer cards while data loads
- [ ] **B8. Subtitle** — "Monitoring N services across M projects" with real counts

### Phase C — Interactivity (NOT STARTED)
- [ ] **C1-C4** — Click watch → navigate, click activity → navigate, auto-refresh, WebSocket real-time updates

---

## Defects

> [!WARNING]
> The current dashboard is a **service widget list**, not the "mission control" view described in the spec. The spec requires a System Health bar, Active Watches section, Recent Activity feed, and Quick Actions — all of which are missing. The current view is closer to a "Project Detail" view than a true Dashboard Overview.

> [!NOTE]
> The dashboard currently uses project services directly rather than calling a dashboard-specific API endpoint for aggregate health data.
