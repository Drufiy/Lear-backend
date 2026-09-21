# Azure Connector Rewrite — `connectors/azure.py`

**Owner:** Anant  
**Status:** Not started  
**Priority:** Tier 3  
**Depends on:** `00_BASE_INTERFACE.md`  

---

## Current State

`AzureConnector(Connector)` mirrors AWS/GCP: `authenticate()`, `poll_state()`, `fetch_logs()`, `execute_command()` (SDK → `az` CLI → SSH). Write action: `execute-azure` (APPROVAL).

**Missing:** `watch()`, `get_stats()`, `azure-alert` action.

---

## Tasks

### T1. `watch(target)` — poll Azure VM state + Monitor metrics
### T2. `get_stats(target, since?)` — Azure Monitor → `ConnectorEvent`
### T3. `AzureAlertAction` — APPROVAL tier
### T4. Preserve SDK → CLI → SSH fallback

---

## Tests

| Test | File | What it verifies |
|---|---|---|
| `test_azure_watch` | `tests/test_azure_connector.py` | Valid `WatchHandle` |
| `test_azure_get_stats` | `tests/test_azure_connector.py` | `ConnectorEvent` shape |
| `test_azure_fallback` | `tests/test_azure_connector.py` | Fallback chain preserved |

---

## Acceptance Criteria

- [ ] Full loop closure (watch → diagnose → fix → verify → notify)
- [ ] All existing Azure tests pass
