# Feature 11 — Dashboard Overview

**Priority:** P1 — top-level summary view  
**Owner:** TBD  
**Depends on:** `07_PROJECT_SYSTEM.md`, `08_METRIC_WIDGETS.md`, `09_WATCHER_STATUS.md`  
**Target file:** [`desktop/src/components/Dashboard.tsx`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/src/components/Dashboard.tsx) (rewrite)  
**Test file:** `desktop/src/__tests__/Dashboard.test.tsx` (new)

---

## Product Spec

The Dashboard is the "mission control" view — a single screen showing the health of your entire infrastructure across all projects and services. Think Vercel's overview page meets a NOC (Network Operations Center) display.

### Layout

```
┌────────────────────────────────────────────────────────────┐
│  Overview                                                  │
│  Monitoring 7 services across 2 projects                   │
│                                                            │
│  ┌── System Health ───────────────────────────────────┐    │
│  │  ● 5 Healthy  ◉ 1 Warning  ○ 1 Inactive           │    │
│  │  ████████████████████░░░ 86% healthy               │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
│  ┌── Active Watches ──────────────────────────────────┐    │
│  │  ☁ AWS EC2 · i-0abc123      ● 23.4% CPU   2s ago  │    │
│  │  ⎈ K8s · api-deployment     ● 3/3 pods    5s ago  │    │
│  │  🔀 GitHub · myorg/myrepo   ● Passing      1m ago │    │
│  └────────────────────────────────────────────────────┘    │
│                                                            │
│  ┌── Recent Activity ────────────────────────────────┐     │
│  │  ○ 2m   AWS   CPU returned to normal on i-0abc123 │     │
│  │  ● 15m  K8s   Pod api-7f9d restarted (OOM)        │     │
│  │  ○ 1h   GitHub CI passed on myorg/myrepo           │     │
│  │  ● 2h   AWS   CloudWatch alarm triggered           │     │
│  └────────────────────────────────────────────────────┘     │
│                                                            │
│  ┌── Quick Actions ──────────────────────────────────┐     │
│  │  [💬 Open Lear AI]  [👁 View All Activity]          │     │
│  │  [+ Watch a Service]  [+ Create Project]            │     │
│  └────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────┘
```

### Sections

#### 1. System Health Bar
- Aggregate health across ALL configured connectors
- Counts: healthy / warning / error / inactive services
- Percentage bar with color segments (green/yellow/red/gray)
- All counts come from REAL `poll_state()` calls, never hardcoded

#### 2. Active Watches
- List of currently watched resources
- Each shows: connector icon, resource name, key metric, last event time
- Click to jump to that service's widget
- Empty state: "No active watches. Start watching a service to see live data here."

#### 3. Recent Activity
- Cross-service event timeline (last 24 hours)
- Events from ALL connectors, sorted by time
- Each event: timestamp, connector icon, summary text
- Click to jump to that service

#### 4. Quick Actions
- Contextual shortcuts based on current state
- "Open Lear AI" — opens global chat
- "View All Activity" — navigates to activity log view
- "Watch a Service" — opens watch setup
- "Create Project" — navigates to project creation

---

## Detailed Task List

### Phase A — Dashboard Data

- [ ] **A1. Create `GET /api/dashboard/summary`** — aggregate health across all connectors:
  - Iterate all configured connectors
  - Call `authenticate()` + `poll_state()` on each
  - Return: `{total, healthy, warning, error, inactive}`
- [ ] **A2. Create `GET /api/dashboard/activity`** — aggregate recent events from all active watches + `get_stats()`
- [ ] **A3. Implement caching** — dashboard data cached for 10 seconds (avoid hitting all connectors on every render)

### Phase B — Dashboard UI

- [ ] **B1. Rewrite Dashboard.tsx** — remove hardcoded service cards and AWS widget
- [ ] **B2. System Health bar** — animated percentage bar, color segments, counts from API
- [ ] **B3. Active Watches section** — render from `/api/watch/active`
- [ ] **B4. Recent Activity feed** — render from `/api/dashboard/activity`
- [ ] **B5. Quick Actions** — contextual buttons
- [ ] **B6. Loading skeleton** — shimmer cards while data loads
- [ ] **B7. Empty state** — when no services connected, show onboarding CTA
- [ ] **B8. Subtitle** — "Monitoring N services across M projects" with real counts

### Phase C — Interactivity

- [ ] **C1. Click watch → navigate to widget**
- [ ] **C2. Click activity → navigate to service**
- [ ] **C3. Auto-refresh** — dashboard refreshes every 30 seconds
- [ ] **C4. Real-time updates** — WebSocket events update watches section without full refresh

---

## Testing Methodology

### Unit Tests

```
test_dashboard_fetches_summary_from_api
test_dashboard_renders_health_counts_from_api
test_dashboard_health_bar_width_matches_percentage
test_dashboard_watches_section_from_api
test_dashboard_activity_from_api
test_dashboard_loading_state
test_dashboard_empty_state_no_services
test_dashboard_subtitle_shows_real_counts
```

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_HEALTH_COUNTS — The health bar counts (healthy=5, 
    warning=1) come from the API, not from the component. Mock the API 
    to return {healthy: 2, warning: 3} and verify the UI shows those 
    exact numbers.

test_NO_HARDCODED_SERVICE_COUNT — "Monitoring N services" uses the 
    real count from the API response.

test_NO_HARDCODED_ACTIVITY — Activity feed shows events from the API, 
    not demo events. With zero events, feed shows "No recent activity."

test_NO_HARDCODED_WATCH_LIST — Active watches section renders from the 
    API's active watch list, not from a preset list.

test_NO_DEMO_DATA — There is no static mock data rendered when the 
    API is unavailable. The dashboard shows an error state instead.
```

---

## Definition of Done

- [ ] System Health shows REAL aggregate status from all connectors
- [ ] Active Watches show REAL watched resources with live metrics
- [ ] Activity feed shows REAL events from connectors, not mock data
- [ ] All counts and metrics come from the API, never hardcoded
- [ ] Loading, error, and empty states handled
- [ ] Anti-hardcoding tests pass
