# Feature 08 — Dynamic Metric Widgets 🟡 PARTIALLY DONE

**Priority:** P0 — the killer demo feature  
**Status:** 🟡 **PARTIAL** — all 5 widget components exist, orchestrator works but is NOT template-driven  
**Depends on:** `01_BACKEND_API_BRIDGE.md` ✅, `02_CONNECTOR_REGISTRY.md` ✅, `07_PROJECT_SYSTEM.md` 🟡  
**Blocks:** `09_WATCHER_STATUS.md`, `11_DASHBOARD_OVERVIEW.md`, `16_AI_WIDGET_GENERATION.md`

---

## What's Done

### Phase A — Widget Components ✅ (5 of 6)
- [x] **A1. `MetricGauge.tsx`** — SVG radial gauge with animated arc, value label, color interpolation (3KB)
- [x] **A2. `MetricLineChart.tsx`** — SVG time-series with bezier smoothing, gradient fill, hover tooltips, auto-scaling Y (5KB)
- [x] **A3. `MetricCard.tsx`** — large number display with trend arrow, sparkline (2.5KB)
- [x] **A4. `EventTimeline.tsx`** — vertical timeline with severity dots, timestamps, summaries (2.8KB)
- [x] **A5. `StatusGrid.tsx`** — grid of status items with status dots (2.7KB)
- [ ] **A6. `BarChart.tsx`** — **MISSING** — file does not exist

### Phase B — Widget Orchestration (PARTIAL)
- [x] **B1. `ServiceWidget.tsx`** — exists, fetches metrics from API, has loading state
- [x] **B3. Loading state** — spinner while fetching
- [ ] **B2. Widget type mapping from templates** — **NOT IMPLEMENTED** — see defects below
- [ ] **B4. Error state** — no explicit error state, just silently fails
- [ ] **B5. Empty state** — no "No data available" message

### Phase C — Data Integration (PARTIAL)
- [x] **C1. Metric data fetching** — `fetchTelemetry()` calls `/api/connectors/{id}/metrics`
- [x] **C6. Auto-refresh** — 30s interval via `setInterval` (line 69)
- [ ] **C2-C5. Data adapters** — none exist; raw metric data piped directly
- [ ] **C7. Data caching** — no history accumulation across refreshes

### Phase D — Interaction (NOT STARTED)
- [ ] **D1-D5** — No expand view, no time range selector, no tooltip interaction, no "Open Chat" from widget

---

## 🔴 Critical Defects

### 1. NOT TEMPLATE-DRIVEN (Core Spec Violation)
`ServiceWidget.tsx` renders a **hardcoded layout** (lines 182-239):
```
Gauge → LineChart → MetricCards → EventTimeline → StatusGrid
```
It does NOT read `widget_templates` from the connector registry. Every connector gets the **same** widget layout regardless of its templates. This violates the core architecture of Feature 08.

**Fix required**: Read widget templates from `/api/connectors` response, map `template.type` → widget component, render dynamically.

### 2. SYNTHETIC CHART DATA (Anti-Hardcoding Violation)
Lines 195-199 generate **fake data points** when no real time-series data exists:
```tsx
data={timeSeriesData.length > 0 ? timeSeriesData : [
  { timestamp: new Date(Date.now() - 600000).toISOString(), value: cpuVal * 0.8 },
  { timestamp: new Date(Date.now() - 300000).toISOString(), value: cpuVal * 1.1 },
  { timestamp: new Date().toISOString(), value: cpuVal },
]}
```
**Must show "No data" instead.**

### 3. HARDCODED STATUS GRID ITEMS
Lines 232-236 fabricate health check items:
```tsx
items={[
  { id: 'sts_auth', name: 'Provider Authentication', status: ... },
  { id: 'metrics_poll', name: 'Telemetry Streaming', status: ... },
  { id: 'watcher_sync', name: 'Watcher Pulse', status: 'healthy' },
]}
```
These are synthetic, not from real connector data.

### 4. HARDCODED TREND VALUE
`MetricCard` on line 213 has `change={2.4}` — a hardcoded percentage that never changes.

---

## Files Required
- `desktop/src/components/widgets/BarChart.tsx` — **NEW**
