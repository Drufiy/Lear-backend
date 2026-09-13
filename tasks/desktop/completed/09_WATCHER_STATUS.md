# Feature 09 — Watcher Status & Live Monitoring ✅ COMPLETED

**Priority:** P0 — real-time is the differentiator  
**Status:** ✅ **COMPLETED** (100%)  
**Depends on:** `01_BACKEND_API_BRIDGE.md` ✅, `08_METRIC_WIDGETS.md` ✅  
**Blocks:** `11_DASHBOARD_OVERVIEW.md`, `13_ACTIVITY_LOG.md`, `15_NOTIFICATIONS.md`

---

## Deliverables Completed

### Phase A — Backend Watch API ✅
- [x] **A1. Watch Start & Stop** — `POST /api/connectors/{id}/watch` and `DELETE /api/connectors/{id}/watch`
- [x] **A2. Watch Interval Cadence** — Per-handle polling frequency (`5s`, `15s`, `30s`, `60s`) honored in background `_poll_watches_loop()`
- [x] **A3. Active Watches Listing** — `GET /api/watch/active` returning handle status (`healthy`, `degraded`, `error`, `paused`), intervals, and error metadata
- [x] **A4. YAML Persistence** — Active watches persisted to and synchronized with `prash.yaml` and reconciled upon server restart (`lifespan`)
- [x] **A5. Error Recovery** — Consecutive failure tracking with graceful degradation (`degraded` -> `error`), automatic recovery to `healthy`, and status transition event broadcasting
- [x] **A6. WebSocket Control Messages** — Full duplex WS control in `/ws/events`: `ping`/`pong`, `pause`, `resume`, `stop`
- [x] **A7. Watch Pause/Resume REST Endpoints** — `POST /api/connectors/{id}/watch/pause` and `/resume`
- [x] **A8. Iterator Adapter** — Transparent adapter for generator/iterator-based watch handles (e.g. Kubernetes)

### Phase B — Frontend WebSocket Hook (`useWebSocket.ts`) ✅
- [x] **B1. Lifecycle Management** — Clean connect, disconnect, and ref tracking
- [x] **B2. Exponential Backoff** — Reconnection backoff scaling at 1s, 2s, 4s, 8s, 16s up to 30s max, with instant reset on handshake
- [x] **B3. Connection Status** — Explicit connection state (`connecting`, `connected`, `reconnecting`, `disconnected`)
- [x] **B4. Message Parsing** — Robust parsing of single events, `events[]` arrays, and control acknowledgments
- [x] **B5. Send Control Messages** — `sendMessage()` API for bidirectional control over WebSocket

### Phase C — Frontend Watcher Hook (`useWatcher.ts`) ✅
- [x] **C1. Watcher State Tracking** — Full tracking across `IDLE`, `STARTING`, `ACTIVE`, `DEGRADED`, `ALERTING`, `ERROR`
- [x] **C2. Event Buffer** — Rolling buffer of 50 normalized events
- [x] **C3. Stale Closure Fix** — Uses functional state setter `setWatcherState(prev => ...)` to eliminate stale closure bugs
- [x] **C4. Active Watch Sync** — Synchronizes with backend `/api/watch/active` on mount
- [x] **C5. Handle Controls** — `startWatch`, `stopWatch`, `pauseWatch`, `resumeWatch`, and `pausedWatches` state

### Phase D — Watcher UI (`WatcherPanel.tsx`) ✅
- [x] **D1. Live Status Badge** — Authentic state badges with animated indicators
- [x] **D2. Next Poll Countdown** — Real-time countdown timer (`Next poll in 4s...`) synchronized with active interval
- [x] **D3. Dynamic Radar Pulse Animations** — Radar ripple wave effects around the radio icon during live monitoring
- [x] **D4. Active Handles Drawer** — Collapsible handle manager listing all active targets, connectors, intervals, and individual pause/resume/stop controls
- [x] **D5. Interval Selector** — Configurable polling interval (`5s`, `15s`, `30s`, `60s`)

### Phase E — Watch Integration with Widgets (`ServiceWidget.tsx`) ✅
- [x] **E1. Per-Service Watch Control Bar** — Inline watch controls in widget header with live status pill, pause/resume, and stop toggle
- [x] **E2. Real-Time Telemetry Updates** — WebSocket events matching the service immediately update metric values and rolling history without waiting for the 30s poll
- [x] **E3. Collapsible Live Event Stream** — Expandable real-time event feed drawer in `ServiceWidget` with JSON raw inspector
- [x] **E4. Live Pulse Visual Indication** — Glowing green accent pulse and ring wave on widget borders when live telemetry arrives

---

## 🔴 Critical Defects Resolved

1. **WEBSOCKET FIXED 3S RECONNECT**: Replaced static 3-second delay in `useWebSocket.ts` with genuine exponential backoff: `Math.min(1000 * Math.pow(2, retryCount), 30000)`.
2. **USEWATCHER STALE CLOSURE BUG**: Resolved stale closure condition in `useWatcher.ts` by wrapping `setWatcherState` in a functional updater `prev => ...`.
3. **METRICS EXCEPTION SWALLOWING**: Fixed `get_connector_metrics` in `prash/server.py` where `connector.get_stats()` was catching all exceptions and converting `NotImplementedError` into empty events instead of `unsupported: True`, and swallowing `RuntimeError` instead of returning 500 `CONNECTOR_API_ERROR`.
4. **WATCH PERSISTENCE MISSING**: Added full YAML persistence and recovery for active watches in `prash.yaml`.

---

## Verification
- `python -m pytest tests/test_desktop_api.py -v`: 15 passed (100%)
- `python -m pytest tests/test_watcher.py -v`: 68 passed (100%)
- `python -m pytest tests/test_widget_generation.py -v`: 2 passed (100%)
- `cmd /c npm run build`: 0 TypeScript errors, 2246 modules transformed cleanly in 3.45s
