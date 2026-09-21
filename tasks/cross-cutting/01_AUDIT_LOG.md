# Audit Log — `audit.py`

**Owner:** Aryan  
**Status:** Built  
**Priority:** Tier 1  

---

## Current State

Append-only audit log in `.prash/audit.log`. Every action records: action_id, risk_tier, target, was_approved, outcome, timestamp.

---

## Tasks

### T1. Complete provenance tracking
- [ ] Log which `ConnectorEvent`(s) triggered the diagnosis
- [ ] Log the full diagnosis summary (not just the action taken)
- [ ] Log options selections: "user selected option 2 of 3 (restart_pod)"
- [ ] Log dry-run executions with `dry_run=True`
- [ ] Log circuit breaker trips with `reason=circuit_open`

### T2. Audit log querying
- [ ] `prash audit` — view recent entries
- [ ] `prash audit --filter action=restart-pod` — filter by action
- [ ] `prash audit --since 1h` — time-based filtering
- [ ] `GET /api/activity` — desktop API returns structured audit data

### T3. Audit log rotation
- [ ] Maximum file size (default 10MB)
- [ ] Rotate to `.prash/audit.log.1`, `.prash/audit.log.2`, etc.
- [ ] Configurable retention (default 30 days)

### T4. Desktop Activity Log integration
- [ ] Merge in-memory `_activity_log` with disk-based `AuditLog`
- [ ] `GET /api/activity` returns combined, deduplicated, sorted events
- [ ] Pagination support (`limit`, `offset`)

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_audit_append` | `tests/test_audit.py` | Entries appended correctly |
| `test_audit_provenance` | `tests/test_audit.py` | ConnectorEvent source tracked |
| `test_audit_options_logged` | `tests/test_audit.py` | Option selections recorded |
| `test_audit_rotation` | `tests/test_audit.py` | File rotated at size limit |
| `test_audit_api` | `tests/test_desktop_api.py` | API returns structured data |

---

## Acceptance Criteria

- [ ] Every action type produces a complete audit entry
- [ ] Options selections logged with context
- [ ] File rotation prevents unbounded growth
- [ ] Desktop Activity Log shows all events
