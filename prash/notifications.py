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

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

SLACK_WEBHOOK_KEY = "SLACK_WEBHOOK_URL"
DISCORD_WEBHOOK_KEY = "DISCORD_WEBHOOK_URL"


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


def team_notifiers(credentials: Mapping[str, Any]) -> list[Notifier]:
    """Every channel that has a webhook configured, in a stable order."""
    return [
        n
        for n in (SlackNotifier(credentials), DiscordNotifier(credentials))
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
