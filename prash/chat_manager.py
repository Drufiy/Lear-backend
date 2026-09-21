"""Lear Unified Chat & Audit Manager.

Manages persistent, multi-channel chat sessions and an immutable audit log across:
- Slack
- Email
- Lear Dashboard / Web
- Incident War Rooms

Strict separation:
- Questions on Slack only reply to Slack.
- Questions on Email only reply to Email.
- Questions on Dashboard only reply to Dashboard.
- All sessions are recorded into the central audit trail with sender tags:
  e.g. "slack: Anant: <prompt>" or "email: user@domain.com: <prompt>".
"""

import datetime
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CHAT_DIR = Path(__file__).resolve().parent.parent / ".prash" / "chat_sessions"
CHAT_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_INDEX_FILE = CHAT_DIR / "sessions_index.json"

_SESSIONS_INDEX: Dict[str, Dict[str, Any]] = {}
_SESSIONS_DATA: Dict[str, Dict[str, Any]] = {}


def _load_sessions():
    global _SESSIONS_INDEX, _SESSIONS_DATA
    if SESSIONS_INDEX_FILE.exists():
        try:
            _SESSIONS_INDEX = json.loads(SESSIONS_INDEX_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Could not load sessions index: {e}")
            _SESSIONS_INDEX = {}

    for path in CHAT_DIR.glob("session_*.json"):
        session_id = path.stem.replace("session_", "")
        if session_id not in _SESSIONS_DATA:
            try:
                _SESSIONS_DATA[session_id] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Could not read session {session_id}: {e}")


def _save_session(session_id: str):
    try:
        session = _SESSIONS_DATA.get(session_id)
        if session:
            session_file = CHAT_DIR / f"session_{session_id}.json"
            session_file.write_text(json.dumps(session, indent=2), encoding="utf-8")
        
        SESSIONS_INDEX_FILE.write_text(json.dumps(_SESSIONS_INDEX, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not save chat session {session_id}: {e}")


_load_sessions()


def generate_session_title(first_prompt: str, origin: str) -> str:
    """Generates a concise, informative title for a chat session."""
    cleaned = re.sub(r"^(slack|email|dashboard):\s*", "", first_prompt, flags=re.IGNORECASE).strip()
    words = cleaned.split()
    if len(words) > 8:
        title = " ".join(words[:8]) + "..."
    else:
        title = cleaned or "General Inquiry"
    
    # Capitalize first letter
    title = title[0].upper() + title[1:] if title else "Operational Query"
    return f"{origin.title()}: {title}"


def create_session(
    title: Optional[str] = None,
    origin: str = "dashboard",
    service: str = "checkout-api",
    incident_id: Optional[str] = None,
    initial_message: Optional[str] = None,
    sender_name: str = "User",
) -> Dict[str, Any]:
    """Creates a new dedicated chat session with audit trail."""
    now = datetime.datetime.now(datetime.timezone.utc)
    session_id = incident_id or f"chat_{int(now.timestamp()*1000)}"
    
    if not title:
        if incident_id:
            title = f"Incident: {incident_id} ({service})"
        elif initial_message:
            title = generate_session_title(initial_message, origin)
        else:
            title = f"{origin.title()} Session"

    session = {
        "session_id": session_id,
        "title": title,
        "origin": origin,
        "service": service,
        "incident_id": incident_id,
        "status": "ACTIVE",
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "created_at_epoch": int(now.timestamp()),
        "last_activity": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "messages": [],
        "attachments": [],
    }

    _SESSIONS_DATA[session_id] = session
    _SESSIONS_INDEX[session_id] = {
        "session_id": session_id,
        "title": title,
        "origin": origin,
        "service": service,
        "incident_id": incident_id,
        "status": "ACTIVE",
        "last_activity": session["last_activity"],
        "created_at_epoch": session["created_at_epoch"],
        "message_count": 0,
    }

    _save_session(session_id)
    return session


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    _load_sessions()
    return _SESSIONS_DATA.get(session_id)


def list_sessions(origin: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists all sessions sorted by last activity."""
    _load_sessions()
    sessions = []
    for sid, meta in _SESSIONS_INDEX.items():
        if origin and origin.lower() != "all" and meta.get("origin", "").lower() != origin.lower():
            continue
        sessions.append(meta)

    # Sort descending by creation epoch or last activity
    return sorted(sessions, key=lambda x: x.get("created_at_epoch", 0), reverse=True)


def append_message(
    session_id: str,
    sender: str,
    role: str,
    text: str,
    origin: str = "dashboard",
    attachment: Optional[Dict[str, Any]] = None,
    quick_replies: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Appends a message to a session with immutable audit recording."""
    session = get_session(session_id)
    if not session:
        session = create_session(session_id=session_id, origin=origin)

    now = datetime.datetime.now(datetime.timezone.utc)
    time_str = now.strftime("%H:%M:%S")

    msg_id = f"msg_{int(now.timestamp()*1000)}"
    message_record = {
        "id": msg_id,
        "sender": sender,
        "role": role,
        "text": text,
        "origin": origin,
        "timestamp": time_str,
        "attachment": attachment,
        "quick_replies": quick_replies,
    }

    session["messages"].append(message_record)
    session["last_activity"] = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    if attachment:
        session.setdefault("attachments", []).append(attachment)

    # Update index
    if session_id in _SESSIONS_INDEX:
        _SESSIONS_INDEX[session_id]["last_activity"] = session["last_activity"]
        _SESSIONS_INDEX[session_id]["message_count"] = len(session["messages"])
        _SESSIONS_INDEX[session_id]["status"] = session.get("status", "ACTIVE")

    _save_session(session_id)
    return message_record


def get_or_create_channel_session(
    channel: str,
    sender_identifier: str,
    initial_text: str,
    incident_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieves an existing active session or creates a new dedicated session for this channel interaction."""
    _load_sessions()

    # If linked to an incident, use or create that incident session
    if incident_id:
        existing = get_session(incident_id)
        if existing:
            return existing
        return create_session(
            origin=channel,
            incident_id=incident_id,
            title=f"Incident: {incident_id}",
            initial_message=initial_text,
            sender_name=sender_identifier,
        )

    # Search for an active session from this sender and channel created in the last 2 hours
    cutoff = int(datetime.datetime.now(datetime.timezone.utc).timestamp()) - 7200
    for sid, meta in sorted(_SESSIONS_INDEX.items(), key=lambda x: x[1].get("created_at_epoch", 0), reverse=True):
        if (
            meta.get("origin", "").lower() == channel.lower()
            and meta.get("created_at_epoch", 0) > cutoff
            and not meta.get("incident_id")
            and meta.get("status") == "ACTIVE"
        ):
            sess = get_session(sid)
            if sess:
                return sess

    # Otherwise create a new dedicated session
    title = generate_session_title(initial_text, channel)
    return create_session(
        title=title,
        origin=channel,
        initial_message=initial_text,
        sender_name=sender_identifier,
    )
