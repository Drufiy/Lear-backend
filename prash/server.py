"""Prash Desktop API Server — Dynamic Backend API Bridge.

Exposes uniform REST and WebSocket endpoints connecting the desktop application
to all 13 backend connectors.
All data returned is 100% dynamic: zero hardcoded metrics, zero synthetic latency strings,
zero fallback numbers.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
import datetime
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
from typing import Any, Dict, Iterator, List, Mapping, Optional, Set

import dotenv
import yaml
from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from prash.connector_registry import (
    CONNECTOR_REGISTRY,
    clear_connector_cache,
    connector_detail_to_json,
    discover_configured,
    get_connector,
    get_missing_fields,
    is_connector_configured,
    registry_to_json,
    safe_mask,
)
from prash.connectors.base import Connector, ConnectorEvent, ConnectorState, ResourceState, WatchHandle
from prash.widget_generator import (
    delete_widget_layout_from_yaml,
    load_widget_layout_from_yaml,
    save_widget_layout_to_yaml,
    synthesize_widgets,
    validate_widget_config,
)

logger = logging.getLogger(__name__)

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
YAML_PATH = os.path.join(os.path.dirname(__file__), "..", "prash.yaml")
NOTIFICATIONS_PATH = os.path.join(os.path.dirname(__file__), "..", ".prash", "notifications.json")

dotenv.load_dotenv(ENV_PATH, override=True)


def _load_persisted_notifications() -> List[Dict[str, Any]]:
    if not os.path.exists(NOTIFICATIONS_PATH):
        return []
    try:
        with open(NOTIFICATIONS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "notifications" in data and isinstance(data["notifications"], list):
                return data["notifications"]
            return []
    except Exception as e:
        logger.warning(f"Error loading persisted notifications: {e}")
        return []


def _save_notifications_to_disk() -> None:
    try:
        os.makedirs(os.path.dirname(NOTIFICATIONS_PATH), exist_ok=True)
        with open(NOTIFICATIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(_notifications[:100], f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to persist notifications to disk: {e}")


def _read_prash_yaml() -> Dict[str, Any]:
    if not os.path.exists(YAML_PATH):
        return {"projects": [], "active_watches": []}
    try:
        with open(YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, dict):
                if "projects" not in data:
                    data["projects"] = []
                if "active_watches" not in data:
                    data["active_watches"] = []
                return data
            return {"projects": [], "active_watches": []}
    except Exception as e:
        logger.error(f"Error reading prash.yaml: {e}")
        return {"projects": [], "active_watches": []}


def _write_prash_yaml(data: Dict[str, Any]) -> None:
    with open(YAML_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)


def _persist_watch_to_yaml(connector_id: str, target: str, interval: int):
    try:
        data = _read_prash_yaml()
        watches = data.get("active_watches", [])
        if not isinstance(watches, list):
            watches = []
        wid = f"{connector_id}:{target}"
        watches = [w for w in watches if isinstance(w, dict) and w.get("watch_id") != wid]
        watches.append({
            "watch_id": wid,
            "connector": connector_id,
            "target": target,
            "interval": interval,
        })
        data["active_watches"] = watches
        _write_prash_yaml(data)
    except Exception as e:
        logger.warning(f"Error persisting watch to prash.yaml: {e}")


def _remove_watch_from_yaml(watch_id: str):
    try:
        data = _read_prash_yaml()
        watches = data.get("active_watches", [])
        if not isinstance(watches, list):
            return
        new_watches = [w for w in watches if isinstance(w, dict) and w.get("watch_id") != watch_id]
        if len(new_watches) != len(watches):
            data["active_watches"] = new_watches
            _write_prash_yaml(data)
    except Exception as e:
        logger.warning(f"Error removing watch from prash.yaml: {e}")


# In-memory watch handles, metadata, paused state, and active websocket clients
_active_watches: Dict[str, WatchHandle] = {}
_watch_metadata: Dict[str, Dict[str, Any]] = {}
_paused_watches: Set[str] = set()
_ws_clients: Set[WebSocket] = set()
_ws_polling_task: Optional[asyncio.Task] = None
_notifications: List[Dict[str, Any]] = []

# Global in-memory activity log for Task 14
_activity_log: List[Dict[str, Any]] = []

# 10s TTL cache for dashboard summary
_dashboard_summary_cache: Dict[str, Any] = {
    "timestamp": 0.0,
    "data": None,
}

# Connection-lifecycle cache (Task 05): restored 2026-09-14 after being
# silently dropped from a server.py rewrite -- see prash/server.py's git
# history at commit 7424044 for the original. Tracks each connector's last
# known auth status ("healthy"/"expired"/"unconfigured") so /status and the
# periodic health-check loop don't re-authenticate on every poll, and so a
# credential known to be invalid isn't retried on every automatic check.
_connection_states: Dict[str, Dict[str, Any]] = {}
_health_check_task: Optional[asyncio.Task] = None
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
    """Expose only candidate registry values while constructing/authenticating a
    connector, restoring whatever was there (including nothing) afterward --
    so testing a new credential never leaks into or clobbers the real process
    environment (a connector's own SDK may read os.environ directly)."""
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


def _connector_error(connector: Connector, secrets: Mapping[str, Any], fallback: str) -> str:
    error = getattr(connector, "auth_error", None) or fallback
    return _safe_text(error, secrets)


def _connection_state(connector_id: str, env_config: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    config = env_config or {}
    if connector_id in _connection_states:
        return dict(_connection_states[connector_id])
    status = "configured" if is_connector_configured(connector_id, config) else "unconfigured"
    return {"status": status, "last_verified": None, "last_checked": None, "error": None, "identity": ""}


def _set_connection_state(connector_id: str, status: str, error: Optional[str] = None,
                           identity: Optional[Any] = None, verified: bool = False) -> Dict[str, Any]:
    """Every call represents one real check attempt, so last_checked always
    advances to now. last_verified is narrower -- the last time a check
    actually CONFIRMED the credential healthy -- so it only advances when
    verified=True, and otherwise carries forward whatever the last successful
    check set, surviving any number of failed checks in between."""
    previous = _connection_states.get(connector_id, {})
    now_ts = _utcnow()
    state = {
        "status": status,
        "last_verified": now_ts if verified else previous.get("last_verified"),
        "last_checked": now_ts,
        "error": error,
        "identity": identity if identity is not None else previous.get("identity", ""),
    }
    _connection_states[connector_id] = state
    return dict(state)


def _clear_connection_state(connector_id: str) -> Dict[str, Any]:
    """Drop any cached state entirely -- used when a connector becomes
    unconfigured (disconnected, or credentials found missing), so
    last_verified/identity read as fresh-default None/{} rather than
    carrying over a stale timestamp from before the credential was removed."""
    _connection_states.pop(connector_id, None)
    return {"status": "unconfigured", "last_verified": None, "last_checked": None, "error": None, "identity": ""}


def _persist_credentials(updates: Mapping[str, Optional[str]]) -> None:
    """Atomically replace .env with `updates` applied -- a crash or concurrent
    write mid-way never leaves a half-written credentials file."""
    with _dotenv_lock:
        directory = os.path.dirname(os.path.abspath(ENV_PATH)) or "."
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
        directory = os.path.dirname(os.path.abspath(ENV_PATH)) or "."
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
    """Re-authenticate using whatever is currently persisted for this
    connector, and cache the result. `automatic=True` (the periodic health
    loop) skips connectors already known expired/errored -- retrying a
    credential already known to be bad on every tick is wasted work and,
    worse, extra failed-auth noise against the real provider."""
    env_config = _owned_config(connector_id, _read_credentials())
    if not is_connector_configured(connector_id, env_config):
        return _clear_connection_state(connector_id)
    current = _connection_states.get(connector_id, {})
    if automatic and current.get("status") in {"expired", "error"}:
        return dict(current)
    secrets = {key: env_config.get(key) for key in _auth_keys(connector_id)}
    try:
        with _candidate_auth_environment(connector_id, env_config):
            clear_connector_cache(connector_id)
            connector = get_connector(connector_id, env_config)
            authenticated = connector.authenticate()
            error = None if authenticated else _connector_error(connector, secrets, "Authentication failed")
            identity = _get_provider_identity(connector_id, connector, env_config) if authenticated else ""
    except Exception as exc:
        error = _safe_text(exc, secrets)
        # verified=False: last_verified tracks the last CONFIRMED-GOOD check,
        # not the last attempt -- a failure must never stamp it, only ever
        # preserve whatever the previous successful verification set.
        return _set_connection_state(connector_id, "expired", error=error, identity="")
    if not authenticated:
        return _set_connection_state(connector_id, "expired", error=error, identity="")
    return _set_connection_state(connector_id, "healthy", identity=identity, verified=True)


async def _health_check_loop() -> None:
    """Periodically re-verify every currently-configured connector so a
    revoked credential surfaces on its own instead of only being noticed the
    next time a user happens to hit /status."""
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
    global _ws_polling_task, _health_check_task, _notifications
    try:
        _restore_persisted_watches()
    except Exception as e:
        logger.warning(f"Error restoring persisted watches on startup: {e}")
    try:
        loaded_notifs = _load_persisted_notifications()
        if loaded_notifs:
            _notifications = loaded_notifs
    except Exception as e:
        logger.warning(f"Error loading persisted notifications on startup: {e}")
    _ws_polling_task = asyncio.create_task(_poll_watches_loop())
    _health_check_task = asyncio.create_task(_health_check_loop())
    yield
    if _ws_polling_task:
        _ws_polling_task.cancel()
    if _health_check_task:
        _health_check_task.cancel()
    for handle in list(_active_watches.values()):
        try:
            handle.stop()
        except Exception:
            pass
    _active_watches.clear()
    _watch_metadata.clear()
    _paused_watches.clear()


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
    """Polls active watch handles according to per-handle interval cadence and pushes real events."""
    while True:
        try:
            await asyncio.sleep(1)
            if not _active_watches:
                continue

            now = time.time()
            events_to_broadcast: List[Dict[str, Any]] = []

            for watch_id, handle in list(_active_watches.items()):
                if watch_id in _paused_watches:
                    continue

                meta = _watch_metadata.get(watch_id, {})
                interval = meta.get("interval", getattr(handle, "interval", 5))
                last_poll = meta.get("last_poll_time", 0.0)

                # Honor per-handle interval
                if now - last_poll < interval:
                    continue

                meta["last_poll_time"] = now

                try:
                    new_events = handle.poll()
                    # If recovered from failure, restore healthy status
                    if meta.get("consecutive_failures", 0) > 0:
                        meta["consecutive_failures"] = 0
                        meta["status"] = "healthy"
                        meta["last_error"] = None
                        events_to_broadcast.append({
                            "watch_id": watch_id,
                            "connector": meta.get("connector", getattr(handle, "connector", "unknown")),
                            "event_type": "watch_recovered",
                            "summary": f"Watch connection recovered for {watch_id}",
                            "raw": {"status": "healthy"},
                            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        })

                    for ev in new_events:
                        ts = ev.get("timestamp")
                        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                        
                        event_payload = {
                            "watch_id": watch_id,
                            "connector": ev.get("connector", meta.get("connector")),
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
                    fails = meta.get("consecutive_failures", 0) + 1
                    meta["consecutive_failures"] = fails
                    meta["last_error"] = str(e)
                    prev_status = meta.get("status", "healthy")
                    new_status = "error" if fails >= 3 else "degraded"
                    meta["status"] = new_status

                    if prev_status != new_status:
                        events_to_broadcast.append({
                            "watch_id": watch_id,
                            "connector": meta.get("connector", getattr(handle, "connector", "unknown")),
                            "event_type": f"watch_{new_status}",
                            "summary": f"Watch {watch_id} {new_status}: {str(e)}",
                            "raw": {"status": new_status, "error": str(e), "failures": fails},
                            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        })

            if events_to_broadcast:
                for item in events_to_broadcast:
                    etype = (item.get("event_type") or "").lower()
                    sev = "error" if "fail" in etype or "error" in etype or "crash" in etype else ("warning" if "spike" in etype or "alarm" in etype or "warn" in etype or "degraded" in etype else "info")
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
                _save_notifications_to_disk()

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
    """Returns all registered connectors with live configuration status.

    status stays registry_to_json's own configured/unconfigured (not the
    richer connection-lifecycle status) -- last_verified/identity come from
    the connection-state cache, but a connector whose credentials are
    literally absent from .env must never read as anything but unconfigured
    here, regardless of a stale cached "healthy" from an earlier session."""
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    connectors = registry_to_json(env_config)
    for c in connectors:
        state = _connection_state(c["id"], env_config)
        c["last_verified"] = state["last_verified"]
        c["identity"] = state["identity"] if c["status"] == "configured" else ""
    return {"connectors": connectors}


@app.get("/api/connectors/{connector_id}")
def get_connector_info(connector_id: str):
    """Returns detailed metadata for a specific connector. See list_connectors
    for why status is left to connector_detail_to_json's own computation."""
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)
    info = connector_detail_to_json(connector_id, env_config)
    state = _connection_state(connector_id, env_config)
    info["last_verified"] = state["last_verified"]
    info["identity"] = state["identity"] if info["status"] == "configured" else ""
    return info


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
            return f"GitHub ({safe_mask(token)})"

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
    """Authenticate candidate credentials BEFORE persisting them, atomically.

    Restored 2026-09-14 (see the connection-state cache comment above) after
    this endpoint had regressed to save-then-authenticate: a rejected
    connection attempt was left writing its (bad, possibly attacker-supplied)
    credentials to .env anyway, clobbering whatever good credentials were
    there before. Also restores rejecting credential keys the registry
    doesn't own -- previously any field name was accepted and persisted."""
    if connector_id not in CONNECTOR_REGISTRY:
        credentials.clear()
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    entry = CONNECTOR_REGISTRY[connector_id]
    allowed = {field.key for field in entry.auth_fields}
    submitted = {key: str(value) for key, value in credentials.items() if key in allowed}
    unknown = sorted(set(credentials) - allowed)
    existing = _owned_config(connector_id, _read_credentials(), include_defaults=False)
    candidate = dict(existing)
    candidate.update(submitted)
    for field in entry.auth_fields:
        if field.key not in candidate and field.default:
            candidate[field.key] = field.default
    secrets = {field.key: candidate.get(field.key) for field in entry.auth_fields}
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
            connector = get_connector(connector_id, candidate)
            authenticated = connector.authenticate()
            error = None if authenticated else _connector_error(
                connector, secrets, f"Authentication failed for {entry.name}. Provider rejected credentials."
            )
            identity = _get_provider_identity(connector_id, connector, candidate) if authenticated else None
    except Exception as exc:
        raise APIBridgeException("CONNECTOR_AUTH_FAILED", _safe_text(exc, secrets), 401)
    if not authenticated:
        # Failure does NOT touch _connection_states: the candidate was never
        # persisted, so whatever state reflects the last-persisted, actually-
        # working credential must be left exactly as it was.
        raise APIBridgeException("CONNECTOR_AUTH_FAILED", error, 401)

    updates = {
        field.key: (str(candidate[field.key]) if candidate.get(field.key) else None)
        for field in entry.auth_fields
        if field.key in submitted or (field.key not in existing and candidate.get(field.key))
    }
    _persist_credentials(updates)
    clear_connector_cache(connector_id)
    state = _set_connection_state(connector_id, "healthy", identity=identity, verified=True)
    secrets.clear()
    submitted.clear()
    return {
        "success": True,
        "message": f"{entry.name} authenticated successfully",
        **state,
    }


@app.post("/api/connectors/{connector_id}/disconnect")
@app.delete("/api/connectors/{connector_id}/disconnect")
def disconnect_connector(connector_id: str):
    """Disconnect a service by removing credentials from .env and halting active watches."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    entry = CONNECTOR_REGISTRY[connector_id]
    _remove_credentials([field.key for field in entry.auth_fields])
    clear_connector_cache(connector_id)

    stopped_watches = []
    for wid in list(_active_watches.keys()):
        if wid.startswith(f"{connector_id}:") or wid == connector_id:
            handle = _active_watches.pop(wid, None)
            if handle:
                try:
                    handle.stop()
                    stopped_watches.append(wid)
                except Exception as e:
                    logger.warning(f"Error stopping watch {wid} on disconnect: {e}")

    state = _clear_connection_state(connector_id)
    return {
        "success": True,
        "message": f"{entry.name} disconnected successfully",
        "stopped_watches": stopped_watches,
        **state,
    }


@app.post("/api/connectors/{connector_id}/check")
def check_connector(connector_id: str):
    """Force an immediate re-verification of the persisted credential,
    bypassing the automatic-check skip that spares an already-known-bad
    credential from being retried on every periodic health tick."""
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
            state = _set_connection_state(connector_id, "healthy", identity=identity, verified=True)
            return {
                "valid": True,
                "status": "connected",
                "message": f"{entry.name} credentials are active",
                "identity": identity,
                "last_verified": state["last_verified"],
            }
        else:
            _set_connection_state(connector_id, "expired", error="Authentication failed", identity="")
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
    """Check status and optionally poll a specific resource.

    With no `resource`, this reads the connection-state CACHE and never
    re-authenticates -- restored 2026-09-14: this had regressed to calling
    connector.authenticate() on every single call, which is exactly the
    re-auth spam / retry-storm-against-a-known-bad-credential the cache
    exists to prevent (a UI polling /status every few seconds would otherwise
    hammer the real provider with auth calls nonstop). Use POST .../check to
    force a real re-verification."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    if not is_connector_configured(connector_id, env_config):
        state = _clear_connection_state(connector_id)
        return {**state, "detail": {"missing_fields": get_missing_fields(connector_id, env_config)}}

    if not resource:
        state = _connection_state(connector_id, env_config)
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
        if not target:
            try:
                res_meta = get_connector_resources(connector_id)
                res_list = res_meta.get("resources", []) if isinstance(res_meta, dict) else []
                if res_list:
                    target = res_list[0].get("id", "")
            except Exception:
                pass

        events = connector.get_stats(target=target)

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

def _start_watch_internal(connector_id: str, target: str, interval: int = 5, persist: bool = True) -> Dict[str, Any]:
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    if not target:
        raise APIBridgeException("BAD_REQUEST", "Field 'target' is required", 400)

    watch_id = f"{connector_id}:{target}"
    if watch_id in _active_watches:
        raise APIBridgeException("WATCH_ALREADY_ACTIVE", f"Watch already active for {watch_id}", 409)

    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    connector = get_connector(connector_id, env_config)

    try:
        import inspect
        sig = inspect.signature(connector.watch)
        if "interval" in sig.parameters:
            handle = connector.watch(target, interval=interval)
        else:
            handle = connector.watch(target)

        # Adapt iterator or generator if connector.watch() yields directly
        if not isinstance(handle, WatchHandle):
            class _WatchHandleAdapter(WatchHandle):
                def __init__(self, raw_handle, conn_name: str, tgt: str, poll_int: int):
                    self.raw = raw_handle
                    self.connector = conn_name
                    self.target = tgt
                    self.interval = poll_int
                    self._active = True
                def poll(self):
                    if not self._active:
                        return []
                    if hasattr(self.raw, "poll"):
                        return self.raw.poll()
                    return []
                def stop(self):
                    self._active = False
                    if hasattr(self.raw, "stop"):
                        self.raw.stop()
            handle = _WatchHandleAdapter(handle, connector_id, target, interval)

        _active_watches[watch_id] = handle
        _watch_metadata[watch_id] = {
            "connector": connector_id,
            "target": target,
            "interval": max(1, interval),
            "last_poll_time": 0.0,
            "status": "healthy",
            "consecutive_failures": 0,
            "last_error": None,
            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        _paused_watches.discard(watch_id)

        if persist:
            _persist_watch_to_yaml(connector_id, target, interval)

        return {"watch_id": watch_id, "target": target, "status": "active", "interval": interval}
    except NotImplementedError:
        raise APIBridgeException("CONNECTOR_API_ERROR", f"Watch not supported by {connector_id}", 400)
    except Exception as e:
        raise APIBridgeException("CONNECTOR_API_ERROR", f"Failed to start watch: {str(e)}", 500)


def _stop_watch_internal(connector_id: str, target: Optional[str] = None, watch_id: Optional[str] = None, persist: bool = True) -> bool:
    wid = watch_id or (f"{connector_id}:{target}" if target else None)
    if not wid or wid not in _active_watches:
        raise APIBridgeException("RESOURCE_NOT_FOUND", f"No active watch found for {wid}", 404)

    handle = _active_watches.pop(wid, None)
    _watch_metadata.pop(wid, None)
    _paused_watches.discard(wid)

    if handle:
        try:
            handle.stop()
        except Exception as e:
            logger.warning(f"Error stopping watch handle {wid}: {e}")

    if persist:
        _remove_watch_from_yaml(wid)

    return True


def _restore_persisted_watches():
    try:
        data = _read_prash_yaml()
        watches = data.get("active_watches", [])
        if not isinstance(watches, list):
            return
        for item in watches:
            if not isinstance(item, dict):
                continue
            cid = item.get("connector")
            target = item.get("target")
            interval = item.get("interval", 5)
            if cid and target:
                try:
                    _start_watch_internal(cid, target, interval=interval, persist=False)
                except Exception as e:
                    logger.debug(f"Could not restore watch {cid}:{target}: {e}")
    except Exception as e:
        logger.warning(f"Error restoring watches from prash.yaml: {e}")


@app.post("/api/connectors/{connector_id}/watch")
def start_watch(connector_id: str, body: Dict[str, Any] = Body(...)):
    """Start watching a resource via the connector's watch() handle."""
    target = body.get("target")
    interval = int(body.get("interval", 5))
    return _start_watch_internal(connector_id, target, interval=interval, persist=True)


@app.delete("/api/connectors/{connector_id}/watch")
def stop_watch(connector_id: str, target: Optional[str] = Query(None), watch_id: Optional[str] = Query(None)):
    """Stop an active watch handle."""
    _stop_watch_internal(connector_id, target=target, watch_id=watch_id, persist=True)
    return {"success": True}


@app.post("/api/connectors/{connector_id}/watch/pause")
def pause_watch(connector_id: str, body: Dict[str, Any] = Body(...)):
    """Pause an active watch handle without destroying it."""
    wid = body.get("watch_id") or (f"{connector_id}:{body.get('target')}" if body.get("target") else None)
    if not wid or wid not in _active_watches:
        raise APIBridgeException("RESOURCE_NOT_FOUND", f"No active watch found for {wid}", 404)
    _paused_watches.add(wid)
    if wid in _watch_metadata:
        _watch_metadata[wid]["status"] = "paused"
    return {"success": True, "watch_id": wid, "status": "paused"}


@app.post("/api/connectors/{connector_id}/watch/resume")
def resume_watch(connector_id: str, body: Dict[str, Any] = Body(...)):
    """Resume a paused watch handle."""
    wid = body.get("watch_id") or (f"{connector_id}:{body.get('target')}" if body.get("target") else None)
    if not wid or wid not in _active_watches:
        raise APIBridgeException("RESOURCE_NOT_FOUND", f"No active watch found for {wid}", 404)
    _paused_watches.discard(wid)
    if wid in _watch_metadata:
        _watch_metadata[wid]["status"] = "healthy"
    return {"success": True, "watch_id": wid, "status": "active"}


@app.get("/api/watch/poll")
def poll_active_watches():
    """Polls all active watch handles for new events. Returns empty if idle."""
    all_events: List[Dict[str, Any]] = []
    for watch_id, handle in list(_active_watches.items()):
        if watch_id in _paused_watches:
            continue
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


def _infer_connector_from_action(action_id: Optional[str]) -> str:
    if not action_id:
        return "system"
    act = str(action_id).lower()
    for cid in (
        "aws", "github", "kubernetes", "k8s", "vercel", "datadog",
        "grafana", "snyk", "gitleaks", "terraform", "gitlab", "azure", "gcp", "pagerduty"
    ):
        if cid in act:
            return "kubernetes" if cid == "k8s" else cid
    return "system"


def _infer_severity(ev: Dict[str, Any]) -> str:
    if "severity" in ev and ev["severity"]:
        return str(ev["severity"]).lower()
    status = str(ev.get("status", "")).lower()
    event_type = str(ev.get("event_type", "")).lower()
    risk = str(ev.get("risk_tier", "")).lower()
    if status in ("failed", "error") or "error" in event_type or "fail" in event_type:
        return "error"
    if status in ("degraded", "warning") or risk in ("destructive", "disruptive") or "warn" in event_type or "degrade" in event_type:
        return "warning"
    return "info"


@app.get("/api/activity")
def get_activity_log(
    q: Optional[str] = Query(None, description="Free text search query"),
    connector: Optional[str] = Query(None, description="Filter by connector ID"),
    event_type: Optional[str] = Query(None, alias="type", description="Filter by event type"),
    severity: Optional[str] = Query(None, description="Filter by severity: info, warning, error"),
    time_range: Optional[str] = Query(None, description="Time range: 1h, 24h, 7d, 30d, all"),
    limit: int = Query(50, ge=1, le=500, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
):
    """Return aggregated historical and live events across active watches and persistent audit log records.
    Supports filtering, text search, and pagination.
    """
    all_events_map: Dict[str, Dict[str, Any]] = {}

    # 1. Ingest live/in-memory events
    for ev in _activity_log:
        norm = dict(ev)
        ev_id = str(norm.get("id") or f"{norm.get('watch_id', 'live')}_{norm.get('timestamp', '')}")
        norm["id"] = ev_id
        norm["severity"] = _infer_severity(norm)
        norm["connector"] = str(norm.get("connector", "system"))
        norm["event_type"] = str(norm.get("event_type", "event"))
        norm["timestamp"] = norm.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat()
        norm["summary"] = str(norm.get("summary") or norm.get("event_type", "System event"))
        all_events_map[ev_id] = norm

    # 2. Ingest disk-persisted audit log entries
    try:
        from prash.audit import AuditLog
        audit = AuditLog()
        for entry in audit.read(limit=500):
            entry_id = str(entry.get("id") or entry.get("seq") or f"audit_{entry.get('ts')}")
            # If already ingested via live activity log, keep the live one or merge
            if entry_id not in all_events_map:
                cid = entry.get("extra", {}).get("service_context", {}).get("connector_id") or _infer_connector_from_action(entry.get("action"))
                sev = "error" if entry.get("status") == "failed" else ("warning" if entry.get("risk_tier") in ("destructive", "disruptive") else "info")
                all_events_map[entry_id] = {
                    "id": entry_id,
                    "timestamp": entry.get("ts") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "connector": cid,
                    "event_type": "ACTION_EXECUTED",
                    "severity": sev,
                    "summary": f"Executed action {entry.get('action')}: {entry.get('summary', 'Action completed')}",
                    "details": entry,
                    "action": entry.get("action"),
                    "status": entry.get("status"),
                }
    except Exception as e:
        logger.warning(f"Error loading disk audit log in get_activity_log: {e}")

    # 3. Sort all events chronologically descending
    results = list(all_events_map.values())
    results.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)

    # 4. Filter by connector
    if connector and connector.lower() != "all":
        conn_lower = connector.lower()
        results = [ev for ev in results if str(ev.get("connector", "")).lower() == conn_lower]

    # 5. Filter by event type
    if event_type and event_type.lower() != "all":
        type_lower = event_type.lower()
        results = [ev for ev in results if type_lower in str(ev.get("event_type", "")).lower()]

    # 6. Filter by severity
    if severity and severity.lower() != "all":
        sev_lower = severity.lower()
        results = [ev for ev in results if str(ev.get("severity", "")).lower() == sev_lower]

    # 7. Filter by time range
    if time_range and time_range.lower() != "all":
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        delta = None
        tr = time_range.lower()
        if tr == "1h":
            delta = datetime.timedelta(hours=1)
        elif tr == "24h":
            delta = datetime.timedelta(hours=24)
        elif tr == "7d":
            delta = datetime.timedelta(days=7)
        elif tr == "30d":
            delta = datetime.timedelta(days=30)

        if delta:
            cutoff = now_dt - delta
            filtered_tr = []
            for ev in results:
                ts_str = ev.get("timestamp") or ev.get("ts")
                if ts_str:
                    try:
                        clean_ts = str(ts_str).replace("Z", "+00:00")
                        ev_dt = datetime.datetime.fromisoformat(clean_ts)
                        if ev_dt.tzinfo is None:
                            ev_dt = ev_dt.replace(tzinfo=datetime.timezone.utc)
                        if ev_dt >= cutoff:
                            filtered_tr.append(ev)
                    except Exception:
                        filtered_tr.append(ev)
                else:
                    filtered_tr.append(ev)
            results = filtered_tr

    # 8. Text search
    if q:
        q_lower = q.lower()
        results = [
            ev for ev in results
            if q_lower in str(ev.get("summary", "")).lower()
            or q_lower in str(ev.get("event_type", "")).lower()
            or q_lower in str(ev.get("connector", "")).lower()
            or q_lower in str(ev.get("id", "")).lower()
        ]

    # 9. Pagination
    total = len(results)
    paged = results[offset : offset + limit]
    has_more = (offset + len(paged)) < total

    return {
        "events": paged,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
    }


@app.get("/api/dashboard/summary")
def get_dashboard_summary():
    """Returns aggregate infrastructure health summary, counts, and active watch totals.
    Implements a 10s in-memory TTL cache to minimize connector polling overhead.
    """
    import time
    now = time.time()
    if _dashboard_summary_cache["data"] is not None and (now - _dashboard_summary_cache["timestamp"]) < 10.0:
        cached_result = dict(_dashboard_summary_cache["data"])
        cached_result["cached"] = True
        return cached_result

    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    yaml_data = _read_prash_yaml()
    projects = yaml_data.get("projects", [])
    if not isinstance(projects, list):
        projects = []

    # Gather configured connectors
    configured_connectors = [
        cid for cid in CONNECTOR_REGISTRY if is_connector_configured(cid, env_config)
    ]
    unconfigured_count = len(CONNECTOR_REGISTRY) - len(configured_connectors)

    # Collect distinct services from projects
    services_seen = set()
    total_services = 0
    for p in projects:
        if isinstance(p, dict):
            for env in p.get("environments", []):
                if isinstance(env, dict):
                    for s in env.get("services", []):
                        if isinstance(s, dict):
                            total_services += 1
                            key = f"{s.get('connector_id')}:{s.get('resource_id')}"
                            services_seen.add(key)

    # Check status of configured connectors
    healthy_count = 0
    degraded_count = 0
    error_count = 0

    # Also incorporate active watch statuses
    for wid, handle in list(_active_watches.items()):
        meta = _watch_metadata.get(wid, {})
        w_status = meta.get("status", "healthy")
        if w_status == "degraded":
            degraded_count += 1
        elif w_status == "error":
            error_count += 1

    # Check configured connectors
    for cid in configured_connectors:
        try:
            conn = get_connector(cid, env_config)
            is_auth = conn.authenticate()
            if is_auth:
                healthy_count += 1
            else:
                degraded_count += 1
        except Exception:
            error_count += 1

    total_active_entities = healthy_count + degraded_count + error_count
    if total_active_entities == 0:
        health_score = 0
        overall_status = "unconfigured"
    else:
        score_calc = int(((healthy_count * 100) + (degraded_count * 50)) / total_active_entities)
        health_score = max(0, min(100, score_calc))
        if error_count > 0:
            overall_status = "error"
        elif degraded_count > 0 or health_score < 80:
            overall_status = "degraded"
        else:
            overall_status = "healthy"

    result = {
        "status": overall_status,
        "health_score": health_score,
        "counts": {
            "total_services": total_services,
            "configured_connectors": len(configured_connectors),
            "unconfigured_connectors": unconfigured_count,
            "healthy": healthy_count,
            "degraded": degraded_count,
            "error": error_count,
        },
        "active_watches_count": len(_active_watches),
        "projects_count": len(projects),
        "cached": False,
    }

    _dashboard_summary_cache["timestamp"] = now
    _dashboard_summary_cache["data"] = result
    return result


@app.get("/api/dashboard/activity")
def get_dashboard_activity(limit: int = Query(10)):
    """Returns cross-service recent events merged from activity log and active watch events."""
    recent_events = list(_activity_log)

    # Also gather recent error events from active watches
    for wid, handle in list(_active_watches.items()):
        meta = _watch_metadata.get(wid, {})
        conn_id = meta.get("connector") or getattr(handle, "connector", wid.split(":")[0] if ":" in wid else "system")
        target = meta.get("target") or getattr(handle, "target", wid.split(":", 1)[1] if ":" in wid else wid)
        last_err = meta.get("last_error")
        if last_err:
            recent_events.append({
                "watch_id": wid,
                "connector": conn_id,
                "event_type": "WATCH_ERROR",
                "summary": f"Watch error on {target}: {last_err}",
                "timestamp": meta.get("started_at") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "severity": "error",
            })

    # Sort descending by timestamp
    recent_events.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
    clamped_limit = max(1, min(100, limit))
    sliced = recent_events[:clamped_limit]

    return {
        "events": sliced,
        "count": len(sliced),
        "total_available": len(recent_events),
    }


@app.get("/api/watch/active")
def get_active_watches():
    """Returns list of currently active watch handles with target, connector, interval, and health status."""
    watches = []
    for wid, handle in list(_active_watches.items()):
        meta = _watch_metadata.get(wid, {})
        connector_id = meta.get("connector") or getattr(handle, "connector", wid.split(":")[0] if ":" in wid else "unknown")
        target = meta.get("target") or getattr(handle, "target", wid.split(":", 1)[1] if ":" in wid else wid)
        interval = meta.get("interval") or getattr(handle, "interval", 5)
        status = "paused" if wid in _paused_watches else meta.get("status", "healthy")

        watches.append({
            "watch_id": wid,
            "connector": connector_id,
            "target": target,
            "interval": interval,
            "status": status,
            "consecutive_failures": meta.get("consecutive_failures", 0),
            "last_error": meta.get("last_error"),
            "started_at": meta.get("started_at"),
        })
    return {"watches": watches, "count": len(watches)}


@app.get("/api/system/version")
def get_system_version():
    """Returns dynamic system version, environment, and connector statistics."""
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}
    configured_count = sum(1 for cid in CONNECTOR_REGISTRY if is_connector_configured(cid, env_config))
    return {
        "version": "2.4.0",
        "name": "Lear Desktop Console",
        "engine": "FastAPI + Prash Core",
        "status": "operational",
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "connectors_total": len(CONNECTOR_REGISTRY),
        "connectors_configured": configured_count,
    }


@app.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """Real-time event stream broadcasting watch events and handling client control messages."""
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            text = await websocket.receive_text()
            if not text:
                continue
            try:
                msg = json.loads(text)
                action = msg.get("action") or msg.get("type")
                if action == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    }))
                elif action == "pause":
                    wid = msg.get("watch_id")
                    if wid and wid in _active_watches:
                        _paused_watches.add(wid)
                        if wid in _watch_metadata:
                            _watch_metadata[wid]["status"] = "paused"
                        await websocket.send_text(json.dumps({
                            "type": "control_ack",
                            "action": "pause",
                            "watch_id": wid,
                            "success": True,
                        }))
                elif action == "resume":
                    wid = msg.get("watch_id")
                    if wid and wid in _active_watches:
                        _paused_watches.discard(wid)
                        if wid in _watch_metadata:
                            _watch_metadata[wid]["status"] = "healthy"
                        await websocket.send_text(json.dumps({
                            "type": "control_ack",
                            "action": "resume",
                            "watch_id": wid,
                            "success": True,
                        }))
                elif action == "stop":
                    wid = msg.get("watch_id")
                    cid = msg.get("connector_id") or (wid.split(":", 1)[0] if wid and ":" in wid else "")
                    target = msg.get("target") or (wid.split(":", 1)[1] if wid and ":" in wid else "")
                    if wid and wid in _active_watches:
                        _stop_watch_internal(cid, target=target, watch_id=wid)
                        await websocket.send_text(json.dumps({
                            "type": "control_ack",
                            "action": "stop",
                            "watch_id": wid,
                            "success": True,
                        }))
            except Exception as e:
                logger.debug(f"Non-JSON or unhandled WS message: {e}")
    except WebSocketDisconnect:
        _ws_clients.discard(websocket)
    except Exception:
        _ws_clients.discard(websocket)


# ---------------------------------------------------------------------------
# Project System (prash.yaml CRUD)
# ---------------------------------------------------------------------------


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

    def mask(val: Optional[str]) -> str:
        if not val:
            return ""
        if len(val) <= 6:
            return "••••••••"
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
    """Update non-connector desktop settings; credentials require
    authentication via /connect. Restored 2026-09-14: this had regressed to
    accepting any key at all, including connector credentials -- meaning a
    bad or untested credential could be written straight to .env through this
    generic endpoint, completely bypassing the /connect authentication gate."""
    registry_keys = {field.key for entry in CONNECTOR_REGISTRY.values() for field in entry.auth_fields}
    rejected = sorted(str(key) for key in updates if str(key) in registry_keys)
    if rejected:
        raise APIBridgeException(
            "CONNECTOR_AUTH_REQUIRED",
            f"Connector credential keys must be authenticated via /api/connectors/{{id}}/connect: {', '.join(rejected)}",
            400,
        )
    _persist_credentials({str(key): str(value) for key, value in updates.items() if value})
    clear_connector_cache()
    return {"success": True}


# ---------------------------------------------------------------------------
# Platform Settings & System Version
# ---------------------------------------------------------------------------

AVAILABLE_AI_MODELS = [
    {
        "id": "deepseek-v4-flash",
        "name": "DeepSeek Flash",
        "desc": "Ultra-fast intent resolution & real-time telemetry diagnostics",
        "provider": "DeepSeek",
    },
    {
        "id": "kimi-k2.6",
        "name": "Kimi K2.6",
        "desc": "Deep technical reasoning & large log context synthesis",
        "provider": "Moonshot",
    },
    {
        "id": "gemini-1.5-pro",
        "name": "Gemini 1.5 Pro",
        "desc": "High-capability multi-modal reasoning & architecture analysis",
        "provider": "Google",
    },
    {
        "id": "claude-3-5-sonnet",
        "name": "Claude 3.5 Sonnet",
        "desc": "Industry standard for systems diagnosis and code generation",
        "provider": "Anthropic",
    },
    {
        "id": "gpt-4o",
        "name": "GPT-4o",
        "desc": "Advanced multi-modal reasoning & operational action routing",
        "provider": "OpenAI",
    },
]

AVAILABLE_PERMISSION_MODES = [
    {
        "id": "ask",
        "label": "Ask First (Recommended)",
        "desc": "Always request user confirmation before modifying cloud or infrastructure resources.",
    },
    {
        "id": "auto-safe",
        "label": "Auto-Safe Tier",
        "desc": "Execute read-only diagnostics and safe remediation automatically; prompt for write actions.",
    },
    {
        "id": "bypass",
        "label": "Bypass (Autonomous)",
        "desc": "Allow autonomous remediation for verified health degradation without interactive prompts.",
    },
]

DEFAULT_POLL_INTERVAL = 15
DEFAULT_RETENTION_DAYS = 30


@app.get("/api/settings")
def get_settings():
    """Returns current AI model, permission mode, watcher settings, and available options."""
    yaml_data = _read_prash_yaml()
    settings = yaml_data.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}

    current_model = settings.get("model") or env_config.get("PRIMARY_MODEL") or "deepseek-v4-flash"
    current_perm = settings.get("permission_mode") or env_config.get("PRASH_PERMISSION_MODE") or "ask"

    poll_interval_str = env_config.get("PRASH_WATCH_INTERVAL_SECONDS")
    try:
        default_poll = int(poll_interval_str) if poll_interval_str else DEFAULT_POLL_INTERVAL
    except Exception:
        default_poll = DEFAULT_POLL_INTERVAL
    poll_interval = settings.get("poll_interval", default_poll)

    retention_days = settings.get("retention_days", DEFAULT_RETENTION_DAYS)
    desktop_notifications = settings.get("desktop_notifications", True)
    alert_on_degraded = settings.get("alert_on_degraded", True)

    slack_webhook = settings.get("slack_webhook") or env_config.get("SLACK_WEBHOOK_URL") or ""
    discord_webhook = settings.get("discord_webhook") or env_config.get("DISCORD_WEBHOOK_URL") or ""
    pagerduty_key = settings.get("pagerduty_key") or env_config.get("PAGERDUTY_ROUTING_KEY") or ""

    return {
        "model": current_model,
        "permission_mode": current_perm,
        "available_models": AVAILABLE_AI_MODELS,
        "available_permission_modes": AVAILABLE_PERMISSION_MODES,
        "poll_interval": poll_interval,
        "retention_days": retention_days,
        "desktop_notifications": desktop_notifications,
        "alert_on_degraded": alert_on_degraded,
        "slack_webhook": slack_webhook,
        "discord_webhook": discord_webhook,
        "pagerduty_key": pagerduty_key,
        "status": "success",
    }


@app.post("/api/settings")
def save_settings(payload: Dict[str, Any] = Body(...)):
    """Persists model, permission mode, watcher cadence, and alerting to prash.yaml and .env."""
    yaml_data = _read_prash_yaml()
    if "settings" not in yaml_data or not isinstance(yaml_data["settings"], dict):
        yaml_data["settings"] = {}

    settings_dict = yaml_data["settings"]

    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, "w").close()

    if "model" in payload and payload["model"]:
        model = str(payload["model"])
        settings_dict["model"] = model
        dotenv.set_key(ENV_PATH, "PRIMARY_MODEL", model)

    if "permission_mode" in payload and payload["permission_mode"]:
        perm = str(payload["permission_mode"])
        settings_dict["permission_mode"] = perm
        dotenv.set_key(ENV_PATH, "PRASH_PERMISSION_MODE", perm)

    if "poll_interval" in payload:
        try:
            val = int(payload["poll_interval"])
            settings_dict["poll_interval"] = val
            dotenv.set_key(ENV_PATH, "PRASH_WATCH_INTERVAL_SECONDS", str(val))
        except (ValueError, TypeError):
            pass

    if "retention_days" in payload:
        try:
            settings_dict["retention_days"] = int(payload["retention_days"])
        except (ValueError, TypeError):
            pass

    if "desktop_notifications" in payload:
        settings_dict["desktop_notifications"] = bool(payload["desktop_notifications"])
        dotenv.set_key(ENV_PATH, "PRASH_DESKTOP_NOTIFICATIONS", "true" if payload["desktop_notifications"] else "false")

    if "alert_on_degraded" in payload:
        settings_dict["alert_on_degraded"] = bool(payload["alert_on_degraded"])

    if "slack_webhook" in payload:
        slack_val = str(payload["slack_webhook"]).strip()
        settings_dict["slack_webhook"] = slack_val
        if slack_val:
            dotenv.set_key(ENV_PATH, "SLACK_WEBHOOK_URL", slack_val)
        else:
            dotenv.unset_key(ENV_PATH, "SLACK_WEBHOOK_URL")

    if "discord_webhook" in payload:
        discord_val = str(payload["discord_webhook"]).strip()
        settings_dict["discord_webhook"] = discord_val
        if discord_val:
            dotenv.set_key(ENV_PATH, "DISCORD_WEBHOOK_URL", discord_val)
        else:
            dotenv.unset_key(ENV_PATH, "DISCORD_WEBHOOK_URL")

    if "pagerduty_key" in payload:
        pd_val = str(payload["pagerduty_key"]).strip()
        settings_dict["pagerduty_key"] = pd_val
        if pd_val:
            dotenv.set_key(ENV_PATH, "PAGERDUTY_ROUTING_KEY", pd_val)
        else:
            dotenv.unset_key(ENV_PATH, "PAGERDUTY_ROUTING_KEY")

    _write_prash_yaml(yaml_data)
    dotenv.load_dotenv(ENV_PATH, override=True)

    return {
        "success": True,
        "status": "success",
        "settings": settings_dict,
    }




# ---------------------------------------------------------------------------
# Enhanced AI Chat with Live Telemetry Injection
# ---------------------------------------------------------------------------

@app.get("/api/chat/greeting")
def get_chat_greeting(
    connector_id: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
):
    """Generates dynamic, live-telemetry greeting and suggested prompts for Copilot."""
    env_config = dotenv.dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}

    # 1. Service context greeting
    if connector_id and connector_id.lower() in CONNECTOR_REGISTRY:
        cid = connector_id.lower()
        conn = None
        if is_connector_configured(cid, env_config):
            try:
                conn = get_connector(cid, env_config)
            except Exception as ce:
                logger.warning(f"Error instantiating connector {cid} for greeting: {ce}")

        state_str = "connected"
        telemetry_detail: Dict[str, Any] = {}
        cpu_val = None
        mem_val = None

        if conn:
            if resource_id:
                try:
                    state_obj = conn.poll_state(resource_id)
                    state_str = state_obj.state.value if hasattr(state_obj, "state") else str(state_obj)
                    telemetry_detail = state_obj.detail if hasattr(state_obj, "detail") else {}
                    if isinstance(telemetry_detail, dict):
                        cpu_val = telemetry_detail.get("cpu") or telemetry_detail.get("cpu_percent") or telemetry_detail.get("cpu_utilization")
                        mem_val = telemetry_detail.get("memory") or telemetry_detail.get("mem_percent") or telemetry_detail.get("memory_utilization")
                except Exception as pe:
                    state_str = f"unreachable ({str(pe)})"
            else:
                try:
                    is_auth = conn.authenticate()
                    state_str = "authenticated" if is_auth else "unauthenticated"
                except Exception as ae:
                    state_str = f"auth_failed ({str(ae)})"

        # Tailor prompt chips based on connector type
        if cid == "aws":
            suggested_prompts = [
                "Why is CPU utilization fluctuating?",
                "Show recent CloudWatch error events",
                "Check EC2 instance health checks",
                "Propose instance reboot or scale plan",
            ]
        elif cid == "kubernetes":
            suggested_prompts = [
                "Are any pods crash looping or failing?",
                "Show recent pod logs and events",
                "Inspect container memory limits",
                "Restart crashed deployment",
            ]
        elif cid == "github":
            suggested_prompts = [
                "Show status of recent CI workflow runs",
                "Diagnose latest build failure",
                "List open dependabot alerts",
            ]
        elif cid == "docker":
            suggested_prompts = [
                "Check container restart counts",
                "Inspect container resource limits",
                "Prune stopped containers and volumes",
            ]
        else:
            suggested_prompts = [
                f"What is the current status of {cid}?",
                "Inspect latest error logs and events",
                "Run diagnostic verification check",
            ]

        metric_snippets = []
        if cpu_val is not None:
            metric_snippets.append(f"CPU: {cpu_val}%")
        if mem_val is not None:
            metric_snippets.append(f"Memory: {mem_val}%")
        metrics_str = f" ({', '.join(metric_snippets)})" if metric_snippets else ""

        if resource_id:
            greeting_text = (
                f"Hello! I am Lear Copilot. Monitoring live infrastructure for **{cid.upper()}** (`{resource_id}`). "
                f"Current status is **{state_str}**{metrics_str}. "
                "How can I assist your operational workflow?"
            )
        else:
            greeting_text = (
                f"Hello! I am Lear Copilot. Connected to **{cid.upper()}** with status **{state_str}**. "
                "How can I assist your operational workflow?"
            )

        return {
            "greeting": greeting_text,
            "service_context": {"connector_id": cid, "resource_id": resource_id or ""},
            "state": state_str,
            "telemetry": telemetry_detail,
            "suggested_prompts": suggested_prompts,
        }

    # 2. Global Chat greeting (no connector specified or connector not registered)
    configured_connectors = [
        c for c in CONNECTOR_REGISTRY if is_connector_configured(c, env_config)
    ]
    active_watch_count = len(_active_watches)
    conf_count = len(configured_connectors)

    if conf_count > 0:
        names = ", ".join([c.upper() for c in configured_connectors])
        greeting_text = (
            f"Hello! I am Lear Copilot. Live bridge active across {conf_count} configured services ({names}) "
            f"with {active_watch_count} active watches. "
            "Ask about any service or use `@connector` to scope context."
        )
    else:
        greeting_text = (
            "Hello! I am Lear Copilot. No connectors configured yet. "
            "You can ask general operational questions, or set up integrations in Settings."
        )

    suggested_prompts = [
        "Summarize overall infrastructure health",
        "Show all active watches and recent events",
        "Check for any failing services or crash loops",
        "Explain available remediation commands",
    ]

    return {
        "greeting": greeting_text,
        "service_context": None,
        "state": "active",
        "telemetry": {"configured_connectors": configured_connectors, "active_watches": active_watch_count},
        "suggested_prompts": suggested_prompts,
    }


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
                "text": "I analyzed the current telemetry but could not identify an automated remediation command.",
                "actionRequired": False,
                "executable": False,
            }
    except Exception as e:
        return {
            "text": f"Error resolving intent: {str(e)}",
            "actionRequired": False,
            "executable": False,
        }


@app.post("/api/chat/stream")
async def chat_stream(
    payload: Dict[str, Any] = Body(...),
):
    """SSE streaming endpoint for Prash Copilot reasoning responses."""
    message = payload.get("message", "")
    service_context = payload.get("service_context")

    if not message:
        raise APIBridgeException("BAD_REQUEST", "Message is required", 400)

    async def event_generator():
        try:
            from prash.intent import _Context, _resolve_via_llm_async, Clarify, resolve, Suggestion

            ctx = _Context()
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
                explain_text = result.explain
                words = explain_text.split(" ")
                for word in words:
                    yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                    await asyncio.sleep(0.01)

                final_text = f"{result.explain} -> `prash {' '.join(result.argv)}`"
                final_payload = {
                    "text": final_text,
                    "actionRequired": True,
                    "command": result.argv,
                    "executable": True,
                    "action_id": result.argv[0] if result.argv else None,
                    "done": True,
                }
                yield f"data: {json.dumps(final_payload)}\n\n"

            elif isinstance(result, Clarify):
                question = result.question + (" Options: " + ", ".join(result.options) if result.options else "")
                words = question.split(" ")
                for word in words:
                    yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                    await asyncio.sleep(0.01)

                yield f"data: {json.dumps({'text': question, 'actionRequired': False, 'executable': False, 'done': True})}\n\n"

            else:
                fallback_msg = "I analyzed the current telemetry but could not identify an automated remediation command."
                words = fallback_msg.split(" ")
                for word in words:
                    yield f"data: {json.dumps({'token': word + ' ', 'done': False})}\n\n"
                    await asyncio.sleep(0.01)

                yield f"data: {json.dumps({'text': fallback_msg, 'actionRequired': False, 'executable': False, 'done': True})}\n\n"

        except Exception as err:
            logger.error(f"Error in chat stream: {err}")
            err_text = f"Bridge Error: {str(err)}"
            yield f"data: {json.dumps({'error': err_text, 'text': err_text, 'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/execute")
def execute_chat_action(payload: Dict[str, Any] = Body(...)):
    """Executes an action generated from intent resolution or chat copilot."""
    command = payload.get("command", [])
    action_id = payload.get("action_id", "")

    if not command and not action_id:
        raise APIBridgeException("BAD_REQUEST", "Command or action_id is required", 400)

    argv: List[str] = list(command) if isinstance(command, list) else str(command).split()
    if not argv and action_id:
        argv = [action_id]

    # Strip redundant 'prash' program prefix if provided
    if argv and argv[0].lower() == "prash":
        argv = argv[1:]

    # Known top-level subcommands in prash CLI
    known_subcommands = {
        "run", "fix", "investigate", "stats", "watch", "config",
        "doctor", "plugins", "actions", "diff", "reconcile", "version", "telemetry"
    }

    # If the command starts with an action name rather than subcommand, route via 'run'
    if argv and argv[0] not in known_subcommands and not argv[0].startswith("-"):
        argv = ["run"] + argv

    cmd_str = " ".join(argv)
    logger.info(f"Executing chat action: {cmd_str}")

    try:
        from prash.audit import AuditLog
        from io import StringIO
        import sys

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

        # Record in desktop in-memory activity log
        try:
            service_ctx = payload.get("service_context")
            conn_name = service_ctx.get("connector_id", "system") if isinstance(service_ctx, dict) else "system"
            act_event = {
                "watch_id": f"chat:{action_id or (argv[0] if argv else 'action')}",
                "connector": conn_name,
                "event_type": "ACTION_EXECUTED" if ret_code == 0 else "ACTION_FAILED",
                "summary": f"Executed `prash {cmd_str}` (exit {ret_code})",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "severity": "info" if ret_code == 0 else "error",
            }
            _activity_log.append(act_event)
        except Exception as act_err:
            logger.warning(f"Failed to record chat action in activity log: {act_err}")

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
            "command": argv,
            "output": f"Execution error: {str(e)}",
        }


# ---------------------------------------------------------------------------
# Notification System
# ---------------------------------------------------------------------------

@app.get("/api/notifications")
def get_notifications():
    """Returns persistent notification queue, unread count, and watch updates."""
    unread = sum(1 for n in _notifications if not n.get("read"))
    return {
        "notifications": _notifications,
        "unread_count": unread,
        "total": len(_notifications),
    }


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str):
    """Mark a notification (or all) as read and persist state."""
    global _notifications
    if notification_id.lower() == "all":
        for n in _notifications:
            n["read"] = True
        _save_notifications_to_disk()
        return {"success": True, "unread_count": 0}

    found = False
    for n in _notifications:
        if n.get("id") == notification_id:
            n["read"] = True
            found = True
            break

    if found:
        _save_notifications_to_disk()

    unread = sum(1 for n in _notifications if not n.get("read"))
    return {"success": True, "unread_count": unread}


@app.delete("/api/notifications")
def clear_notifications():
    """Clear all notifications and persist empty queue."""
    global _notifications
    _notifications = []
    _save_notifications_to_disk()
    return {"success": True, "unread_count": 0}


# ---------------------------------------------------------------------------
# AI Widget Generation & Layout Persistence
# ---------------------------------------------------------------------------

@app.post("/api/connectors/{connector_id}/generate-widgets")
def generate_widgets(
    connector_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
):
    """Dynamically generates custom widget configurations tailored to the connector, live telemetry, and prompt."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    entry = CONNECTOR_REGISTRY[connector_id]
    resource_id = payload.get("resource_id", "")
    prompt = payload.get("prompt", "")
    save_to_yaml = payload.get("save_to_yaml", False)

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

    # Synthesize widget configuration via dedicated widget_generator
    layout = synthesize_widgets(
        connector_id=connector_id,
        connector_name=entry.name,
        category=entry.category,
        capabilities=["metrics", "status", "watch"] if entry.supports_watch else ["metrics", "status"],
        available_metrics=available_metrics,
        current_status=current_status,
        templates=entry.widget_templates,
        resource_id=resource_id,
        prompt=prompt,
    )

    out_data = layout.to_dict()

    if save_to_yaml:
        save_widget_layout_to_yaml(connector_id, resource_id, out_data["widgets"], yaml_path=YAML_PATH)

    return out_data


@app.get("/api/connectors/{connector_id}/widgets")
def get_connector_widgets(
    connector_id: str,
    resource_id: str = Query(default=""),
):
    """Returns saved custom widget layout if present, otherwise returns registry default templates."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    entry = CONNECTOR_REGISTRY[connector_id]
    custom_layout = load_widget_layout_from_yaml(connector_id, resource_id, yaml_path=YAML_PATH)

    if custom_layout:
        return {
            "connector_id": connector_id,
            "resource_id": resource_id,
            "custom": True,
            "widgets": custom_layout,
        }

    # Transform default templates to consistent widget dict shape
    default_widgets = []
    row, col = 0, 0
    for idx, template in enumerate(entry.widget_templates):
        span = 2 if template.type in ("line_chart", "event_timeline", "bar_chart") else (3 if template.type == "status_grid" else 1)
        default_widgets.append({
            "id": f"{connector_id}_{template.id}",
            "type": template.type,
            "label": template.label,
            "metric_keys": template.metric_keys,
            "unit": template.unit,
            "description": template.description,
            "refresh_interval": template.refresh_interval,
            "position": {"row": row, "col": col, "span": span},
            "ai_generated": False,
        })
        col += span
        if col >= 3:
            col = 0
            row += 1

    return {
        "connector_id": connector_id,
        "resource_id": resource_id,
        "custom": False,
        "widgets": default_widgets,
    }


@app.put("/api/connectors/{connector_id}/widgets")
def save_connector_widgets(
    connector_id: str,
    payload: Dict[str, Any] = Body(...),
):
    """Persists a custom or manually customized widget layout for a connector/resource."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    resource_id = payload.get("resource_id", "")
    widgets = payload.get("widgets", [])
    if not isinstance(widgets, list):
        raise APIBridgeException("INVALID_PAYLOAD", "Expected 'widgets' to be a list", 400)

    # Validate each widget
    valid_widgets = []
    for w in widgets:
        if validate_widget_config(w):
            valid_widgets.append(w)

    success = save_widget_layout_to_yaml(connector_id, resource_id, valid_widgets, yaml_path=YAML_PATH)
    return {
        "success": success,
        "connector_id": connector_id,
        "resource_id": resource_id,
        "count": len(valid_widgets),
    }


@app.delete("/api/connectors/{connector_id}/widgets")
def reset_connector_widgets(
    connector_id: str,
    resource_id: str = Query(default=""),
):
    """Resets custom widget layout to connector registry defaults."""
    if connector_id not in CONNECTOR_REGISTRY:
        raise APIBridgeException("CONNECTOR_NOT_FOUND", f"Unknown connector: {connector_id}", 404)

    delete_widget_layout_from_yaml(connector_id, resource_id, yaml_path=YAML_PATH)
    return {
        "success": True,
        "connector_id": connector_id,
        "resource_id": resource_id,
        "reset": True,
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
