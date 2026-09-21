# Notification Channels — `notifications.py`

**Owner:** Aryan (Slack/Discord), Anant (Email/WhatsApp)  
**Status:** Built  
**Priority:** Tier 2  

---

## Current Channels

| Channel | Class | Auth | Status |
|---|---|---|---|
| Desktop | `plyer` | N/A | ✅ Working (macOS verified, Windows not live-verified) |
| Slack | `SlackNotifier` | `SLACK_WEBHOOK_URL` | ✅ Built, live-verified |
| Discord | `DiscordNotifier` | `DISCORD_WEBHOOK_URL` | ✅ Built, live-verified |
| Email | `EmailNotifier` | SMTP config | ✅ Built |
| WhatsApp | `WhatsAppNotifier` | Twilio API | ✅ Built |
| PagerDuty | Via `pagerduty-page` action | REST API | ✅ Built |

**Design decision:** Notifiers are NOT `Connector` subclasses. They're write-only sinks (`Notifier` base with `configured() -> send()`). This is a deliberate shape divergence — see §9, 2026-08-18.

---

## Tasks

### T1. Verify Windows desktop notification path
- [ ] `plyer` Windows toast notification — never live-verified, only mocked
- [ ] Test on actual Windows machine (not just CI)
- [ ] Fallback if `plyer` fails on Windows

### T2. Notification reliability
- [ ] Failed webhook send logs and returns `False` (never raises)
- [ ] Watch loop never dies because a notification channel is temporarily down
- [ ] `prash watch` prints which channels are configured on startup
- [ ] `prash notify` reports per-channel `sent/failed` and exits non-zero on any failure

### T3. Notification content formatting
- [ ] Slack: rich formatting with blocks (severity badge, target, summary)
- [ ] Discord: embed with color-coded severity
- [ ] Email: basic HTML formatting
- [ ] WhatsApp: plain text (Twilio limitations)

### T4. Notification deduplication
- [ ] Same problem shouldn't fire notifications every poll cycle
- [ ] "New problem" notification once, then silence until resolved
- [ ] "Resolved" notification when problem clears

### T5. Desktop notification persistence (`.prash/notifications.json`)
- [ ] Persistent local JSON storage bounded to 100 entries
- [ ] Restore historical notifications on server startup
- [ ] `GET /api/notifications` returns live `unread_count`
- [ ] `POST /api/notifications/{id}/read` marks as read
- [ ] `DELETE /api/notifications` clears all

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_slack_send` | `tests/test_notifications.py` | Webhook POST works |
| `test_discord_send` | `tests/test_notifications.py` | Webhook POST works |
| `test_notification_failure_safe` | `tests/test_notifications.py` | Failed send doesn't crash |
| `test_deduplication` | `tests/test_notifications.py` | Same problem not repeated |
| `test_notification_persistence` | `tests/test_desktop_api.py` | JSON storage works |

---

## Acceptance Criteria

- [ ] All 5 channels working and tested
- [ ] Windows desktop notification verified live
- [ ] Notification failures don't crash the watcher
- [ ] Deduplication prevents spam
