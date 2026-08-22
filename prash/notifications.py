"""Team notification channels (Sprint 2 Tier 2, PRASH_V2.md §7b — Aryan).

Closes the exact gap §7b's Team/notifications row flags: the watcher's plyer
ping reaches one laptop. Slack/Discord webhooks give the whole team the same
ping — §3's "it pings the user (desktop notification, Slack, whatever channel
is configured)" made channel-configurable pings part of the product from day
one, this just makes it real.

Deliberately NOT a Connector. `base.Connector`'s shape (authenticate ->
locate -> fetch logs -> poll state) models *reading* infrastructure state; a
notification channel is a write-only sink, so forcing fetch_logs/poll_state
on it would be fake. Same spirit though: configured() -> send().

Webhooks, deliberately: incoming-webhook URLs are the lowest-friction
mechanism both Slack and Discord expose for "POST a message to a channel" —
no OAuth app, no bot token, no permissions matrix, works from a plain CLI,
and matches the local-first posture (§4) exactly: the webhook URL lives in
the user's .env, is read locally, and is never sent to Drufiy. A richer
chat-bot API (threaded replies, slash commands) is real functionality nobody
has asked for yet — not built speculatively.

Stdlib-only (urllib), matching github.py/gitlab.py's "zero network deps
beyond what ships with Python" convention.

A failed webhook send never raises: it logs and returns False. The caller
(the watch loop in particular) must never die because a team channel is
temporarily down — that would be the notification failing the very service
it exists to notify about.
"""

from __future__ import annotations

import base64
import json
import logging
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from email.message import EmailMessage
from typing import Any

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_KEY = "SLACK_WEBHOOK_URL"
DISCORD_WEBHOOK_KEY = "DISCORD_WEBHOOK_URL"

EMAIL_SMTP_HOST_KEY = "EMAIL_SMTP_HOST"
EMAIL_SMTP_PORT_KEY = "EMAIL_SMTP_PORT"
EMAIL_USER_KEY = "EMAIL_USER"
EMAIL_PASSWORD_KEY = "EMAIL_PASSWORD"
EMAIL_FROM_KEY = "EMAIL_FROM"
EMAIL_TO_KEY = "EMAIL_TO"

TWILIO_ACCOUNT_SID_KEY = "TWILIO_ACCOUNT_SID"
TWILIO_AUTH_TOKEN_KEY = "TWILIO_AUTH_TOKEN"
WHATSAPP_FROM_KEY = "WHATSAPP_FROM_NUMBER"
WHATSAPP_TO_KEY = "WHATSAPP_TO_NUMBERS"


class Notifier:
    """One team notification channel: configured() -> send()."""

    name = "base"
    key: str = ""

    def __init__(self, credentials: Mapping[str, Any]):
        self.credentials = credentials

    def configured(self) -> bool:
        return bool(self.credentials.get(self.key))

    def _payload(self, title: str, message: str) -> dict[str, str]:
        raise NotImplementedError

    def send(self, title: str, message: str) -> bool:
        """True if the webhook accepted the message. Never raises."""
        url = self.credentials.get(self.key)
        if not url:
            return False
        data = json.dumps(self._payload(title, message)).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
            return True
        except urllib.error.HTTPError as exc:
            # Discord answers non-2xx with a human-readable body (e.g. 400
            # "Webhook message must be 2000 or fewer characters"); surfacing
            # it makes channel-config mistakes diagnosable instead of silent.
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            logger.warning(f"{self.name}: webhook rejected ({exc.code}): {detail}")
        except Exception as exc:  # noqa: BLE001 — a failed team ping must never kill the caller
            logger.warning(f"{self.name}: webhook send failed: {exc}")
        return False


class SlackNotifier(Notifier):
    """Slack incoming-webhook. `text` is mrkdwn: *bold*, `code`, links."""

    name = "slack"
    key = SLACK_WEBHOOK_KEY

    def _payload(self, title: str, message: str) -> dict[str, str]:
        return {"text": f"*{title}*\n{message}"}


class DiscordNotifier(Notifier):
    """Discord webhook. `content` is markdown: **bold**, `code`, links."""

    name = "discord"
    key = DISCORD_WEBHOOK_KEY

    def _payload(self, title: str, message: str) -> dict[str, str]:
        return {"content": f"**{title}**\n{message}"}


class EmailNotifier(Notifier):
    """Email via SMTP, sent in basic HTML format."""
    name = "email"
    key = EMAIL_SMTP_HOST_KEY

    def configured(self) -> bool:
        return bool(self.credentials.get(self.key)) and bool(self.credentials.get(EMAIL_TO_KEY))

    def send(self, title: str, message: str) -> bool:
        host = self.credentials.get(self.key)
        if not host:
            return False
            
        port = int(self.credentials.get(EMAIL_SMTP_PORT_KEY, "587"))
        user = self.credentials.get(EMAIL_USER_KEY)
        password = self.credentials.get(EMAIL_PASSWORD_KEY)
        sender = self.credentials.get(EMAIL_FROM_KEY, user)
        recipients_raw = self.credentials.get(EMAIL_TO_KEY, "")
        
        if not recipients_raw:
            return False
            
        recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
        
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        
        html_content = f"<html><body><h3>{title}</h3><p>{message.replace(chr(10), '<br>')}</p></body></html>"
        msg.set_content(message)
        msg.add_alternative(html_content, subtype='html')
        
        try:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
            return True
        except Exception as exc:
            logger.warning(f"{self.name}: send failed: {exc}")
        return False


class WhatsAppNotifier(Notifier):
    """WhatsApp via Twilio API."""
    name = "whatsapp"
    key = TWILIO_ACCOUNT_SID_KEY

    def configured(self) -> bool:
        return bool(self.credentials.get(self.key)) and bool(self.credentials.get(WHATSAPP_TO_KEY))

    def send(self, title: str, message: str) -> bool:
        sid = self.credentials.get(self.key)
        token = self.credentials.get(TWILIO_AUTH_TOKEN_KEY)
        from_number = self.credentials.get(WHATSAPP_FROM_KEY)
        to_numbers_raw = self.credentials.get(WHATSAPP_TO_KEY, "")
        
        if not (sid and token and from_number and to_numbers_raw):
            return False
            
        recipients = [r.strip() for r in to_numbers_raw.split(",") if r.strip()]
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        auth_string = f"{sid}:{token}"
        auth_header = "Basic " + base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
        
        body_text = f"*{title}*\n{message}"
        success = False
        
        for recipient in recipients:
            if not recipient.startswith("whatsapp:"):
                recipient = f"whatsapp:{recipient}"
            from_sender = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"
                
            data = urllib.parse.urlencode({
                "To": recipient,
                "From": from_sender,
                "Body": body_text
            }).encode("utf-8")
            
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Authorization": auth_header},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp.read()
                success = True
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                logger.warning(f"{self.name}: webhook rejected for {recipient} ({exc.code}): {detail}")
            except Exception as exc:
                logger.warning(f"{self.name}: webhook send failed for {recipient}: {exc}")
                
        return success


def team_notifiers(credentials: Mapping[str, Any]) -> list[Notifier]:
    """Every channel that has a webhook configured, in a stable order."""
    return [
        n
        for n in (
            SlackNotifier(credentials), 
            DiscordNotifier(credentials),
            EmailNotifier(credentials),
            WhatsAppNotifier(credentials),
        )
        if n.configured()
    ]


def send_team_notifications(
    credentials: Mapping[str, Any], title: str, message: str
) -> dict[str, bool]:
    """Send to every configured channel. Never raises.

    Returns {channel_name: succeeded} — the caller decides how honestly to
    surface partial failure. An empty dict means no channel is configured.
    """
    return {n.name: n.send(title, message) for n in team_notifiers(credentials)}
