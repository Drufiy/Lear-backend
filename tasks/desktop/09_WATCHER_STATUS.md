# Feature 09 — Watcher Status & Live Monitoring

**Priority:** P0 — real-time is the differentiator  
**Owner:** TBD  
**Depends on:** `01_BACKEND_API_BRIDGE.md`, `08_METRIC_WIDGETS.md`  
**Target files:**  
- `desktop/src/components/WatcherPanel.tsx` (new)  
- `desktop/src/hooks/useWatcher.ts` (new)  
- `desktop/src/hooks/useWebSocket.ts` (new)  
**Test file:** `desktop/src/__tests__/Watcher.test.tsx` (new), `tests/test_watcher_api.py` (new)

---

## Product Spec

The Watcher is Lear's always-on monitoring engine. When you tell Lear to "watch" a service, it continuously polls the connector and pushes real-time events to the desktop app. The UI shows live status with animated indicators, event streams, and instant notifications when something changes.

### How Watching Works

```
User clicks "Start Watching" on a service
    │
    ▼
Frontend POST /api/connectors/{id}/watch {target: "i-0abc123"}
    │
    ▼
Backend calls connector.watch("i-0abc123") → returns WatchHandle
    │
    ▼
Backend starts polling WatchHandle.poll() every {interval} seconds
    │
    ├──► No new events → continue polling
    │
    └──► New events detected → push via WebSocket /ws/events
              │
              ▼
         Frontend receives event
              │
              ├──► Update status dot in sidebar
              ├──► Add event to activity feed
              ├──► Update metric widgets
              └──► Show notification toast (if degraded/failed)
```

### Watcher States

```
IDLE       → Not watching anything (default)
STARTING   → Watch requested, waiting for backend confirmation
ACTIVE     → Watching, receiving events
DEGRADED   → Watching, but the service has issues
ALERTING   → Watching, critical issue detected
PAUSED     → Temporarily paused by user
STOPPED    → Stopped by user
ERROR      → Watcher failed (backend error, connector error)
```

### UI Components

#### Watcher Control Bar (in service widget header)
```
┌──────────────────────────────────────┐
│  ☁ AWS EC2 · i-0abc123              │
│  ● Watching · Last event: 2s ago    │
│  [⏸ Pause]  [⏹ Stop]               │
└──────────────────────────────────────┘
```

#### Watcher Panel (sidebar section + expandable)
```
WATCHING (3 active)
  ● AWS EC2: i-0abc123        2s ago
  ◉ K8s: api-deployment       5s ago
  ● GitHub: myorg/myrepo      1m ago
```

#### Event Stream (live feed within service widget)
```
┌─ Live Events ─────────────────────┐
│  🔴 21:03:42  CPU spike: 94.2%    │
│  🟡 21:03:12  Network latency     │
│  🟢 21:02:45  Status check passed │
│  🟢 21:02:15  All metrics normal  │
│                                   │
│  ◉ Watching... next poll in 12s   │
└───────────────────────────────────┘
```

### WebSocket Protocol

```json
// Server → Client (event push)
{
    "type": "watch_event",
    "data": {
        "connector_id": "aws",
        "resource_id": "i-0abc123",
        "event": {
            "timestamp": "2026-09-07T21:03:42Z",
            "connector": "aws",
            "event_type": "cpu_spike",
            "summary": "CPU utilization reached 94.2% (threshold: 80%)",
            "raw": { ... }
        }
    }
}

// Server → Client (status update)
{
    "type": "watch_status",
    "data": {
        "connector_id": "aws",
        "resource_id": "i-0abc123",
        "status": "degraded",
        "last_poll": "2026-09-07T21:03:42Z",
        "next_poll": "2026-09-07T21:04:12Z"
    }
}

// Client → Server (control)
{
    "type": "watch_control",
    "action": "pause" | "resume" | "stop",
    "connector_id": "aws",
    "resource_id": "i-0abc123"
}
```

### Notification Rules

| Event Severity | Action |
|---|---|
| `info` (normal metric) | Update widget, add to feed silently |
| `warning` (threshold breach) | Update widget, toast notification, sidebar dot turns yellow |
| `critical` (service down) | Update widget, toast notification, sidebar dot turns red, sound alert |
| `recovery` (issue resolved) | Update widget, toast notification, sidebar dot turns green |

---

## Detailed Task List

### Phase A — Backend Watch API

- [ ] **A1. Implement `POST /api/connectors/{id}/watch`** — validate connector is configured, call `connector.watch(target)`, store handle with metadata
- [ ] **A2. Implement `DELETE /api/connectors/{id}/watch`** — stop the watch handle, remove from active list
- [ ] **A3. Implement `GET /api/watch/active`** — list all active watches with current status and last event time
- [ ] **A4. Implement WebSocket `/ws/events`** — background asyncio task that polls all active handles and pushes events to connected WS clients
- [ ] **A5. Watch event normalization** — convert raw `ConnectorEvent` to the WebSocket protocol format
- [ ] **A6. Polling frequency management** — use each `WatchHandle.interval` for per-handle poll timing
- [ ] **A7. Error handling** — if a `poll()` call fails, push an error event to the client, don't crash the watch loop
- [ ] **A8. Watch state persistence** — save active watches to `prash.yaml` so they can be re-established on server restart

### Phase B — Frontend WebSocket Hook

- [ ] **B1. Create `useWebSocket` hook** — manages WebSocket connection lifecycle (connect, reconnect, close)
- [ ] **B2. Auto-reconnect** — if WS disconnects, attempt reconnect with exponential backoff (1s, 2s, 4s, max 30s)
- [ ] **B3. Connection status** — expose connection state (connecting, connected, disconnected, error)
- [ ] **B4. Message parsing** — parse incoming JSON messages, dispatch by `type`
- [ ] **B5. Send control messages** — pause/resume/stop via the WS channel

### Phase C — Frontend Watcher Hook

- [ ] **C1. Create `useWatcher` hook** — wraps the WebSocket hook with watcher-specific logic
- [ ] **C2. Event buffer** — maintain a rolling buffer of recent events per watch (max 100)
- [ ] **C3. Status tracking** — track current status per watched resource
- [ ] **C4. Notification dispatch** — when critical events arrive, trigger toast notifications
- [ ] **C5. Widget update** — when metric events arrive, update the corresponding widget data

### Phase D — Watcher UI Components

- [ ] **D1. Create `WatcherPanel.tsx`** — the sidebar section showing active watches
- [ ] **D2. Watch control bar** — start/pause/stop buttons in the service widget header
- [ ] **D3. Live event stream** — scrollable feed within the service widget showing recent events with timestamps
- [ ] **D4. Next poll countdown** — "next poll in Xs" indicator
- [ ] **D5. Status transition animation** — animate status dot color changes (fade transition)
- [ ] **D6. Notification toast** — slide-in toast for warning/critical events

### Phase E — Watch Integration with Widgets

- [ ] **E1. Widget auto-refresh from watch events** — when a watch event contains metric data, update the widget without waiting for the next poll
- [ ] **E2. Event-to-widget mapping** — route events to the correct widget based on `event_type` matching `metric_keys`
- [ ] **E3. History accumulation** — line charts accumulate data points from watch events, building up history over time

---

## Testing Methodology

### Unit Tests

```
# Backend
test_watch_start_creates_handle
test_watch_start_requires_configured_connector
test_watch_start_rejects_duplicate
test_watch_stop_calls_handle_stop
test_watch_active_lists_all_watches
test_watch_poll_returns_real_events
test_watch_poll_handles_connector_error_gracefully
test_ws_pushes_events_to_client
test_ws_reconnects_after_disconnect
test_watch_persists_to_yaml

# Frontend
test_use_websocket_connects
test_use_websocket_reconnects_on_close
test_use_websocket_parses_messages
test_use_watcher_buffers_events
test_use_watcher_updates_status
test_watcher_panel_shows_active_watches
test_watch_control_start
test_watch_control_pause
test_watch_control_stop
test_event_stream_shows_events_chronologically
test_notification_toast_on_critical_event
test_next_poll_countdown_decrements
```

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_WATCH_EVENTS — The event stream displays ONLY events 
    received from the WebSocket, never synthetic/demo events. Start 
    watching with no actual events, verify the stream is empty — not 
    pre-populated with fake data.

test_NO_HARDCODED_POLL_INTERVAL — The polling interval comes from the 
    WatchHandle's `interval` property (set by the connector), not from 
    a hardcoded constant in the frontend.

test_NO_HARDCODED_STATUS — The status dot color is determined by the 
    event data from the backend, not by connector ID or resource name.

test_NO_SIMULATED_EVENTS — When the backend returns no events from 
    poll(), the frontend event stream shows "No events" — never 
    generates fake events to fill the UI.

test_NO_HARDCODED_TIMESTAMPS — All timestamps in the event stream 
    come from the event's `timestamp` field, not from `Date.now()` 
    on the frontend.

test_WATCHER_CONNECTOR_AGNOSTIC — The watcher UI works identically 
    for any connector. Test by starting watches on two different 
    connectors and verifying both get equal treatment.

test_NO_DEMO_MODE — There is no "demo mode" that simulates events 
    for presentation purposes. The app shows real data or nothing.
```

### Integration Tests

```
test_FULL_WATCH_FLOW — Start watch → receive events → verify UI 
    updates → stop watch → verify events stop

test_MULTIPLE_WATCHES — Start 3 watches simultaneously → verify 
    all 3 appear in sidebar → verify events from each are routed 
    correctly

test_WATCH_SURVIVES_RECONNECT — Start watch → disconnect WS → 
    reconnect → verify events resume

test_WATCH_ERROR_RECOVERY — Start watch → connector throws error → 
    verify error shown in UI → connector recovers → verify events resume
```

### Performance Tests

```
test_EVENT_THROUGHPUT — Push 100 events/second via WS → verify UI 
    renders without lag or dropped frames

test_BUFFER_MEMORY — Accumulate 10,000 events → verify memory usage 
    stays bounded (ring buffer evicts old events)

test_MULTIPLE_WS_CLIENTS — Connect 5 WS clients → verify all receive 
    the same events
```

---

## Definition of Done

- [ ] Watch can be started/paused/stopped for any connector via the API
- [ ] WebSocket pushes real events from connector watch handles
- [ ] Frontend displays live event stream with real timestamps and summaries
- [ ] Sidebar shows active watches with real-time status dots
- [ ] Notification toasts appear for warning/critical events
- [ ] Widgets auto-update from watch events
- [ ] Watch state persists across server restarts
- [ ] Zero synthetic/demo events — all data from connectors
- [ ] Anti-hardcoding tests all pass
