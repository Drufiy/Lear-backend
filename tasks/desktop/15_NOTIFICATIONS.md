# Feature 15 — Notification System

**Priority:** P2 — in-app alerts and toasts  
**Owner:** TBD  
**Depends on:** `09_WATCHER_STATUS.md`  
**Target files:**  
- [`desktop/src/components/Notifications.tsx`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/desktop/src/components/Notifications.tsx) (rewrite)  
- `desktop/src/components/NotificationToast.tsx` (new)  
- `desktop/src/hooks/useNotifications.ts` (new)  
**Test file:** `desktop/src/__tests__/Notifications.test.tsx` (new)

---

## Product Spec

The Notification System handles all in-app alerts — toast notifications for real-time events, a notification center for history, and badge counts in the sidebar.

### Notification Types

| Type | Trigger | Toast | Persist |
|---|---|---|---|
| `watch_critical` | Service went down / crash-loop | Yes (auto-dismiss 10s) | Yes |
| `watch_warning` | Metric threshold breach | Yes (auto-dismiss 5s) | Yes |
| `watch_recovery` | Service recovered | Yes (auto-dismiss 5s) | Yes |
| `action_complete` | An action finished executing | Yes (auto-dismiss 5s) | Yes |
| `action_approval` | An action needs approval | Yes (stays until dismissed) | Yes |
| `connection_lost` | Connector health check failed | Yes (stays until resolved) | Yes |
| `info` | General info (e.g., watch started) | No | Yes |

### Toast Notification UI

```
┌────────────────────────────────────────┐
│  ⚠️  CPU Spike on AWS EC2             │
│  Instance i-0abc123: 94.2% CPU         │
│  2 seconds ago                   [✕]   │
└────────────────────────────────────────┘
```

Toasts appear in the top-right corner, stack vertically, and auto-dismiss based on type.

### Notification Center

```
┌────────────────────────────────────────────┐
│  Notifications                    [Clear]  │
│                                            │
│  NEW                                       │
│  ● ⚠️ CPU Spike on i-0abc123    2m ago     │
│  ● ✅ K8s pod api-7f9d recovered  5m ago    │
│                                            │
│  EARLIER                                   │
│  ○ Watch started on i-0abc123     1h ago   │
│  ○ GitHub CI passed               2h ago   │
└────────────────────────────────────────────┘
```

### Notification Badge

Sidebar "Notifications" nav item shows an unread count badge:
```
  🔔 Notifications  ● 3
```

---

## Detailed Task List

### Phase A — Backend

- [ ] **A1. Create `GET /api/notifications`** — return notification history (from watch events + action results + audit log)
- [ ] **A2. Notification persistence** — store in a local JSON file (lightweight, no database)
- [ ] **A3. Mark as read** — `POST /api/notifications/{id}/read`
- [ ] **A4. Clear all** — `DELETE /api/notifications`

### Phase B — Frontend

- [ ] **B1. Create `useNotifications` hook** — listens to WebSocket events and creates notifications
- [ ] **B2. Create `NotificationToast.tsx`** — slide-in toast component with auto-dismiss
- [ ] **B3. Toast stacking** — multiple toasts stack vertically with animation
- [ ] **B4. Rewrite `Notifications.tsx`** — notification center with read/unread states
- [ ] **B5. Sidebar badge** — unread count on the Notifications nav item
- [ ] **B6. Click notification → navigate** to the service that generated it

---

## Testing Methodology

### Anti-Hardcoding Test Suite

```
test_NO_HARDCODED_NOTIFICATIONS — Notifications come from real 
    watcher events and API responses, never from demo data.

test_NO_FAKE_UNREAD_COUNT — The unread badge count reflects actual 
    unread notifications from the API.

test_NOTIFICATIONS_FROM_REAL_EVENTS — Each notification traces to a 
    real ConnectorEvent or action result.

test_NO_DEMO_TOASTS — Toasts only fire when real events arrive via 
    WebSocket, never on a timer or at app start.
```

---

## Definition of Done

- [ ] Toast notifications appear for real watcher events
- [ ] Notification center shows history from real events
- [ ] Unread badge count reflects actual unread items
- [ ] Click notification navigates to the relevant service
- [ ] Zero demo/fake notifications
