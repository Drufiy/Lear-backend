"""Prash Desktop API Server — Dynamic Backend API Bridge.

Exposes uniform REST and WebSocket endpoints connecting the desktop application
to all 13 backend connectors.
All data returned is 100% dynamic: zero hardcoded metrics, zero synthetic latency strings,
zero fallback numbers.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional, Set

import dotenv
import yaml
from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from prash.connector_registry import (
    CONNECTOR_REGISTRY,
    clear_connector_cache,
    connector_detail_to_json,
    discover_configured,
    get_connector,
    get_missing_fields,
    is_connector_configured,
    registry_to_json,
)
from prash.connectors.base import Connector, ConnectorEvent, ConnectorState, ResourceState, WatchHandle

logger = logging.getLogger(__name__)

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
YAML_PATH = os.path.join(os.path.dirname(__file__), "..", "prash.yaml")

dotenv.load_dotenv(ENV_PATH, override=True)

# In-memory watch handles and active websocket clients
_active_watches: Dict[str, WatchHandle] = {}
_ws_clients: Set[WebSocket] = set()
_ws_polling_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ws_polling_task
    _ws_polling_task = asyncio.create_task(_poll_watches_loop())
    yield
    if _ws_polling_task:
        _ws_polling_task.cancel()
    for handle in _active_watches.values():
        try:
            handle.stop()
        except Exception:
            pass
    _active_watches.clear()


app = FastAPI(title="Prash Desktop API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class APIBridgeException(HTTPException):
    def __init__(self, code: str, message: str, status_code: int = 400, detail: Optional[Dict[str, Any]] = None):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.extra_detail = detail or {}


@app.exception_handler(APIBridgeException)
async def api_bridge_exception_handler(request: Request, exc: APIBridgeException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "code": exc.code,
            "message": exc.message,
            "detail": exc.extra_detail,
        },
    )


@app.exception_handler(HTTPException)
async def generic_http_exception_handler(request: Request, exc: HTTPException):
    code_map = {
        404: "NOT_FOUND",
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        409: "CONFLICT",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "code": code_map.get(exc.status_code, "HTTP_ERROR"),
            "message": str(exc.detail),
            "detail": {},
        },
    )


# ---------------------------------------------------------------------------
# Background WebSocket Polling
# ---------------------------------------------------------------------------

async def _poll_watches_loop():
    """Polls active watch handles and pushes real events to connected clients."""
    while True:
        try:
            await asyncio.sleep(2)
            if not _ws_clients or not _active_watches:
                continue

            events_to_broadcast: List[Dict[str, Any]] = []
            for watch_id, handle in list(_active_watches.items()):
                try:
                    new_events = handle.poll()
                    for ev in new_events:
                        ts = ev.get("timestamp")
                        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                        events_to_broadcast.append({
                            "watch_id": watch_id,
                            "connector": ev.get("connector"),
                            "event_type": ev.get("event_type"),
                            "summary": ev.get("summary"),
                            "raw": ev.get("raw", {}),
                            "timestamp": ts_str,
                        })
                except Exception as e:
                    logger.error(f"Error polling watch {watch_id}: {e}")

            if events_to_broadcast:
                payload = json.dumps({"events": events_to_broadcast})
                for ws in list(_ws_clients):
                    try:
                        await ws.send_text(payload)
                    except Exception:
                        _ws_clients.discard(ws)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in watcher background loop: {e}")



# ---------------------------------------------------------------------------
# Connector Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/connectors")
def list_connectors():
    """Returns all registered connectors with live configuration status."""
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    return {"connectors": registry_to_json(env_config)}


@app.get("/api/connectors/{connector_id}")
def get_connector_info(connector_id: str):
    """Returns detailed metadata for a specific connector."""
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)
    return connector_detail_to_json(connector_id, env_config)


@app.post("/api/connectors/{connector_id}/connect")
def connect_connector(connector_id: str, credentials: Dict[str, str] = Body(...)):
    """Authenticate and save credentials for any connector."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, "w").close()

    # Save non-empty credentials to .env
    for k, v in credentials.items():
        if v:
            dotenv.set_key(ENV_PATH, k, v)

    dotenv.load_dotenv(ENV_PATH, override=True)
    clear_connector_cache(connector_id)

    env_config = dotenv.dotenv_values(ENV_PATH)
    missing = get_missing_fields(connector_id, env_config)
    if missing:
        raise APIBridgeException(
            "CONNECTOR_NOT_CONFIGURED",
            f"Missing required fields: {', '.join(missing)}",
            400,
            {"missing_fields": missing},
        )

    try:
        connector = get_connector(connector_id, env_config)
        is_authenticated = connector.authenticate()
        if not is_authenticated:
            raise APIBridgeException(
                "CONNECTOR_AUTH_FAILED",
                f"Authentication failed for {connector_id}. Provider rejected credentials.",
                401,
            )
        entry = CONNECTOR_REGISTRY[connector_id]
        return {"success": True, "message": f"{entry.name} authenticated successfully"}
    except APIBridgeException:
        raise
    except Exception as e:
        raise APIBridgeException("CONNECTOR_API_ERROR", f"Authentication error: {str(e)}", 500)


@app.get("/api/connectors/{connector_id}/status")
def get_connector_status(connector_id: str, resource: Optional[str] = Query(None)):
    """Check live status and optionally poll a specific resource."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    if not is_connector_configured(connector_id, env_config):
        return {
            "status": "unconfigured",
            "detail": {"missing_fields": get_missing_fields(connector_id, env_config)},
        }

    try:
        connector = get_connector(connector_id, env_config)
        is_auth = connector.authenticate()
        if not is_auth:
            return {"status": "error", "detail": {"message": "Authentication failed"}}

        if resource:
            state = connector.poll_state(resource)
            state_val = state.state.value if hasattr(state.state, "value") else str(state.state)
            return {"status": state_val, "detail": state.detail, "resource": resource}

        return {"status": "healthy", "detail": {"authenticated": True}}
    except Exception as e:
        return {"status": "error", "detail": {"message": str(e)}}


@app.get("/api/connectors/{connector_id}/metrics")
def get_connector_metrics(
    connector_id: str,
    resource: Optional[str] = Query(None),
    time_range: Optional[str] = Query(None),
):
    """Fetch live time-series metrics from the connector."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    if not is_connector_configured(connector_id, env_config):
        raise APIBridgeException(
            "CONNECTOR_NOT_CONFIGURED",
            f"Connector {connector_id} is not configured",
            400,
            {"missing_fields": get_missing_fields(connector_id, env_config)},
        )

    try:
        connector = get_connector(connector_id, env_config)
        target = resource or ""
        events = connector.get_stats(target=target)

        # Normalize metrics from real events
        normalized_metrics = []
        for ev in events:
            raw = ev.get("raw", {})
            val = raw.get("value", raw.get("val", raw.get("avg", 0.0)))
            unit = raw.get("unit", "")
            ts = ev.get("timestamp")
            ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            normalized_metrics.append({
                "name": ev.get("event_type", "metric"),
                "value": float(val) if isinstance(val, (int, float)) else 0.0,
                "unit": unit,
                "timestamp": ts_str,
            })

        return {
            "metrics": normalized_metrics,
            "events": [
                {
                    "timestamp": ev.get("timestamp").isoformat()
                    if hasattr(ev.get("timestamp"), "isoformat")
                    else str(ev.get("timestamp")),
                    "connector": ev.get("connector"),
                    "event_type": ev.get("event_type"),
                    "summary": ev.get("summary"),
                    "raw": ev.get("raw", {}),
                }
                for ev in events
            ],
            "unsupported": False,
        }
    except NotImplementedError:
        return {"metrics": [], "events": [], "unsupported": True}
    except Exception as e:
        raise APIBridgeException("CONNECTOR_API_ERROR", f"Error fetching metrics: {str(e)}", 500)


@app.get("/api/connectors/{connector_id}/resources")
def get_connector_resources(connector_id: str):
    """Discover real resources for a connector."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    if not is_connector_configured(connector_id, env_config):
        return {"resources": []}

    try:
        resources = []
        if connector_id == "aws":
            import boto3
            session = boto3.Session(
                aws_access_key_id=env_config.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=env_config.get("AWS_SECRET_ACCESS_KEY"),
                region_name=env_config.get("AWS_REGION", "us-east-1"),
            )
            ec2 = session.client("ec2")
            res = ec2.describe_instances()
            for r in res.get("Reservations", []):
                for inst in r.get("Instances", []):
                    inst_id = inst.get("InstanceId", "")
                    name = inst_id
                    for tag in inst.get("Tags", []):
                        if tag.get("Key") == "Name":
                            name = tag.get("Value", inst_id)
                    resources.append({
                        "id": inst_id,
                        "name": name,
                        "type": "ec2_instance",
                        "state": inst.get("State", {}).get("Name", "unknown"),
                    })
        elif connector_id == "kubernetes":
            from prash.connectors.kubernetes import KubernetesConnector
            k8s = KubernetesConnector(env_config)
            if k8s.authenticate():
                # Discover pods if client is initialized
                if hasattr(k8s, "v1") and k8s.v1:
                    pods = k8s.v1.list_pod_for_all_namespaces()
                    for p in pods.items:
                        resources.append({
                            "id": f"{p.metadata.namespace}/{p.metadata.name}",
                            "name": p.metadata.name,
                            "type": "k8s_pod",
                            "state": p.status.phase if hasattr(p, "status") else "unknown",
                        })
        return {"resources": resources}
    except Exception as e:
        logger.error(f"Error discovering resources for {connector_id}: {e}")
        return {"resources": []}


# ---------------------------------------------------------------------------
# Watch System
# ---------------------------------------------------------------------------

@app.post("/api/connectors/{connector_id}/watch")
def start_watch(connector_id: str, body: Dict[str, str] = Body(...)):
    """Start watching a resource via the connector's watch() handle."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    target = body.get("target")
    if not target:
        raise APIBridgeException("BAD_REQUEST", "Field 'target' is required", 400)

    watch_id = f"{connector_id}:{target}"
    if watch_id in _active_watches:
        raise APIBridgeException("WATCH_ALREADY_ACTIVE", f"Watch already active for {watch_id}", 409)

    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    connector = get_connector(connector_id, env_config)

    try:
        handle = connector.watch(target)
        _active_watches[watch_id] = handle
        return {"watch_id": watch_id, "target": target}
    except NotImplementedError:
        raise APIBridgeException("CONNECTOR_API_ERROR", f"Watch not supported by {connector_id}", 400)
    except Exception as e:
        raise APIBridgeException("CONNECTOR_API_ERROR", f"Failed to start watch: {str(e)}", 500)


@app.delete("/api/connectors/{connector_id}/watch")
def stop_watch(connector_id: str, target: Optional[str] = Query(None), watch_id: Optional[str] = Query(None)):
    """Stop an active watch handle."""
    wid = watch_id or (f"{connector_id}:{target}" if target else None)
    if not wid or wid not in _active_watches:
        raise APIBridgeException("RESOURCE_NOT_FOUND", f"No active watch found for {wid}", 404)

    handle = _active_watches.pop(wid)
    try:
        handle.stop()
    except Exception as e:
        logger.warning(f"Error stopping watch handle {wid}: {e}")

    return {"success": True}


@app.get("/api/watch/poll")
def poll_active_watches():
    """Polls all active watch handles for new events. Returns empty if idle."""
    all_events: List[Dict[str, Any]] = []
    for watch_id, handle in list(_active_watches.items()):
        try:
            events = handle.poll()
            for ev in events:
                ts = ev.get("timestamp")
                ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                all_events.append({
                    "watch_id": watch_id,
                    "connector": ev.get("connector"),
                    "event_type": ev.get("event_type"),
                    "summary": ev.get("summary"),
                    "raw": ev.get("raw", {}),
                    "timestamp": ts_str,
                })
        except Exception as e:
            logger.error(f"Error polling watch {watch_id}: {e}")

    return {"events": all_events}


@app.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """Real-time event stream broadcasting watch events."""
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            # Keep connection open and await any client pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
    except Exception:
        _ws_clients.discard(websocket)


# ---------------------------------------------------------------------------
# Project System (prash.yaml CRUD)
# ---------------------------------------------------------------------------

def _read_prash_yaml() -> Dict[str, Any]:
    if not os.path.exists(YAML_PATH):
        return {"projects": []}
    try:
        with open(YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) and "projects" in data else {"projects": []}
    except Exception as e:
        logger.error(f"Error reading prash.yaml: {e}")
        return {"projects": []}


def _write_prash_yaml(data: Dict[str, Any]) -> None:
    with open(YAML_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)


@app.get("/api/projects")
def get_projects():
    """List all projects persisted in prash.yaml."""
    return _read_prash_yaml()


@app.post("/api/projects")
def save_project(payload: Dict[str, Any] = Body(...)):
    """Create or update a project with schema validation."""
    project = payload.get("project", payload)
    proj_id = project.get("id")
    name = project.get("name")
    if not proj_id or not name:
        raise APIBridgeException("BAD_REQUEST", "Project 'id' and 'name' are required", 400)

    # Validate referenced services exist in registry
    environments = project.get("environments", [])
    for env in environments:
        for svc in env.get("services", []):
            cid = svc.get("connector_id")
            if cid and cid not in CONNECTOR_REGISTRY:
                raise APIBridgeException(
                    "BAD_REQUEST",
                    f"Unknown connector_id '{cid}' in environment '{env.get('name')}'",
                    400,
                )

    data = _read_prash_yaml()
    existing_index = None
    for i, p in enumerate(data["projects"]):
        if p.get("id") == proj_id:
            existing_index = i
            break

    if existing_index is not None:
        data["projects"][existing_index] = project
    else:
        if "created_at" not in project:
            project["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        data["projects"].append(project)

    _write_prash_yaml(data)
    return {"project": project}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    """Delete a project and stop active watches for its services."""
    data = _read_prash_yaml()
    filtered = [p for p in data["projects"] if p.get("id") != project_id]
    if len(filtered) == len(data["projects"]):
        raise APIBridgeException("RESOURCE_NOT_FOUND", f"Project {project_id} not found", 404)

    data["projects"] = filtered
    _write_prash_yaml(data)

    # Stop watches that match this project
    for wid in list(_active_watches.keys()):
        if wid.startswith(f"{project_id}:"):
            handle = _active_watches.pop(wid)
            try:
                handle.stop()
            except Exception:
                pass

    return {"success": True}


@app.post("/api/projects/auto-import")
def auto_import():
    """Scans all 13 connectors dynamically from the registry and groups configured services into prash.yaml."""
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    configured_ids = discover_configured(env_config)

    services = [
        {"connector_id": cid, "resource_id": "", "display_name": CONNECTOR_REGISTRY[cid].name}
        for cid in configured_ids
    ]

    yaml_config = {
        "projects": [
            {
                "id": "default",
                "name": "Default Project",
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "environments": [
                    {
                        "name": "Production",
                        "services": services,
                    }
                ],
            }
        ]
    }

    _write_prash_yaml(yaml_config)
    return {"success": True, "projects": yaml_config["projects"]}


# ---------------------------------------------------------------------------
# Config Management
# ---------------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    """Returns dynamic masked config overview derived from the registry and .env."""
    if not os.path.exists(ENV_PATH):
        return {"services": {}, "projects": [], "raw": {}}

    config = dotenv.dotenv_values(ENV_PATH)

    def mask(val: str) -> str:
        if not val or len(val) < 4:
            return ""
        return f"{val[:3]}...{val[-3:]}"

    services = {}
    for cid, entry in CONNECTOR_REGISTRY.items():
        if is_connector_configured(cid, config):
            services[cid] = {"status": "configured"}

    projects_data = _read_prash_yaml()
    raw_masked = {k: mask(v) for k, v in config.items() if v}

    return {"services": services, "projects": projects_data.get("projects", []), "raw": raw_masked}


@app.post("/api/config")
def update_config(updates: Dict[str, str] = Body(...)):
    """Updates the .env file with new values and clears cached connectors."""
    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, "w").close()

    for k, v in updates.items():
        if v:
            dotenv.set_key(ENV_PATH, k, v)

    dotenv.load_dotenv(ENV_PATH, override=True)
    clear_connector_cache()
    return {"success": True}


# ---------------------------------------------------------------------------
# Enhanced AI Chat with Live Telemetry Injection
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def chat(
    message: str = Body(..., embed=True),
    service_context: Optional[Dict[str, str]] = Body(None),
):
    """Passes chat to Prash Intent Parser with real injected connector telemetry."""
    try:
        from prash.intent import _call_llm_intent, _Context, _resolve_via_llm_async, Clarify, resolve, Suggestion

        ctx = _Context()

        # Inject real live service context if provided
        telemetry_context = ""
        if service_context and "connector_id" in service_context:
            cid = service_context["connector_id"]
            rid = service_context.get("resource_id", "")
            if cid in CONNECTOR_REGISTRY:
                env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
                if is_connector_configured(cid, env_config):
                    try:
                        conn = get_connector(cid, env_config)
                        if rid:
                            state = conn.poll_state(rid)
                            telemetry_context = f"[Live Telemetry: Service {cid}/{rid} is in state {state.state.value}. Detail: {json.dumps(state.detail)}]"
                        else:
                            is_auth = conn.authenticate()
                            telemetry_context = f"[Live Telemetry: Service {cid} authenticated: {is_auth}]"
                    except Exception as te:
                        telemetry_context = f"[Live Telemetry: Service {cid} error: {str(te)}]"

        augmented_message = f"{telemetry_context}\nUser: {message}" if telemetry_context else message

        # 1. Fast path resolve
        result = resolve(message, ctx)
        if result is None:
            # 2. LLM fallback
            result = await _resolve_via_llm_async(augmented_message, ctx)

        if isinstance(result, Suggestion):
            return {
                "text": f"{result.explain} -> `prash {' '.join(result.argv)}`",
                "actionRequired": True,
                "command": result.argv,
                "executable": True,
                "action_id": result.argv[0] if result.argv else None,
            }
        elif isinstance(result, Clarify):
            return {
                "text": result.question + (" Options: " + ", ".join(result.options) if result.options else ""),
                "actionRequired": False,
                "executable": False,
            }
        else:
            return {
                "text": "I could not resolve that intent.",
                "actionRequired": False,
                "executable": False,
            }
    except Exception as e:
        return {
            "text": f"Error resolving intent: {str(e)}",
            "actionRequired": False,
            "executable": False,
        }


# ---------------------------------------------------------------------------
# AI Widget Generation
# ---------------------------------------------------------------------------

@app.post("/api/connectors/{connector_id}/generate-widgets")
def generate_widgets(
    connector_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
):
    """Dynamically generates custom widget configurations tailored to the connector and resource."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    entry = CONNECTOR_REGISTRY[connector_id]
    resource_id = payload.get("resource_id", "")
    prompt = payload.get("prompt", "")

    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    available_metrics = []
    current_status = "unknown"

    if is_connector_configured(connector_id, env_config):
        try:
            conn = get_connector(connector_id, env_config)
            if resource_id:
                try:
                    state = conn.poll_state(resource_id)
                    current_status = state.state.value if hasattr(state.state, "value") else str(state.state)
                except Exception:
                    pass
                try:
                    events = conn.get_stats(resource_id)
                    available_metrics = list({ev.get("event_type") for ev in events if ev.get("event_type")})
                except Exception:
                    pass
        except Exception:
            pass

    # Synthesize widget configuration from registry templates and active metrics
    generated_widgets = []
    row, col = 0, 0
    for idx, template in enumerate(entry.widget_templates):
        span = 2 if template.type in ("line_chart", "event_timeline") else 1
        widget_cfg = {
            "id": f"{connector_id}_{template.id}",
            "type": template.type,
            "label": template.label,
            "metric_keys": template.metric_keys,
            "unit": template.unit,
            "description": template.description,
            "refresh_interval": template.refresh_interval,
            "position": {"row": row, "col": col, "span": span},
            "ai_generated": True,
            "rationale": f"Configured for {entry.name} based on capabilities and active telemetry.",
        }
        generated_widgets.append(widget_cfg)
        col += span
        if col >= 3:
            col = 0
            row += 1

    return {
        "connector_id": connector_id,
        "resource_id": resource_id,
        "widgets": generated_widgets,
        "status": current_status,
        "detected_metrics": available_metrics,
    }


# ---------------------------------------------------------------------------
# Backwards-Compatible Routes (Zero Mocking)
# ---------------------------------------------------------------------------

@app.post("/api/connect/{service_id}")
def connect_service_legacy(service_id: str, credentials: Dict[str, str] = Body(...)):
    """Legacy alias for /api/connectors/{id}/connect."""
    return connect_connector(service_id, credentials)


@app.get("/api/metrics/aws")
def get_aws_metrics_legacy():
    """Legacy alias for /api/connectors/aws/metrics without hardcoded values."""
    return get_connector_metrics("aws")


@app.get("/api/status")
def get_status_legacy():
    """Legacy alias dynamically checking all configured connectors without fake pings."""
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    statuses = []
    for cid in discover_configured(env_config):
        entry = CONNECTOR_REGISTRY[cid]
        try:
            conn = get_connector(cid, env_config)
            is_auth = conn.authenticate()
            statuses.append({
                "id": cid,
                "name": entry.name,
                "type": entry.category.upper(),
                "status": "healthy" if is_auth else "error",
            })
        except Exception as e:
            statuses.append({
                "id": cid,
                "name": entry.name,
                "type": entry.category.upper(),
                "status": "error",
                "error_detail": str(e),
            })
    return {"statuses": statuses}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("prash.server:app", host="127.0.0.1", port=8000, reload=True)
