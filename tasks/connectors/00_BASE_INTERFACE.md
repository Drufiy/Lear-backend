# Base Connector Interface — `connectors/base.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 1  
**Depends on:** Nothing  
**Blocks:** Every other connector rewrite  

---

## Goal

Add `watch()` and `get_stats()` to the `Connector` ABC, plus the `ConnectorEvent` and `WatchHandle` shared types. Every connector rewrite builds on top of this.

---

## Tasks

### T1. Define `ConnectorEvent` TypedDict
- [ ] Add `ConnectorEvent` to `connectors/base.py` (or a shared types file)
- [ ] Fields: `timestamp: datetime` (UTC), `connector: str`, `event_type: str`, `summary: str`, `raw: dict`, `severity: str`
- [ ] Ensure JSON-serializable for WebSocket broadcast

### T2. Define `WatchHandle` dataclass
- [ ] `connector_id: str`, `target: str`, `interval_seconds: int`, `state: Literal["healthy","degraded","error"]`
- [ ] `failure_count: int`, `last_poll: datetime | None`, `last_event: ConnectorEvent | None`
- [ ] Method: `is_active() -> bool`

### T3. Add `watch()` to `Connector` ABC
- [ ] `def watch(self, target: str) -> WatchHandle` — concrete default raising `NotImplementedError`
- [ ] Docstring: purpose, return type, relationship to `poll_state()`
- [ ] Same pattern as existing `fetch_logs`/`poll_state` (concrete default, not abstract)

### T4. Add `get_stats()` to `Connector` ABC
- [ ] `def get_stats(self, target: str, since: datetime | None = None) -> list[ConnectorEvent]`
- [ ] Concrete default raising `NotImplementedError`
- [ ] Docstring: "time-series, not point-in-time" distinction from `poll_state()`

### T5. Backward compatibility check
- [ ] Verify all 14 existing connector subclasses still instantiate cleanly
- [ ] Verify no existing test breaks (the new methods raise `NotImplementedError` by default)
- [ ] Verify `connector_registry.py` still works with unchanged connectors

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_connector_event_shape` | `tests/test_connector_base.py` | `ConnectorEvent` has all required fields |
| `test_watch_handle_defaults` | `tests/test_connector_base.py` | `WatchHandle` initializes with correct defaults |
| `test_watch_not_implemented` | `tests/test_connector_base.py` | Base `watch()` raises `NotImplementedError` |
| `test_get_stats_not_implemented` | `tests/test_connector_base.py` | Base `get_stats()` raises `NotImplementedError` |
| `test_existing_connectors_unbroken` | `tests/test_connector_base.py` | All 14 connectors still instantiate |

---

## Acceptance Criteria

- [ ] `ConnectorEvent` and `WatchHandle` importable from `prash.connectors.base`
- [ ] All existing connector tests pass unchanged
- [ ] `connector_registry.py` unchanged
- [ ] CI green on Linux/Windows/macOS
