# Watcher Architecture — Overview

**Owner:** Aradhya  
**Status:** K8s watcher working, multi-provider refactor needed  
**Priority:** Tier 1  

---

## Architecture

```
prash watch (entry point)
      │
      ▼
┌──────────────────┐
│  Poll Loop        │  Runs continuously, configurable interval (5s-60s)
│  (watcher.py)     │  Per-connector WatchHandle
│                   │  Failure degradation: healthy → degraded → error
└────────┬─────────┘
         │ detects problem
         ▼
┌──────────────────┐
│  Notify           │  Desktop: plyer (Windows/macOS/Linux)
│                   │  Team: Slack, Discord, Email, WhatsApp
│                   │  cp1252 console safety (Windows)
└────────┬─────────┘
         │ user investigates
         ▼
┌──────────────────┐
│  Diagnose + Fix   │  prash fix (the full pipeline)
└──────────────────┘
```

### Current State
- K8s watch loop: detects `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, stuck Pending
- AWS watch loop: `run_aws_watch_loop` (separate, not unified)
- Terraform watch: `prash watch --provider terraform`
- Desktop: WebSocket `/ws/events` broadcasting
- YAML persistence: active watches survive server restart

---

## Submodule Task Files

1. [`01_WATCHER_CORE.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/watcher/01_WATCHER_CORE.md) — Core poll loop and multi-provider refactor
2. [`02_NOTIFICATIONS.md`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/tasks/watcher/02_NOTIFICATIONS.md) — Notification channels
