# Feature 15 — Notification System ❌ NOT STARTED (as spec'd)

**Priority:** P2 — in-app alerts and toasts  
**Status:** ❌ **NOT STARTED** — existing `Notifications.tsx` is a **completely different component**  
**Depends on:** `09_WATCHER_STATUS.md` 🟡  
**Blocks:** Nothing

---

## Current State

> [!CAUTION]
> **`Notifications.tsx` is NOT the notification system described in this spec.** The existing file is a **notification routing/channels page** (Slack, Discord, WhatsApp, Email, PagerDuty channel management). The spec describes an **in-app toast notification + notification center** system. These are completely different features with zero overlap.

The existing `Notifications.tsx`:
- Shows hardcoded notification channels (Slack, Discord, WhatsApp, Email, PagerDuty)
- Has a "Routing Rules" section (empty state)
- Does NOT implement toast notifications, notification center, badge counts, or `useNotifications` hook
- Uses old design tokens (`bg-gray-900/30`, `border-gray-800`) inconsistent with the design system

---

## Full Task List (ALL REMAINING)

### Phase A — Backend
- [ ] **A1. Create `GET /api/notifications`** — notification history from watch events + action results + audit log
- [ ] **A2. Notification persistence** — store in local JSON file
- [ ] **A3. Mark as read** — `POST /api/notifications/{id}/read`
- [ ] **A4. Clear all** — `DELETE /api/notifications`

### Phase B — Frontend
- [ ] **B1. Create `useNotifications` hook** — listens to WebSocket events, creates notifications
- [ ] **B2. Create `NotificationToast.tsx`** — slide-in toast with auto-dismiss (5s/10s based on severity)
- [ ] **B3. Toast stacking** — multiple toasts stack vertically with animation
- [ ] **B4. Rewrite `Notifications.tsx`** — notification center with read/unread states, grouped by NEW/EARLIER
- [ ] **B5. Sidebar badge** — unread count on the Notifications nav item (currently using Bell icon)
- [ ] **B6. Click notification → navigate** to the relevant service

---

## Decision Needed

> [!IMPORTANT]
> The existing `Notifications.tsx` handles notification **routing channels** (Slack, Discord, etc.). This functionality needs to be preserved somewhere — either as a tab within the new Notifications page, or moved to Settings. The in-app notification system (toasts, center, badges) is the priority described in this spec.

---

## Files Required
- `desktop/src/components/NotificationToast.tsx` — **NEW**
- `desktop/src/hooks/useNotifications.ts` — **NEW**
- `desktop/src/components/Notifications.tsx` — **REWRITE** (or rename existing to `NotificationChannels.tsx`)
