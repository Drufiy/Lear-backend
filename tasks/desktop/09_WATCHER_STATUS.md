# Feature 09 — Watcher Status & Live Monitoring 🟡 PARTIALLY DONE

**Priority:** P0 — real-time is the differentiator  
**Status:** 🟡 **PARTIAL** — hooks and panel exist, major integration gaps  
**Depends on:** `01_BACKEND_API_BRIDGE.md` ✅, `08_METRIC_WIDGETS.md` 🟡  
**Blocks:** `11_DASHBOARD_OVERVIEW.md`, `13_ACTIVITY_LOG.md`, `15_NOTIFICATIONS.md`

---

## What's Done

### Phase B — Frontend WebSocket Hook ✅
- [x] **B1. `useWebSocket.ts`** — manages WebSocket lifecycle (connect, close)
- [x] **B2. Auto-reconnect** — 3s reconnect on close (line 43)
- [x] **B3. Connection status** — `isConnected` state exposed
- [x] **B4. Message parsing** — parses JSON, handles both `events[]` array and single event (lines 30-34)
- [ ] **B5. Send control messages** — no send capability (pause/resume/stop via WS)

### Phase C — Frontend Watcher Hook ✅ (basic)
- [x] **C1. `useWatcher.ts`** — wraps WebSocket hook with watcher-specific logic
- [x] **C2. Event buffer** — rolling buffer of 50 events (line 15)
- [x] **C3. Status tracking** — tracks `IDLE`/`STARTING`/`ACTIVE`/`ALERTING`/`ERROR` states
- [x] Start/stop watch via API calls (`startWatch`, `stopWatch`)
- [ ] **C4. Notification dispatch** — no toast triggers on critical events
- [ ] **C5. Widget update** — no automatic widget data update from watch events

### Phase D — Watcher UI (PARTIAL)
- [x] **D1. `WatcherPanel.tsx`** — shows state badge, active count, event count, start/stop button
- [ ] **D2. Watch control bar** — no per-service start/pause/stop in widget header
- [ ] **D3. Live event stream** — no scrollable event feed within service widget
- [ ] **D4. Next poll countdown** — not implemented
- [ ] **D5. Status transition animation** — no animated dot color changes
- [ ] **D6. Notification toast** — not implemented

### Phase E — Watch Integration with Widgets (NOT STARTED)
- [ ] **E1-E3** — Widgets don't update from watch events, no event-to-widget mapping

---

## Defects

> [!WARNING]
> **WebSocket reconnect uses fixed 3s delay** — spec calls for exponential backoff (1s, 2s, 4s, max 30s). Current implementation is `setTimeout(connect, 3000)`.

> [!WARNING]
> **`useWatcher` has a stale closure bug** — `watcherState` is referenced in the `useEffect` dependency-free callback (line 20-21) but `watcherState` is not in the deps array, so the condition `watcherState === 'IDLE'` may read a stale value.

> [!NOTE]
> The watcher panel shows "LIVE MONITORING ACTIVE" text labels (lines 25-26) which is acceptable since it's UI chrome, not data.

---

## Phase A — Backend Watch API (Status Unknown)
- [ ] **A1-A8** — Backend watch endpoints exist in `prash/server.py` per CHANGELOG. Need verification of: persistence to `prash.yaml`, per-handle polling frequency, error recovery, event normalization.
