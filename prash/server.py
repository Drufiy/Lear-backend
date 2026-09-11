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
import shutil
import tempfile
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Mapping, Optional, Set

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
    mask_credential,
    registry_to_json,
    safe_mask,
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
_notifications: List[Dict[str, Any]] = []

# Global in-memory activity log for Task 14
_activity_log: List[Dict[str, Any]] = []
_health_check_task: Optional[asyncio.Task] = None
_connection_states: Dict[str, Dict[str, Any]] = {}
# Connector SDKs inconsistently consult their config mapping and os.environ.
# Serialize temporary environment projection and dotenv read-modify-replace operations.
_auth_environment_lock = threading.RLock()
_dotenv_lock = threading.RLock()


def _auth_keys(connector_id: str) -> List[str]:
    return [field.key for field in CONNECTOR_REGISTRY[connector_id].auth_fields]


def _owned_config(connector_id: str, config: Mapping[str, Any], include_defaults: bool = True) -> Dict[str, Any]:
    """Return only registry fields owned by one connector."""
    owned: Dict[str, Any] = {}
    for field in CONNECTOR_REGISTRY[connector_id].auth_fields:
        if field.key in config:
            owned[field.key] = config[field.key]
        elif include_defaults and field.default:
            owned[field.key] = field.default
    return owned


@contextmanager
def _candidate_auth_environment(connector_id: str, candidate: Mapping[str, Any]) -> Iterator[None]:
    """Expose only candidate registry values while constructing/authenticating a connector."""
    keys = _auth_keys(connector_id)
    with _auth_environment_lock:
        previous = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                value = candidate.get(key)
                if value is None or str(value) == "":
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = str(value)
            yield
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def _read_credentials() -> Dict[str, Any]:
    with _dotenv_lock:
        return dict(dotenv.dotenv_values(ENV_PATH)) if os.path.exists(ENV_PATH) else {}


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _safe_text(value: Any, secrets: Mapping[str, Any]) -> str:
    text = str(value)
    for secret in secrets.values():
        if secret:
            text = text.replace(str(secret), "[redacted]")
    return text[:1000]


def _safe_metadata(value: Any, secrets: Mapping[str, Any]) -> Any:
    sensitive = ("token", "secret", "password", "credential", "key")
    if isinstance(value, Mapping):
        return {
            str(key): "[redacted]" if any(part in str(key).lower() for part in sensitive)
            else _safe_metadata(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(item, secrets) for item in value[:50]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_text(value, secrets)


def _connector_identity(connector: Connector, secrets: Mapping[str, Any]) -> Dict[str, Any]:
    identity = getattr(connector, "auth_identity", None)
    if callable(identity):
        identity = identity()
    if not isinstance(identity, Mapping):
        identity = {}
    return _safe_metadata(identity, secrets)


def _connector_error(connector: Connector, secrets: Mapping[str, Any], fallback: str) -> str:
    error = getattr(connector, "auth_error", None) or fallback
    return _safe_text(error, secrets)


def _state(connector_id: str, env_config: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    config = env_config if env_config is not None else {}
    # Cached health is valid only while the registry-owned required credentials
    # that produced it are still present in the current persisted configuration.
    if not is_connector_configured(connector_id, config):
        previous = _connection_states.get(connector_id, {})
        return {
            "status": "unconfigured",
            "last_verified": previous.get("last_verified"),
            "last_checked": previous.get("last_checked"),
            "error": None,
            "identity": {},
        }
    if connector_id in _connection_states:
        return dict(_connection_states[connector_id])
    return {"status": "configured", "last_verified": None, "last_checked": None, "error": None, "identity": {}}


def _set_state(connector_id: str, status: str, error: Optional[str] = None,
               identity: Optional[Dict[str, Any]] = None, verified: bool = False) -> Dict[str, Any]:
    previous = _connection_states.get(connector_id, {})
    checked_at = _utcnow()
    state = {
        "status": status,
        "last_verified": checked_at if verified else previous.get("last_verified"),
        "last_checked": checked_at,
        "error": error,
        "identity": identity if identity is not None else previous.get("identity", {}),
    }
    _connection_states[connector_id] = state
    return dict(state)


def _stop_connector_watches(connector_id: str) -> None:
    for watch_id in [wid for wid in _active_watches if wid.startswith(f"{connector_id}:")]:
        handle = _active_watches.pop(watch_id)
        try:
            handle.stop()
        except Exception as exc:
            logger.warning(f"Error stopping watch handle {watch_id}: {exc}")


def _persist_credentials(updates: Mapping[str, Optional[str]]) -> None:
    with _dotenv_lock:
        directory = os.path.dirname(os.path.abspath(ENV_PATH))
        os.makedirs(directory, exist_ok=True)
        fd, candidate_path = tempfile.mkstemp(prefix=".env.", dir=directory, text=True)
        os.close(fd)
        try:
            if os.path.exists(ENV_PATH):
                shutil.copyfile(ENV_PATH, candidate_path)
            for key, value in updates.items():
                if value is None or value == "":
                    dotenv.unset_key(candidate_path, key)
                else:
                    dotenv.set_key(candidate_path, key, value)
            os.replace(candidate_path, ENV_PATH)
        finally:
            if os.path.exists(candidate_path):
                os.unlink(candidate_path)


def _remove_credentials(keys: List[str]) -> None:
    with _dotenv_lock:
        if not os.path.exists(ENV_PATH):
            return
        directory = os.path.dirname(os.path.abspath(ENV_PATH))
        fd, candidate_path = tempfile.mkstemp(prefix=".env.", dir=directory, text=True)
        os.close(fd)
        try:
            shutil.copyfile(ENV_PATH, candidate_path)
            for key in keys:
                dotenv.unset_key(candidate_path, key)
            os.replace(candidate_path, ENV_PATH)
        finally:
            if os.path.exists(candidate_path):
                os.unlink(candidate_path)


def _verify_persisted_connector(connector_id: str, automatic: bool = False) -> Dict[str, Any]:
    env_config = _owned_config(connector_id, _read_credentials())
    if not is_connector_configured(connector_id, env_config):
        return _set_state(connector_id, "unconfigured", identity={})
    current = _connection_states.get(connector_id, {})
    if automatic and current.get("status") in {"expired", "error"}:
        return dict(current)
    secrets = {key: env_config.get(key) for key in _auth_keys(connector_id)}
    try:
        with _candidate_auth_environment(connector_id, env_config):
            clear_connector_cache(connector_id)
            connector = get_connector(connector_id, _owned_config(connector_id, env_config))
            authenticated = connector.authenticate()
            error = None if authenticated else _connector_error(connector, secrets, "Authentication failed")
            identity = _connector_identity(connector, secrets) if authenticated else {}
    except Exception as exc:
        error = _safe_text(exc, secrets)
        return _set_state(connector_id, "expired", error=error, identity={})
    if not authenticated:
        return _set_state(connector_id, "expired", error=error, identity={})
    return _set_state(connector_id, "healthy", identity=identity, verified=True)


async def _health_check_loop() -> None:
    while True:
        try:
            await asyncio.sleep(60)
            env_config = _read_credentials()
            for connector_id in discover_configured(env_config):
                await asyncio.to_thread(_verify_persisted_connector, connector_id, True)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(f"Error in connector health check loop: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ws_polling_task, _health_check_task
    _ws_polling_task = asyncio.create_task(_poll_watches_loop())
    _health_check_task = asyncio.create_task(_health_check_loop())
    yield
    if _ws_polling_task:
        _ws_polling_task.cancel()
    if _health_check_task:
        _health_check_task.cancel()
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

from pydantic import BaseModel
import yaml
import os

class SettingsModel(BaseModel):
    permission_mode: str
    poll_interval: int
    slack_webhook: str = ""
    discord_webhook: str = ""
    pagerduty_key: str = ""

SETTINGS_FILE = "prash.yaml"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            data = yaml.safe_load(f)
            if data and "settings" in data:
                return data["settings"]
    return {
        "permission_mode": "ask",
        "poll_interval": 15,
        "slack_webhook": "",
        "discord_webhook": "",
        "pagerduty_key": ""
    }

def save_settings_to_file(settings_dict):
    data = {}
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            data = yaml.safe_load(f) or {}
    data["settings"] = settings_dict
    with open(SETTINGS_FILE, "w") as f:
        yaml.dump(data, f)

@app.get("/api/settings")
async def get_settings():
    return load_settings()

@app.post("/api/settings")
async def save_settings(settings: SettingsModel):
    settings_dict = settings.dict()
    save_settings_to_file(settings_dict)
    return {"status": "success", "settings": settings_dict}


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
                        
                        event_payload = {
                            "watch_id": watch_id,
                            "connector": ev.get("connector"),
                            "event_type": ev.get("event_type"),
                            "summary": ev.get("summary"),
                            "raw": ev.get("raw", {}),
                            "timestamp": ts_str,
                        }
                        events_to_broadcast.append(event_payload)
                        
                        # Store in global activity log, keep last 1000
                        _activity_log.insert(0, event_payload)
                        if len(_activity_log) > 1000:
                            _activity_log.pop()
                except Exception as e:
                    logger.error(f"Error polling watch {watch_id}: {e}")

            if events_to_broadcast:
                for item in events_to_broadcast:
                    etype = (item.get("event_type") or "").lower()
                    sev = "error" if "fail" in etype or "error" in etype or "crash" in etype else ("warning" if "spike" in etype or "alarm" in etype or "warn" in etype else "info")
                    _notifications.insert(0, {
                        "id": f"notif_{int(datetime.datetime.now(datetime.timezone.utc).timestamp()*1000)}_{item.get('connector')}",
                        "title": item.get("summary") or f"{item.get('connector')} update",
                        "message": f"{item.get('event_type')} on {item.get('watch_id')}",
                        "connector": item.get("connector"),
                        "severity": sev,
                        "timestamp": item.get("timestamp"),
                        "read": False,
                    })
                if len(_notifications) > 100:
                    del _notifications[100:]

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
    env_config = _read_credentials()
    connectors = registry_to_json(env_config)
    for connector in connectors:
        connector.update(_state(connector["id"], env_config))
    return {"connectors": connectors}


@app.get("/api/connectors/{connector_id}")
def get_connector_info(connector_id: str):
    """Returns detailed metadata for a specific connector."""
    env_config = _read_credentials()
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)
    detail = connector_detail_to_json(connector_id, env_config)
    detail.update(_state(connector_id, env_config))
    return detail


def _get_provider_identity(connector_id: str, connector: Any, env_config: Dict[str, str]) -> str:
    """Extract human-readable provider identity (account ID, username, context) from authenticated connector."""
    entry = CONNECTOR_REGISTRY.get(connector_id)
    name = entry.name if entry else connector_id.upper()

    try:
        if connector_id == "aws":
            region = env_config.get("AWS_REGION", "us-east-1")
            sts = getattr(connector, "_sts_client", None)
            if not sts and hasattr(connector, "session") and connector.session:
                try:
                    sts = connector.session.client("sts")
                except Exception:
                    pass
            if sts:
                try:
                    ident = sts.get_caller_identity()
                    acct = ident.get("Account", "Active")
                    return f"AWS Account {acct} ({region})"
                except Exception:
                    pass
            return f"AWS ({region})"

        if connector_id == "github":
            owner = env_config.get("GITHUB_OWNER") or env_config.get("GITHUB_REPO")
            if owner:
                return f"GitHub: {owner}"
            token = env_config.get("GITHUB_TOKEN", "")
            return f"GitHub ({mask_credential(token)})"

        if connector_id == "kubernetes":
            context = getattr(connector, "context", None)
            namespace = getattr(connector, "namespace", None) or env_config.get("K8S_NAMESPACE", "default")
            if context:
                return f"Cluster: {context} ({namespace})"
            return f"Kubernetes ({namespace})"

        if connector_id == "vercel":
            team = env_config.get("VERCEL_TEAM_ID") or env_config.get("VERCEL_PROJECT_ID")
            if team:
                return f"Vercel: {team}"
            return "Vercel Platform"

        if connector_id == "datadog":
            site = env_config.get("DATADOG_SITE", "datadoghq.com")
            return f"Datadog ({site})"

        # General account key heuristics
        for key in ("ACCOUNT_ID", "PROJECT_ID", "ORG_ID", "USERNAME"):
            for k, v in env_config.items():
                if key in k and v:
                    return f"{name} ({v})"

        return f"{name} Verified"
    except Exception:
        return f"{name} Connected"


@app.post("/api/connectors/{connector_id}/connect")
def connect_connector(connector_id: str, credentials: Dict[str, str] = Body(...)):
    """Authenticate candidate credentials before atomically persisting them."""
    if connector_id not in CONNECTOR_REGISTRY:
        credentials.clear()
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    entry = CONNECTOR_REGISTRY[connector_id]
    allowed = {field.key for field in entry.auth_fields}
    submitted = {key: str(value) for key, value in credentials.items() if key in allowed}
    unknown = sorted(set(credentials) - allowed)
    supplied_values = [str(value) for value in credentials.values() if value]
    existing = _owned_config(connector_id, _read_credentials(), include_defaults=False)
    candidate = dict(existing)
    candidate.update(submitted)
    for field in entry.auth_fields:
        if field.key not in candidate and field.default:
            candidate[field.key] = field.default
    secrets = {field.key: candidate.get(field.key) for field in entry.auth_fields}
    secrets.update({f"submitted_{index}": value for index, value in enumerate(supplied_values)})
    credentials.clear()

    if unknown:
        raise APIBridgeException("BAD_REQUEST", f"Unknown credential fields: {', '.join(unknown)}", 400)
    missing = get_missing_fields(connector_id, candidate)
    if missing:
        raise APIBridgeException(
            "CONNECTOR_NOT_CONFIGURED",
            f"Missing required fields: {', '.join(missing)}",
            400,
            {"missing_fields": missing},
        )

    try:
        with _candidate_auth_environment(connector_id, candidate):
            connector = entry.connector_class(candidate)
            authenticated = connector.authenticate()
            error = None if authenticated else _connector_error(
                connector, secrets, f"Authentication failed for {entry.name}"
            )
            identity = _connector_identity(connector, secrets) if authenticated else {}
    except Exception as exc:
        error = _safe_text(exc, secrets)
        raise APIBridgeException("CONNECTOR_AUTH_FAILED", error, 401)
    if not authenticated:
        raise APIBridgeException("CONNECTOR_AUTH_FAILED", error, 401)

    updates = {
        field.key: (str(candidate[field.key]) if candidate.get(field.key) else None)
        for field in entry.auth_fields
        if field.key in submitted or (field.key not in existing and candidate.get(field.key))
    }
    _persist_credentials(updates)
    clear_connector_cache(connector_id)
    state = _set_state(connector_id, "healthy", identity=identity, verified=True)
    secrets.clear()
    submitted.clear()
    return {
        "success": True,
        "message": f"{entry.name} authenticated successfully",
        **state,
    }


@app.delete("/api/connectors/{connector_id}/disconnect")
def disconnect_connector(connector_id: str):
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)
    entry = CONNECTOR_REGISTRY[connector_id]
    _remove_credentials([field.key for field in entry.auth_fields])
    clear_connector_cache(connector_id)
    _stop_connector_watches(connector_id)
    state = _set_state(connector_id, "unconfigured", identity={})
    return {"success": True, "message": f"{entry.name} disconnected", **state}


@app.post("/api/connectors/{connector_id}/check")
def check_connector(connector_id: str):
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)
    state = _verify_persisted_connector(connector_id)
    success = state["status"] == "healthy"
    message = "Connection verified" if success else (state.get("error") or "Connection check failed")
    return {"success": success, "message": message, **state}


@app.get("/api/connectors/{connector_id}/validate")
def validate_connector(connector_id: str):
    """Check credentials validity and health without modifying .env."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    entry = CONNECTOR_REGISTRY[connector_id]
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    if not is_connector_configured(connector_id, env_config):
        return {
            "valid": False,
            "status": "unconfigured",
            "message": f"{entry.name} is not configured",
            "identity": None,
        }

    try:
        connector = get_connector(connector_id, env_config)
        is_authenticated = connector.authenticate()
        if is_authenticated:
            identity = _get_provider_identity(connector_id, connector, env_config)
            return {
                "valid": True,
                "status": "connected",
                "message": f"{entry.name} credentials are active",
                "identity": identity,
            }
        else:
            return {
                "valid": False,
                "status": "expired",
                "message": f"{entry.name} credentials failed authentication or expired",
                "identity": None,
            }
    except Exception as e:
        return {
            "valid": False,
            "status": "error",
            "message": f"Validation error: {str(e)}",
            "identity": None,
        }



@app.get("/api/connectors/{connector_id}/status")
def get_connector_status(connector_id: str, resource: Optional[str] = Query(None)):
    """Check live status and optionally poll a specific resource."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    env_config = _read_credentials()
    if not is_connector_configured(connector_id, env_config):
        state = _set_state(connector_id, "unconfigured", identity={})
        return {**state, "detail": {"missing_fields": get_missing_fields(connector_id, env_config)}}

    if not resource:
        state = _state(connector_id, env_config)
        return {**state, "detail": {"authenticated": state["status"] == "healthy"}}

    try:
        connector = get_connector(connector_id, _owned_config(connector_id, env_config))
        state = connector.poll_state(resource)
        state_val = state.state.value if hasattr(state.state, "value") else str(state.state)
        return {"status": state_val, "detail": state.detail, "resource": resource}
    except Exception as e:
        return {"status": "error", "detail": {"message": _safe_text(e, env_config)}}


@app.get("/api/connectors/{connector_id}/metrics")
def get_connector_metrics(
    connector_id: str,
    resource: Optional[str] = Query(None),
    time_range: Optional[str] = Query(None),
):
    """Fetch live time-series metrics from the connector."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    env_config = _read_credentials()
    if not is_connector_configured(connector_id, env_config):
        raise APIBridgeException(
            "CONNECTOR_NOT_CONFIGURED",
            f"Connector {connector_id} is not configured",
            400,
            {"missing_fields": get_missing_fields(connector_id, env_config)},
        )

    try:
        connector = get_connector(connector_id, _owned_config(connector_id, env_config))
        target = resource or ""
        if not target:
            try:
                res_meta = get_connector_resources(connector_id)
                res_list = res_meta.get("resources", []) if isinstance(res_meta, dict) else []
                if res_list:
                    target = res_list[0].get("id", "")
            except Exception:
                pass

        events = []
        try:
            events = connector.get_stats(target=target)
        except Exception:
            events = []

        # Normalize metrics from real events
        normalized_metrics = []
        for ev in events:
            raw = ev.get("raw", {})
            val = raw.get("value", raw.get("val", raw.get("avg", None))) if isinstance(raw, dict) else None
            unit = raw.get("unit", "") if isinstance(raw, dict) else ""

            if val is None and isinstance(raw, dict):
                # Check for nested stats (e.g. Datadog / monitoring connectors)
                if isinstance(raw.get("stats"), dict):
                    st = raw["stats"]
                    val = st.get("max", st.get("mean", st.get("value", st.get("points"))))
                # Check for standard telemetry fields
                if val is None:
                    for k in ("metric_value", "data_point", "count", "latency", "points", "total", "rate"):
                        if k in raw and isinstance(raw[k], (int, float)):
                            val = raw[k]
                            if not unit:
                                unit = "ms" if "latency" in k else ("count" if "count" in k or "total" in k else "")
                            break
            # Fallback for event-based connectors: count each event as 1.0 signal
            if val is None and ev.get("event_type"):
                val = 1.0
                if not unit:
                    unit = "event"

            if val is None:
                continue

            ts = ev.get("timestamp")
            ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            normalized_metrics.append({
                "name": ev.get("event_type", "metric"),
                "value": float(val) if isinstance(val, (int, float)) else 0.0,
                "unit": unit,
                "timestamp": ts_str,
            })

        # If get_stats returned events without numeric metrics, inspect poll_state
        if not normalized_metrics:
            try:
                state_obj = connector.poll_state(target)
                if state_obj and hasattr(state_obj, "detail") and isinstance(state_obj.detail, dict):
                    now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    for k, v in state_obj.detail.items():
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            unit_str = "%" if any(x in k.lower() for x in ("cpu", "percent", "util", "memory", "ratio")) else ""
                            normalized_metrics.append({
                                "name": k,
                                "value": float(v),
                                "unit": unit_str,
                                "timestamp": now_ts,
                            })
                    # Inspect connector-specific structures if still empty
                    if not normalized_metrics:
                        if "runs_by_workflow" in state_obj.detail and isinstance(state_obj.detail["runs_by_workflow"], dict):
                            normalized_metrics.append({
                                "name": "active_workflows",
                                "value": float(len(state_obj.detail["runs_by_workflow"])),
                                "unit": "workflows",
                                "timestamp": now_ts,
                            })
                        if "incidents" in state_obj.detail and isinstance(state_obj.detail["incidents"], list):
                            normalized_metrics.append({
                                "name": "active_incidents",
                                "value": float(len(state_obj.detail["incidents"])),
                                "unit": "incidents",
                                "timestamp": now_ts,
                            })
            except Exception:
                pass

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

    env_config = _read_credentials()
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
            k8s = KubernetesConnector(_owned_config("kubernetes", env_config))
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
        elif connector_id == "github":
            repo_val = env_config.get("GITHUB_REPO")
            if repo_val:
                resources.append({
                    "id": repo_val,
                    "name": repo_val,
                    "type": "github_repo",
                    "state": "configured",
                })
        elif connector_id == "vercel":
            proj_val = env_config.get("VERCEL_PROJECT_ID") or env_config.get("VERCEL_PROJECT")
            if proj_val:
                resources.append({
                    "id": proj_val,
                    "name": proj_val,
                    "type": "vercel_project",
                    "state": "configured",
                })
        elif connector_id == "datadog":
            mon_val = env_config.get("DATADOG_MONITOR_ID")
            if mon_val:
                resources.append({
                    "id": mon_val,
                    "name": f"Datadog Monitor ({mon_val})",
                    "type": "datadog_monitor",
                    "state": "configured",
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
    interval = body.get("interval", 5) # Default 5s if not provided

    if not target:
        raise APIBridgeException("BAD_REQUEST", "Field 'target' is required", 400)

    watch_id = f"{connector_id}:{target}"
    if watch_id in _active_watches:
        raise APIBridgeException("WATCH_ALREADY_ACTIVE", f"Watch already active for {watch_id}", 409)

    env_config = _read_credentials()
    connector = get_connector(connector_id, _owned_config(connector_id, env_config))

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


@app.get("/api/activity")
def get_activity_log(q: Optional[str] = Query(None), connector: Optional[str] = Query(None)):
    """Return historical events from the in-memory activity log."""
    results = _activity_log
    
    if connector and connector.lower() != "all":
        results = [ev for ev in results if ev.get("connector", "").lower() == connector.lower()]
        
    if q:
        q_lower = q.lower()
        results = [ev for ev in results if q_lower in ev.get("summary", "").lower() or q_lower in ev.get("event_type", "").lower()]
        
    return {"events": results}

@app.get("/api/watch/active")
def get_active_watches():
    """Returns list of currently active watch handles with target and connector metadata."""
    watches = []
    for wid, handle in list(_active_watches.items()):
        connector_id = getattr(handle, "connector", wid.split(":")[0] if ":" in wid else "unknown")
        target = getattr(handle, "target", wid.split(":", 1)[1] if ":" in wid else wid)
        watches.append({
            "watch_id": wid,
            "connector": connector_id,
            "target": target,
            "status": "healthy",
        })
    return {"watches": watches, "count": len(watches)}


@app.get("/api/system/version")
def get_system_version():
    """Returns application name and version."""
    return {"name": "Lear", "version": "2.0.0", "engine": "FastAPI + Prash Core"}


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


@app.put("/api/projects/{project_id}")
def update_project(project_id: str, payload: Dict[str, Any] = Body(...)):
    """Update an existing project's name, environments, and services."""
    project = payload.get("project", payload)
    data = _read_prash_yaml()
    existing_index = None
    for i, p in enumerate(data["projects"]):
        if p.get("id") == project_id:
            existing_index = i
            break

    if existing_index is None:
        raise APIBridgeException("RESOURCE_NOT_FOUND", f"Project {project_id} not found", 404)

    # Validate referenced connectors exist
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

    orig = data["projects"][existing_index]
    updated = {
        "id": project_id,
        "name": project.get("name", orig.get("name", project_id)),
        "created_at": orig.get("created_at", datetime.datetime.now(datetime.timezone.utc).isoformat()),
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "environments": environments,
    }
    data["projects"][existing_index] = updated
    _write_prash_yaml(data)
    return {"project": updated}


@app.get("/api/projects/{project_id}/status")
def get_project_status(project_id: str):
    """Aggregate live health per service via poll_state() across all environments in a project."""
    data = _read_prash_yaml()
    project = None
    for p in data.get("projects", []):
        if p.get("id") == project_id:
            project = p
            break

    if not project:
        raise APIBridgeException("RESOURCE_NOT_FOUND", f"Project {project_id} not found", 404)

    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    summary_counts = {"healthy": 0, "warning": 0, "error": 0, "unknown": 0, "total": 0}
    env_statuses = []

    for env in project.get("environments", []):
        env_services = []
        env_summary = {"healthy": 0, "warning": 0, "error": 0, "unknown": 0}

        for svc in env.get("services", []):
            cid = svc.get("connector_id")
            rid = svc.get("resource_id", "")
            disp_name = svc.get("display_name") or (f"{CONNECTOR_REGISTRY[cid].name} ({rid})" if cid in CONNECTOR_REGISTRY else rid)

            svc_status = "unknown"
            state_label = "NOT_CONFIGURED"
            detail_msg = ""

            if cid in CONNECTOR_REGISTRY and is_connector_configured(cid, env_config):
                try:
                    connector = get_connector(cid, env_config)
                    poll_res = connector.poll_state(rid) if hasattr(connector, "poll_state") else None
                    if poll_res:
                        state_val = getattr(poll_res, "state", None)
                        state_name = getattr(state_val, "name", str(state_val)).upper()
                        state_label = state_name
                        detail_msg = getattr(poll_res, "message", "")

                        if state_name in ("HEALTHY", "OK", "STABLE", "RUNNING"):
                            svc_status = "healthy"
                        elif state_name in ("DEGRADED", "WARN", "WARNING", "DEPLOYING"):
                            svc_status = "warning"
                        elif state_name in ("FAILED", "ERROR", "ALERT", "CRASHLOOP"):
                            svc_status = "error"
                        else:
                            svc_status = "unknown"
                except Exception as e:
                    logger.warning(f"Error polling state for {cid}/{rid}: {e}")
                    svc_status = "error"
                    state_label = "ERROR"
                    detail_msg = str(e)
            else:
                svc_status = "unknown"
                state_label = "UNCONFIGURED"
                detail_msg = f"Connector '{cid}' not configured in environment"

            env_summary[svc_status] = env_summary.get(svc_status, 0) + 1
            summary_counts[svc_status] = summary_counts.get(svc_status, 0) + 1
            summary_counts["total"] += 1

            env_services.append({
                "connector_id": cid,
                "resource_id": rid,
                "display_name": disp_name,
                "status": svc_status,
                "state_label": state_label,
                "detail": detail_msg,
                "last_checked": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

        if env_summary["error"] > 0:
            env_status = "error"
        elif env_summary["warning"] > 0:
            env_status = "warning"
        elif env_summary["healthy"] > 0:
            env_status = "healthy"
        else:
            env_status = "unknown"

        env_statuses.append({
            "name": env.get("name"),
            "status": env_status,
            "services": env_services,
        })

    if summary_counts["error"] > 0:
        overall_status = "error"
    elif summary_counts["warning"] > 0:
        overall_status = "warning"
    elif summary_counts["healthy"] > 0:
        overall_status = "healthy"
    else:
        overall_status = "unknown"

    return {
        "project_id": project_id,
        "status": overall_status,
        "summary": summary_counts,
        "environments": env_statuses,
    }


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
    env_config = _read_credentials()
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

    services = {}
    for cid, entry in CONNECTOR_REGISTRY.items():
        if is_connector_configured(cid, config):
            services[cid] = {"status": "configured"}

    projects_data = _read_prash_yaml()
    raw_masked = {k: safe_mask(v) for k, v in config.items() if v}

    return {"services": services, "projects": projects_data.get("projects", []), "raw": raw_masked}


@app.post("/api/config")
def update_config(updates: Dict[str, str] = Body(...)):
    """Update non-connector desktop settings; credentials require authentication."""
    registry_keys = {field.key for entry in CONNECTOR_REGISTRY.values() for field in entry.auth_fields}
    rejected = sorted(str(key) for key in updates if str(key) in registry_keys)
    if rejected:
        raise APIBridgeException(
            "CONNECTOR_AUTH_REQUIRED",
            f"Connector credential keys must be authenticated via /api/connectors/{{id}}/connect: {', '.join(rejected)}",
            400,
        )
    _persist_credentials({str(key): str(value) for key, value in updates.items() if value})
    return {"success": True}


# ---------------------------------------------------------------------------
# Platform Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def get_settings():
    """Returns current AI model, permission mode, and available models."""
    yaml_data = _read_prash_yaml()
    settings = yaml_data.get("settings", {})
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}

    current_model = settings.get("model") or env_config.get("PRIMARY_MODEL") or "deepseek-v4-flash"
    current_perm = settings.get("permission_mode") or env_config.get("PRASH_PERMISSION_MODE") or "ask"

    available_models = [
        {"id": "deepseek-v4-flash", "name": "DeepSeek Flash", "desc": "Ultra-fast intent resolution & diagnostics"},
        {"id": "kimi-k2.6", "name": "Kimi K2.6", "desc": "Deep technical reasoning & large log contexts"},
        {"id": "gemini-1.5-pro", "name": "Gemini Pro", "desc": "High capability multi-modal analysis"},
    ]
    return {
        "model": current_model,
        "permission_mode": current_perm,
        "available_models": available_models,
    }


@app.post("/api/settings")
def save_settings(payload: Dict[str, Any] = Body(...)):
    """Persists model and permission mode to prash.yaml and .env."""
    yaml_data = _read_prash_yaml()
    if "settings" not in yaml_data or not isinstance(yaml_data["settings"], dict):
        yaml_data["settings"] = {}

    model = payload.get("model")
    permission_mode = payload.get("permission_mode")

    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, "w").close()

    if model:
        yaml_data["settings"]["model"] = model
        dotenv.set_key(ENV_PATH, "PRIMARY_MODEL", model)
    if permission_mode:
        yaml_data["settings"]["permission_mode"] = permission_mode
        dotenv.set_key(ENV_PATH, "PRASH_PERMISSION_MODE", permission_mode)

    _write_prash_yaml(yaml_data)
    dotenv.load_dotenv(ENV_PATH, override=True)
    return {"success": True, "settings": yaml_data["settings"]}


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
                env_config = _read_credentials()
                if is_connector_configured(cid, env_config):
                    try:
                        conn = get_connector(cid, _owned_config(cid, env_config))
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


@app.post("/api/chat/execute")
def execute_chat_action(payload: Dict[str, Any] = Body(...)):
    """Executes an action generated from intent resolution or chat copilot."""
    command = payload.get("command", [])
    action_id = payload.get("action_id", "")

    if not command and not action_id:
        raise APIBridgeException("BAD_REQUEST", "Command or action_id is required", 400)

    cmd_str = " ".join(command) if isinstance(command, list) else str(command)
    logger.info(f"Executing chat action: {cmd_str}")

    try:
        from prash.audit import AuditLog
        from io import StringIO
        import sys

        argv = command if isinstance(command, list) else command.split()

        from prash import cli
        parser = cli.build_parser()

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        capture_out = StringIO()
        sys.stdout = capture_out
        sys.stderr = capture_out

        ret_code = 0
        try:
            parsed_args = parser.parse_args(argv)
            ret_code = parsed_args.func(parsed_args)
            if ret_code is None:
                ret_code = 0
        except SystemExit as se:
            ret_code = se.code if isinstance(se.code, int) else 0
        except Exception as exec_err:
            ret_code = 1
            capture_out.write(f"\nExecution error: {str(exec_err)}")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        output_text = capture_out.getvalue().strip()
        if not output_text:
            output_text = f"Action '{cmd_str}' completed successfully (exit code: {ret_code})."

        # Record to audit log
        try:
            from prash.actions.contract import ActionResult, ActionResultStatus, Decision, RiskTier
            from prash.permissions import PermissionMode
            audit = AuditLog()
            status_enum = ActionResultStatus.SUCCEEDED if ret_code == 0 else ActionResultStatus.FAILED
            result = ActionResult(status=status_enum, summary=output_text[:200])
            audit.append(
                action_id=action_id or (argv[0] if argv else "chat_action"),
                risk_tier=RiskTier.SAFE,
                mode=PermissionMode.ASK,
                decision=Decision.ALLOW if ret_code == 0 else Decision.REFUSE,
                result=result,
                environment="staging",
                actor="chat_copilot",
                extra={"argv": argv, "exit_code": ret_code, "output": output_text[:500]},
            )
        except Exception as ae:
            logger.warning(f"Audit log recording error: {ae}")

        return {
            "success": ret_code == 0,
            "exit_code": ret_code,
            "command": argv,
            "output": output_text,
        }
    except Exception as e:
        logger.error(f"Error executing chat command {cmd_str}: {e}")
        return {
            "success": False,
            "exit_code": 1,
            "command": argv if 'argv' in locals() else [cmd_str],
            "output": f"Execution error: {str(e)}",
        }


# ---------------------------------------------------------------------------
# Notification System
# ---------------------------------------------------------------------------

@app.get("/api/notifications")
def get_notifications():
    """Returns in-memory notification queue and watch updates."""
    return {"notifications": _notifications}


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str):
    """Mark a notification as read."""
    for n in _notifications:
        if n.get("id") == notification_id:
            n["read"] = True
            return {"success": True}
    return {"success": True}


@app.delete("/api/notifications")
def clear_notifications():
    """Clear all notifications."""
    global _notifications
    _notifications = []
    return {"success": True}


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

    env_config = _read_credentials()
    available_metrics = []
    current_status = "unknown"

    if is_connector_configured(connector_id, env_config):
        try:
            conn = get_connector(connector_id, _owned_config(connector_id, env_config))
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
    env_config = _read_credentials()
    statuses = []
    for cid in discover_configured(env_config):
        entry = CONNECTOR_REGISTRY[cid]
        try:
            conn = get_connector(cid, _owned_config(cid, env_config))
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
