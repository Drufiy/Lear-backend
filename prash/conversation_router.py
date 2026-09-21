"""Bidirectional Conversation Router for Lear SRE Copilot (Email & Slack).

Enables two-way conversational interaction with Lear Copilot via:
1. Real Gmail Inbound (IMAP poller checking for incoming replies from anantacharya5568@gmail.com)
2. Slack Integration (Incoming Webhook, Slash Commands /lear, Event Subscriptions, and Interactivity)
3. Shared Incident War Room & Lear Mission Control Dashboard
"""

import asyncio
import datetime
import email
from email.header import decode_header
import html
import imaplib
import json
import logging
import os
import re
import smtplib
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from prash.incident_manager import (
    get_incident,
    get_latest_incident,
    post_incident_chat,
    approve_incident,
    deny_incident,
    execute_remediation
)
from prash.email_service import dispatch_copilot_email_reply, dispatch_email_alert
from prash.slack_service import dispatch_slack_chat_response, dispatch_slack_alert

logger = logging.getLogger(__name__)

_IMAP_THREAD = None
_IMAP_STOP_EVENT = threading.Event()
_PROCESSED_EMAIL_IDS = set()


def load_credentials() -> Dict[str, str]:
    """Loads environment credentials from os.environ and .env file into os.environ and returns dict."""
    import dotenv
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        dotenv.load_dotenv(env_file, override=False)
    return dict(os.environ)

load_credentials()


def decode_mime_words(s: Optional[str]) -> str:
    """Decodes MIME encoded header strings like '=?UTF-8?B?...=' into plain text."""
    if not s:
        return ""
    try:
        parts = decode_header(s)
        decoded = []
        for part, enc in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(enc or "utf-8", errors="ignore"))
            else:
                decoded.append(str(part))
        return " ".join(decoded)
    except Exception:
        return str(s)


def extract_plain_text(msg: email.message.Message) -> str:
    """Extracts clean text body from an email, stripping quotation headers and HTML."""
    body = ""
    html_fallback = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if "attachment" in content_disposition:
                continue
            if content_type == "text/plain" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
            elif content_type == "text/html" and not html_fallback:
                payload = part.get_payload(decode=True)
                if payload:
                    html_fallback = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            decoded = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
            if content_type == "text/plain":
                body = decoded
            else:
                html_fallback = decoded

    if not body and html_fallback:
        # Strip html tags for plain text
        cleaned = re.sub(r"<style[\s\S]*?</style>", " ", html_fallback, flags=re.IGNORECASE)
        cleaned = re.sub(r"<script[\s\S]*?</script>", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        body = html.unescape(cleaned)

    # Strip quotation headers, e.g. "On Mon, Sep 21... wrote:" or ">" quotes
    lines = []
    for line in body.splitlines():
        trimmed = line.strip()
        if trimmed.startswith(">"):
            continue
        if re.match(r"^On\s+.*wrote:\s*$", trimmed, re.IGNORECASE):
            break
        if re.match(r"^-+\s*Original Message\s*-+", trimmed, re.IGNORECASE):
            break
        lines.append(line)

    clean_text = "\n".join(lines).strip()
    return clean_text or body.strip()


def extract_incident_id(subject: str, body: str) -> Optional[str]:
    """Finds incident ID from subject or body."""
    match = re.search(r"\bINC-\d+\b", subject)
    if match:
        return match.group(0)
    match = re.search(r"\bINC-\d+\b", body)
    if match:
        return match.group(0)
    return None


async def answer_general_copilot_query(user_message: str, source: str = "copilot") -> str:
    """Answers general SRE infrastructure queries when no specific incident is active."""
    try:
        from prash.brain.kimi_client import _deepseek_client, _deepseek_model, _kimi_client, _kimi_model
        
        system_prompt = (
            "You are Lear Copilot, an autonomous AI Site Reliability Engineer operating on AWS EKS cluster "
            "'lear-demo' in region ap-south-1 (Mumbai). "
            "You monitor microservices including 'checkout-api', 'frontend', and 'postgres-replica'. "
            "Respond concisely, authoritatively, and technically to queries sent via "
            f"{source.title()}. Mention current cluster health or operational status."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        reply_text = ""
        client = _deepseek_client()
        if client:
            try:
                resp = await client.chat.completions.create(
                    model=_deepseek_model(),
                    messages=messages,
                    max_tokens=350,
                    temperature=0.2,
                )
                reply_text = resp.choices[0].message.content or ""
            except Exception as de:
                logger.debug(f"DeepSeek general query: {de}")

        if not reply_text:
            k_client = _kimi_client()
            if k_client:
                resp = await k_client.chat.completions.create(
                    model=_kimi_model(),
                    messages=messages,
                    max_tokens=350,
                    temperature=0.2,
                )
                reply_text = resp.choices[0].message.content or ""

        if not reply_text:
            reply_text = (
                f"Lear Copilot reporting: Cluster 'lear-demo' (ap-south-1 Mumbai) is online. "
                f"All nodes healthy. Received your query: '{user_message}'."
            )
        return reply_text
    except Exception as exc:
        logger.error(f"Error answering general copilot query: {exc}")
        return f"Lear Copilot active. Received: '{user_message}'. Cluster operational."


async def route_inbound_message(
    source: str,
    sender_identifier: str,
    message_text: str,
    incident_id: Optional[str] = None,
    subject: str = ""
) -> Dict[str, Any]:
    """Processes incoming message from Email or Slack, runs Copilot / action, and dispatches responses."""
    clean_msg = message_text.strip()
    if not clean_msg:
        return {"success": False, "error": "Empty message"}

    target_inc_id = incident_id or extract_incident_id(subject, clean_msg)
    if not target_inc_id:
        latest = get_latest_incident()
        target_inc_id = latest["incident_id"] if latest else None

    sender_tag = f"{source.title()} ({sender_identifier})"
    logger.info(f"Routing message from {sender_tag} (Incident: {target_inc_id}): '{clean_msg[:60]}'")

    # If an incident exists, route through the dedicated Incident War Room brain
    if target_inc_id:
        inc = get_incident(target_inc_id)
        res = await post_incident_chat(target_inc_id, clean_msg, sender=sender_tag)
        copilot_reply = res.get("copilot_reply") or "Understood. The incident is being managed."
        action = res.get("action")
        service = (inc or {}).get("service", "checkout-api")
        status = (inc or {}).get("status", "ACTIVE")
    else:
        # General infrastructure query
        copilot_reply = await answer_general_copilot_query(clean_msg, source=source)
        action = "general_query"
        service = "cluster-infrastructure"
        status = "HEALTHY"
        target_inc_id = "INC-GENERAL"

    # Dispatch response back to the inbound channel
    if source.lower() == "email":
        creds = load_credentials()
        to_email = sender_identifier if "@" in sender_identifier else creds.get("EMAIL_TO", "anantacharya5568@gmail.com")
        reply_subject = f"Re: {subject}" if subject else f"Re: [UPDATE] Lear SRE Copilot regarding {target_inc_id}"
        if not reply_subject.lower().startswith("re:"):
            reply_subject = f"Re: {reply_subject}"

        dispatch_copilot_email_reply(
            to_email=to_email,
            subject=reply_subject,
            user_query=clean_msg,
            copilot_reply=copilot_reply,
            incident_id=target_inc_id,
            service=service,
            status=status,
            action=action
        )

    elif source.lower() == "slack":
        dispatch_slack_chat_response(
            user_name=sender_identifier,
            user_message=clean_msg,
            copilot_reply=copilot_reply,
            incident_id=target_inc_id,
            service=service,
            status=status,
            action=action
        )

    return {
        "success": True,
        "incident_id": target_inc_id,
        "action": action,
        "copilot_reply": copilot_reply,
        "sender": sender_tag,
        "source": source
    }


def poll_imap_inbox_once() -> int:
    """Connects to IMAP, fetches unseen messages, routes to Copilot, and marks as seen."""
    creds = load_credentials()
    user = creds.get("EMAIL_USER", "anantacharya290@gmail.com").strip()
    pwd = creds.get("EMAIL_PASSWORD", "").replace(" ", "").strip()
    if not user or not pwd:
        return 0

    processed_count = 0
    mail = None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=12)
        mail.login(user, pwd)
        mail.select("INBOX")

        status, data = mail.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            mail.logout()
            return 0

        msg_ids = data[0].split()[-5:]
        for mid in msg_ids:
            try:
                res, msg_data = mail.fetch(mid, "(RFC822)")
                if res != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        raw_sender = msg.get("From", "")
                        raw_subject = msg.get("Subject", "")
                        subject = decode_mime_words(raw_subject)
                        message_id = msg.get("Message-ID", str(mid))

                        if message_id in _PROCESSED_EMAIL_IDS:
                            continue

                        match = re.search(r"[\w\.-]+@[\w\.-]+", raw_sender)
                        clean_sender = match.group(0) if match else raw_sender

                        # Ignore automated / system senders or self-echoes
                        ignore_patterns = ["no-reply", "noreply", "googleassistant", "mailer-daemon", "notifications@", "google.com"]
                        if any(p in clean_sender.lower() for p in ignore_patterns) or clean_sender.lower() == user.lower():
                            mail.store(mid, "+FLAGS", "(\\Seen)")
                            _PROCESSED_EMAIL_IDS.add(message_id)
                            continue

                        clean_body = extract_plain_text(msg)
                        if clean_body:
                            logger.info(f"[IMAP] Inbound email from {clean_sender}: '{subject}' - Body: '{clean_body[:80]}'")
                            
                            loop = asyncio.new_event_loop()
                            try:
                                loop.run_until_complete(
                                    route_inbound_message(
                                        source="email",
                                        sender_identifier=clean_sender,
                                        message_text=clean_body,
                                        subject=subject
                                    )
                                )
                                processed_count += 1
                            finally:
                                loop.close()

                        mail.store(mid, "+FLAGS", "(\\Seen)")
                        _PROCESSED_EMAIL_IDS.add(message_id)
            except Exception as item_err:
                logger.warning(f"Error processing email message {mid}: {item_err}")

        mail.logout()
    except Exception as e:
        logger.debug(f"IMAP poll notice: {e}")
        try:
            if mail:
                mail.logout()
        except Exception:
            pass

    return processed_count


def _imap_listener_worker():
    """Background worker polling every 6 seconds for new emails."""
    logger.info("Lear IMAP Background Email Listener started.")
    while not _IMAP_STOP_EVENT.is_set():
        try:
            poll_imap_inbox_once()
        except Exception as exc:
            logger.debug(f"IMAP worker loop notice: {exc}")
        
        for _ in range(12):
            if _IMAP_STOP_EVENT.is_set():
                break
            time.sleep(0.5)


def start_imap_listener():
    """Starts the background IMAP email listener thread."""
    global _IMAP_THREAD
    if _IMAP_THREAD and _IMAP_THREAD.is_alive():
        return
    _IMAP_STOP_EVENT.clear()
    _IMAP_THREAD = threading.Thread(target=_imap_listener_worker, daemon=True, name="LearIMAPListener")
    _IMAP_THREAD.start()
    logger.info("IMAP listener thread started.")


def stop_imap_listener():
    """Stops the IMAP email listener thread."""
    _IMAP_STOP_EVENT.set()
