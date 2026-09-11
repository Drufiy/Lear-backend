# Feature 13 — Activity & Event Log 🟡 PARTIALLY DONE

**Priority:** P1 — audit trail UI  
**Status:** 🟡 **PARTIAL** — basic event list exists with hardcoded filter buttons  
**Depends on:** `09_WATCHER_STATUS.md` 🟡, `01_BACKEND_API_BRIDGE.md` ✅  
**Blocks:** Nothing

---

## What's Done

- [x] **B1. `ActivityLog.tsx`** — renders event list
- [x] **B3. Event rendering** — icon, connector badge, event_type, summary, timestamp
- [x] Events sourced from `useWatcher()` hook (line 6) — real WebSocket events
- [x] Empty state — "No activity events recorded yet" (lines 47-51)
- [x] Basic filter by connector name (lines 9-12)
- [x] Timestamp formatting (line 79)

## What's Remaining

### 🔴 Critical Fix
- [ ] **FIX: Hardcoded filter buttons** — Line 29: `{['all', 'aws', 'github', 'datadog'].map(...)}` — filters are hardcoded connector names instead of derived from `events` or from `/api/connectors`. If the user has Kubernetes and GitLab connected, they can't filter by those.

### Phase A — Backend (NOT STARTED)
- [ ] **A1. `GET /api/activity`** — backend activity endpoint (current implementation uses client-side watcher events only, missing audit log entries, AI diagnosis records, action executions)
- [ ] **A2. Pagination** — offset + limit
- [ ] **A3. Filtering** — query params for type, time range, connector, severity
- [ ] **A4. Search** — text search across event summaries

### Phase B — Frontend (remaining)
- [ ] **B2. Event grouping** — group by day (TODAY, YESTERDAY, date)
- [ ] **B4. Filter bar** — dynamic dropdowns for type, time range, service (from API), severity
- [ ] **B5. Search input** — debounced search
- [ ] **B6. Infinite scroll** — load more events on scroll
- [ ] **B7. Click event** — navigate to the service that generated it

---

## Defects

> [!CAUTION]
> **HARDCODING VIOLATION**: Filter buttons `['all', 'aws', 'github', 'datadog']` are a hardcoded array. Must derive from unique `ev.connector` values in the event stream, or from connected connectors via `/api/connectors`.

> [!WARNING]
> **Events are client-side only**: `ActivityLog` uses `useWatcher()` which provides only WebSocket events received during the current session. Historical events, AI diagnoses, and action executions are not included. The spec requires a backend `GET /api/activity` endpoint that aggregates from watch handles, audit log, connector stats, and AI diagnosis history.
