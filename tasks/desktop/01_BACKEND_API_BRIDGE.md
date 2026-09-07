# Feature 01 — Backend API Bridge

**Priority:** P0 — everything depends on this  
**Owner:** TBD  
**Depends on:** Existing `prash/connectors/` module, existing `prash/server.py`  
**Target file:** [`prash/server.py`](file:///c:/Users/anant/Downloads/Lear-Backend/Lear-Backend/prash/server.py)  
**Test file:** `tests/test_desktop_api.py` (new)

---

## Product Spec

The Backend API Bridge is the FastAPI server that acts as the single gateway between the React frontend and all 13 backend connectors. Every piece of data shown in the desktop app — metrics, statuses, events, chat responses — flows through this API.

### What It Does

1. **Exposes every connector** through a uniform REST API — no per-connector endpoint spaghetti
2. **Manages connector lifecycle** — instantiate, authenticate, cache, tear down
3. **Bridges the watcher** — start/stop/poll watch handles for live monitoring
4. **Serves AI context** — feeds connector data into the brain module for chat
5. **Manages project state** — CRUD for projects/environments/services (persisted in `prash.yaml`)
6. **Real-time events** — WebSocket endpoint for pushing watch events to the frontend without polling

### What It Must NOT Do

- **Hold any state that isn't in `.env` or `prash.yaml`** — restart-safe
- **Hardcode any connector behavior** — all connector-specific logic lives in the connector classes
- **Return mock/fake data** — if a connector isn't configured, return an explicit error, never fabricated numbers
- **Expose credentials** — API returns masked versions only (first 3 + last 3 chars)

### API Surface

| Method | Endpoint | Purpose | Response Shape |
|---|---|---|---|
| `GET` | `/api/connectors` | List all available connectors with status | `{connectors: [{id, name, category, icon, color, status, auth_fields}]}` |
| `POST` | `/api/connectors/{id}/connect` | Authenticate a connector with credentials | `{success: bool, message: str}` |
| `GET` | `/api/connectors/{id}/status` | Live health check | `{status: "healthy"|"error"|"unconfigured", detail: {...}}` |
| `GET` | `/api/connectors/{id}/metrics` | Fetch current metrics/stats | `{metrics: [{name, value, unit, timestamp}], events: [ConnectorEvent]}` |
| `GET` | `/api/connectors/{id}/resources` | Discover watchable resources | `{resources: [{id, name, type, state}]}` |
| `POST` | `/api/connectors/{id}/watch` | Start watching a resource | `{watch_id: str, target: str}` |
| `DELETE` | `/api/connectors/{id}/watch` | Stop watching | `{success: bool}` |
| `GET` | `/api/watch/poll` | Poll all active watch handles | `{events: [ConnectorEvent]}` |
| `WS` | `/ws/events` | Real-time event stream | Pushes `ConnectorEvent` objects |
| `GET` | `/api/projects` | List all projects | `{projects: [{id, name, environments, services}]}` |
| `POST` | `/api/projects` | Create/update a project | `{project: {...}}` |
| `DELETE` | `/api/projects/{id}` | Delete a project | `{success: bool}` |
| `POST` | `/api/chat` | AI chat with service context | `{text: str, actionRequired: bool, command?: str[]}` |
| `GET` | `/api/config` | Get masked config overview | `{services: {...}, raw: {...}}` |
| `POST` | `/api/config` | Update `.env` values | `{success: bool}` |

### Connector Instance Management

```python
# Connectors are instantiated lazily and cached per-session
# NOT hardcoded — dynamically resolved from the registry

_active_connectors: Dict[str, Connector] = {}

def get_connector(connector_id: str) -> Connector:
    """Get or create a connector instance from the registry."""
    if connector_id in _active_connectors:
        return _active_connectors[connector_id]
    
    registry_entry = CONNECTOR_REGISTRY.get(connector_id)
    if not registry_entry:
        raise HTTPException(404, f"Unknown connector: {connector_id}")
    
    config = dotenv.dotenv_values(ENV_PATH)
    connector = registry_entry["class"](config)
    _active_connectors[connector_id] = connector
    return connector
```

### Error Response Contract

Every endpoint returns errors in a consistent shape — never a bare 500:

```json
{
    "error": true,
    "code": "CONNECTOR_NOT_CONFIGURED",
    "message": "AWS connector requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY",
    "detail": {
        "missing_fields": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
    }
}
```

Error codes:
- `CONNECTOR_NOT_FOUND` — unknown connector ID
- `CONNECTOR_NOT_CONFIGURED` — credentials missing
- `CONNECTOR_AUTH_FAILED` — credentials rejected by provider
- `CONNECTOR_API_ERROR` — provider API returned an error
- `RESOURCE_NOT_FOUND` — requested resource doesn't exist
- `WATCH_ALREADY_ACTIVE` — duplicate watch request
- `INTERNAL_ERROR` — unexpected server error

---

## Detailed Task List

### Phase A — Core API Structure

- [ ] **A1. Create `CONNECTOR_REGISTRY` dict** — maps connector IDs to their class, auth fields, category, icon, color. Must import ALL 13 connector classes dynamically (guarded by try/except for missing deps)
- [ ] **A2. Implement `GET /api/connectors`** — iterate the registry, check each connector's auth status against `.env`, return the full list with `status: "configured"|"unconfigured"`
- [ ] **A3. Implement `POST /api/connectors/{id}/connect`** — receive credentials, save to `.env` via `dotenv.set_key`, instantiate connector, call `authenticate()`, return success/failure with actual provider error message
- [ ] **A4. Implement `GET /api/connectors/{id}/status`** — instantiate connector, call `authenticate()`, then `poll_state()` if a target resource is configured. Return real health status
- [ ] **A5. Implement error response middleware** — catch all exceptions and return the consistent error shape
- [ ] **A6. Remove all hardcoded fallback data** from existing `server.py` — no more `"disk_usage": 45.2` or `"ping": "14ms"` fallbacks

### Phase B — Metrics & Resources

- [ ] **B1. Implement `GET /api/connectors/{id}/metrics`** — call `connector.get_stats()`, normalize the response. If connector doesn't support `get_stats()`, return `{metrics: [], unsupported: true}`
- [ ] **B2. Implement `GET /api/connectors/{id}/resources`** — per-connector resource discovery:
  - AWS: `ec2.describe_instances()` → list instances
  - K8s: list pods/deployments/namespaces
  - GitHub: list repos with Actions enabled
  - Datadog: list monitors
  - etc.
- [ ] **B3. Add resource-specific metrics** — `GET /api/connectors/{id}/metrics?resource={resource_id}` for targeted metric queries

### Phase C — Watch System

- [ ] **C1. Implement `POST /api/connectors/{id}/watch`** — call `connector.watch(target)`, store the `WatchHandle` in-memory
- [ ] **C2. Implement `DELETE /api/connectors/{id}/watch`** — call `handle.stop()`, remove from active watches
- [ ] **C3. Implement `GET /api/watch/poll`** — iterate all active handles, call `handle.poll()`, aggregate events
- [ ] **C4. Implement WebSocket `/ws/events`** — background task that polls all handles every N seconds and pushes events to connected WebSocket clients
- [ ] **C5. Watch persistence** — on server restart, re-establish watches based on `prash.yaml` project config

### Phase D — Project CRUD

- [ ] **D1. Implement `GET /api/projects`** — read from `prash.yaml`
- [ ] **D2. Implement `POST /api/projects`** — create/update project in `prash.yaml`, validate that referenced services are actually configured
- [ ] **D3. Implement `DELETE /api/projects/{id}`** — remove project, stop any active watches for its services
- [ ] **D4. Project schema validation** — projects have `id`, `name`, `environments: [{name, services: [{connector_id, resource_id, display_name}]}]`

### Phase E — Enhanced Chat

- [ ] **E1. Modify `POST /api/chat`** — accept optional `service_context: {connector_id, resource_id}` in the request body
- [ ] **E2. Context injection** — when service_context is provided, fetch current metrics/status from that connector and prepend to the AI prompt
- [ ] **E3. Action execution** — when the AI suggests an action, include `executable: true` and `action_id` in the response so the frontend can show an "Execute" button

---

## Testing Methodology

### Unit Tests (`tests/test_desktop_api.py`)

```
test_list_connectors_returns_all_registered
test_list_connectors_shows_configured_status_from_env
test_list_connectors_shows_unconfigured_when_no_env
test_connect_aws_calls_real_authenticate
test_connect_aws_saves_to_dotenv
test_connect_aws_returns_provider_error_on_failure
test_connect_unknown_connector_returns_404
test_status_returns_real_poll_state
test_status_unconfigured_returns_explicit_error
test_metrics_calls_get_stats_not_hardcoded
test_metrics_unsupported_connector_returns_empty_with_flag
test_resources_returns_real_ec2_instances
test_watch_start_creates_handle
test_watch_poll_returns_real_events
test_watch_stop_calls_handle_stop
test_project_crud_persists_to_yaml
test_project_validates_service_exists
test_chat_includes_service_context
test_error_responses_have_consistent_shape
test_config_get_masks_secrets
test_config_post_updates_dotenv
```

### Anti-Hardcoding Test Suite

These tests specifically verify that no data is fabricated:

```
test_NO_HARDCODED_METRICS — /api/connectors/{id}/metrics must NOT return 
    data when the connector is not configured. Mock the connector's get_stats() 
    to raise NotImplementedError and verify the API returns {metrics: [], 
    unsupported: true}, NOT fake numbers.

test_NO_HARDCODED_STATUS — /api/connectors/{id}/status with no credentials 
    must return {status: "unconfigured"}, NOT {status: "healthy"}.

test_NO_HARDCODED_PING — Verify that no endpoint returns a hardcoded 
    latency string like "14ms" or "22ms". Grep all response fixtures 
    for numeric+ms patterns.

test_NO_HARDCODED_FALLBACKS — Parse server.py source code. Assert that 
    no numeric literal is used in a response dict (e.g., no 
    `"disk_usage": 45.2`). Use AST analysis or regex.

test_CONNECTOR_AGNOSTIC_ROUTES — Every /api/connectors/{id}/* route 
    works with ANY registered connector ID, not just "aws" or "github". 
    Test with a MockConnector registered at runtime.

test_NO_SIMULATED_EVENTS — /api/watch/poll with no active watches 
    returns {events: []}, NOT synthetic events.

test_ERROR_NEVER_SILENT — When a connector throws an exception, the API 
    returns the real error message, not a generic "ok" response.
```

### Integration Tests

- [ ] **Full flow test**: Register a mock connector → connect → start watch → poll → get events → stop watch
- [ ] **Multi-connector test**: Configure 3 connectors simultaneously, verify independent status/metrics
- [ ] **Restart resilience test**: Start server, configure connectors, restart server, verify config persisted

### Load/Performance Tests

- [ ] **Concurrent watch polling**: 10 active watches, verify poll completes within 2 seconds
- [ ] **WebSocket stability**: Connect WS client, keep alive for 5 minutes, verify no disconnection
- [ ] **Memory leak check**: Start/stop 100 watch cycles, verify no handle accumulation

---

## Definition of Done

- [ ] All 13 connectors accessible via `/api/connectors`
- [ ] `POST /api/connectors/{id}/connect` calls REAL `authenticate()` — not simulated
- [ ] `/api/connectors/{id}/metrics` returns REAL data from the connector — never hardcoded numbers
- [ ] Watch system starts/stops/polls correctly
- [ ] WebSocket pushes events in real-time
- [ ] Project CRUD persists to `prash.yaml`
- [ ] Chat includes real service context
- [ ] Zero hardcoded fallback values in any response
- [ ] All anti-hardcoding tests pass
- [ ] Error responses follow consistent contract
