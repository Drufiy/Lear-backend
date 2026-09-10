# Task 01 — Base Interface Extension

**Priority:** Phase 0/1 — must land before any individual connector rewrite  
**Owner:** Anant  
**Spec ref:** CONNECTOR_REWRITE_SPEC §4a, §4b, §4c  
**Blocking:** Every other task in this folder  

---

## Goal

Extend `prash/connectors/base.py` with the three new capabilities (`watch()`, `get_stats()`, `ConnectorEvent`) and create the base `alert` Action skeleton in `prash/actions/`, so that every connector rewrite has a concrete interface to implement against.

---

## Current State

[`base.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/connectors/base.py) has:
- `Connector` ABC with `authenticate()`, `locate()`, `fetch_logs()`, `poll_state()`
- `ConnectorState` enum, `ResourceState` dataclass
- No `watch()`, no `get_stats()`, no `ConnectorEvent`, no `WatchHandle`

---

## Tasks

### 1. Define `ConnectorEvent` type
- [ ] Add `ConnectorEvent` as a `TypedDict` in `base.py`
- [ ] Fields: `timestamp` (datetime, UTC), `connector` (str), `event_type` (str), `summary` (str), `raw` (dict)
- [ ] Ensure it's importable from `prash.connectors.base`

### 2. Define `WatchHandle` type
- [ ] Add `WatchHandle` dataclass/protocol in `base.py`
- [ ] Must support: `stop()` method, `is_active` property, `connector` name, `target` string
- [ ] Design for async-compatible future (but sync-first for now)

### 3. Add `watch()` to `Connector` ABC
- [ ] Add `watch(self, target: str) -> WatchHandle` as a concrete default method
- [ ] Default raises `NotImplementedError` (same pattern as `fetch_logs`/`poll_state`)
- [ ] Docstring references §4c watcher integration

### 4. Add `get_stats()` to `Connector` ABC
- [ ] Add `get_stats(self, target: str, since: datetime | None = None) -> list[ConnectorEvent]` as a concrete default method
- [ ] Default raises `NotImplementedError`
- [ ] Docstring clarifies relationship to `poll_state()` (point-in-time) vs `get_stats()` (time-series)

### 5. Create base `alert` Action skeleton
- [ ] Create `prash/actions/alert_base.py` with a base `AlertAction(Action)` class
- [ ] Default `risk_tier = RiskTier.APPROVAL` (outbound + not cleanly reversible)
- [ ] `spec.capabilities = ("alert",)`
- [ ] Subclasses per provider will override `execute()` to call their specific alert API

### 6. Update `connectors/__init__.py`
- [ ] Export new types: `ConnectorEvent`, `WatchHandle`
- [ ] Update module docstring to reference the extended interface

### 7. Update `read_capabilities` / `write_capabilities` metadata pattern
- [ ] Document that connectors implementing `watch()` should add `"watch"` to `read_capabilities`
- [ ] Document that connectors implementing `get_stats()` should add `"stats"` to `read_capabilities`
- [ ] Document that each provider alert action adds `"alert"` to the connector's `write_capabilities`

---

## Testing

### Unit Tests
- [ ] `tests/test_base_connector.py` — verify default `watch()` raises `NotImplementedError`
- [ ] Verify default `get_stats()` raises `NotImplementedError`
- [ ] Verify `ConnectorEvent` accepts correct fields, rejects wrong types
- [ ] Verify `WatchHandle` protocol contract
- [ ] Verify `AlertAction` base class has correct `spec` defaults

### Integration Checks
- [ ] All existing connector tests still pass (backward compat §4e)
- [ ] `pytest` green on all platforms
- [ ] No import errors from any existing connector

---

## Backward Compatibility Checklist

- [ ] `ConnectorState` enum unchanged
- [ ] `ResourceState` dataclass unchanged
- [ ] `authenticate()`, `locate()`, `fetch_logs()`, `poll_state()` signatures unchanged
- [ ] No existing test breaks

---

## Definition of Done

- `Connector` ABC has `watch()` and `get_stats()` (default `NotImplementedError`)
- `ConnectorEvent` type defined and importable
- `WatchHandle` type defined
- Base `AlertAction` stub exists in `prash/actions/`
- All existing tests green
- Concrete types exist for Aradhya to build NLP integration (M3) against
