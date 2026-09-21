# Circuit Breaker — `circuit_breaker.py`

**Owner:** Aryan  
**Status:** Built  
**Priority:** Tier 1  

---

## Current State

Persistent per-resource action cap (default 5 actions / 60s window). On breach: stop, audit with `reason=circuit_open`, escalate to human. `prash circuit status/reset` for management.

---

## Tasks

### T1. Verify circuit breaker coverage
- [ ] Every action dispatched through `Dispatcher.run()` checks circuit breaker FIRST
- [ ] Circuit breaker checked BEFORE permission prompt (don't ask then refuse)
- [ ] Per-resource granularity: pod `api-7f9d` separate from pod `worker-abc`
- [ ] Per-namespace aggregation option: all pods in `production` share a budget

### T2. Configuration
- [ ] `PRASH_CIRCUIT_MAX_ACTIONS` — max actions per resource per window (default 5)
- [ ] `PRASH_CIRCUIT_WINDOW_SECONDS` — time window (default 60)
- [ ] Configurable via `.env` or `prash.yaml`
- [ ] `prash config` shows current circuit breaker settings

### T3. Autopilot mode safety
- [ ] In autopilot (24/7 watcher), circuit breaker prevents runaway loops
- [ ] Crash-loop → restart → crash → restart → CIRCUIT OPEN
- [ ] Escalation: notify team that circuit breaker tripped
- [ ] Manual reset required: `prash circuit reset <resource>`

### T4. Circuit breaker persistence
- [ ] State survives process restart
- [ ] Stored in `.prash/circuit_state.json` or similar
- [ ] `prash circuit status` shows all open circuits and their counts

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_circuit_blocks_after_limit` | `tests/test_circuit_breaker.py` | 6th action blocked |
| `test_circuit_per_resource` | `tests/test_circuit_breaker.py` | Different resources independent |
| `test_circuit_reset` | `tests/test_circuit_breaker.py` | Manual reset clears state |
| `test_circuit_window_expiry` | `tests/test_circuit_breaker.py` | Window expires, actions allowed |
| `test_circuit_persistence` | `tests/test_circuit_breaker.py` | State survives restart |

---

## Acceptance Criteria

- [ ] Circuit breaker prevents runaway action loops
- [ ] Per-resource granularity
- [ ] Persistent state
- [ ] Team notification on trip
