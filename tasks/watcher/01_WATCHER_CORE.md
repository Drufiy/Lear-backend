# Watcher Core — `watcher.py` Multi-Provider Refactor

**Owner:** Aradhya  
**Status:** K8s working, refactor needed for multi-provider  
**Priority:** Tier 1  
**Depends on:** `connectors/00_BASE_INTERFACE.md` (WatchHandle, ConnectorEvent)  

---

## Goal

Refactor `watcher.py` from hardcoded K8s/AWS/Terraform poll loops into a generic loop that works with **any** connector implementing `watch()` and `get_stats()`.

---

## Current State

- `run_watch_loop()` — K8s-specific, hardcoded pod status checks
- `run_aws_watch_loop()` — AWS-specific, separate function
- `run_watchhandle_loop()` — generic-ish but not connector-agnostic
- 38K file, significant refactor needed

---

## Tasks

### T1. Unify poll loops into one generic connector-agnostic loop
- [ ] Replace `run_watch_loop()`, `run_aws_watch_loop()` with single `run_connector_watch(handle: WatchHandle)`
- [ ] Loop calls `connector.get_stats(target, since=last_poll)` each cycle
- [ ] Compare new events against last state → detect problems
- [ ] Failure degradation: healthy → degraded (3 failures) → error (5 failures)
- [ ] Self-healing: consecutive successes restore health

### T2. Multi-connector orchestration
- [ ] `prash watch` starts watches for ALL configured connectors simultaneously
- [ ] Each connector gets its own `WatchHandle` with independent interval
- [ ] Concurrent polling (asyncio or threading) — don't serialize across connectors
- [ ] One slow connector doesn't block others

### T3. State change detection
- [ ] Compare `ConnectorEvent` stream against previous state
- [ ] Detect: new problems, resolved problems, escalated problems
- [ ] Deduplicate: same problem shouldn't fire multiple notifications
- [ ] State persistence across watcher restarts (YAML sync)

### T4. Problem → notification → diagnosis pipeline
- [ ] On new problem detected:
  1. Fire desktop notification (`plyer`)
  2. Fire team notifications (Slack/Discord/Email/WhatsApp) if configured
  3. Print "Run `prash fix <target>` to investigate" with exact target
- [ ] Closed problems: optional "resolved" notification

### T5. WebSocket broadcasting for desktop app
- [ ] Every poll cycle emits events to `/ws/events`
- [ ] State changes broadcast immediately
- [ ] Desktop `WatcherPanel.tsx` receives and renders

### T6. Graceful shutdown
- [ ] SIGINT/Ctrl+C stops all watch loops cleanly
- [ ] No orphaned threads/processes
- [ ] State saved to YAML before exit

### T7. `prash watch` CLI options
- [ ] `--provider kubernetes/aws/datadog/all` — which connectors to watch
- [ ] `--interval 30` — override default polling interval
- [ ] `--once` — single poll cycle, then exit (for testing/scripting)

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_generic_watch_loop` | `tests/test_watcher.py` | Any connector with `watch()` works |
| `test_multi_connector_concurrent` | `tests/test_watcher.py` | Multiple connectors poll independently |
| `test_state_change_detection` | `tests/test_watcher.py` | New problem detected, resolved detected |
| `test_deduplication` | `tests/test_watcher.py` | Same problem not notified twice |
| `test_failure_degradation` | `tests/test_watcher.py` | healthy → degraded → error |
| `test_self_healing` | `tests/test_watcher.py` | Recovery restores healthy |
| `test_graceful_shutdown` | `tests/test_watcher.py` | SIGINT cleans up |
| `test_yaml_persistence` | `tests/test_watcher.py` | State survives restart |
| `test_websocket_broadcast` | `tests/test_watcher.py` | Events reach WebSocket |

---

## Acceptance Criteria

- [ ] One generic loop works for any connector
- [ ] Multiple connectors polled concurrently
- [ ] State changes detected and notified correctly
- [ ] Desktop WebSocket integration works
- [ ] All 44K+ of watcher tests pass
- [ ] CI green on all 3 OSes
