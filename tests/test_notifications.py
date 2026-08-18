"""Sprint 2 Tier 2 — team notification channels (PRASH_V2.md §7b, Aryan).

Slack/Discord webhook notifiers + the factory/send helpers the watcher and
CLI use. send() is the only network touch; every test exercises it with
urllib.request.urlopen mocked so nothing leaves the machine (same stance as
every other connector test in this suite).
"""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock

import prash.notifications as notif_mod
from prash.notifications import (
    DISCORD_WEBHOOK_KEY,
    SLACK_WEBHOOK_KEY,
    DiscordNotifier,
    Notifier,
    SlackNotifier,
    send_team_notifications,
    team_notifiers,
)

SLACK_URL = "https://hooks.slack.com/services/T000/B000/XXXX"
DISCORD_URL = "https://discord.com/api/webhooks/000/xxx"


def _ok_response() -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = b"ok"
    return resp


# ── configured() ─────────────────────────────────────────────────────────────

def test_notifiers_report_unconfigured_when_webhook_absent():
    assert SlackNotifier({}).configured() is False
    assert DiscordNotifier({}).configured() is False


def test_notifiers_report_configured_when_webhook_present():
    assert SlackNotifier({SLACK_WEBHOOK_KEY: SLACK_URL}).configured() is True
    assert DiscordNotifier({DISCORD_WEBHOOK_KEY: DISCORD_URL}).configured() is True


def test_blank_webhook_value_counts_as_unconfigured():
    """Same lesson as the 2026-08-13 KUBECONFIG bug: a key left BLANK in .env
    is present with value '' -- must mean 'not configured', not a webhook URL
    pointing at the empty string."""
    assert SlackNotifier({SLACK_WEBHOOK_KEY: ""}).configured() is False


# ── send(): payload shape + failure honesty ─────────────────────────────────

def test_slack_send_posts_mrkdwn_payload_and_returns_true(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout=15):
        captured["req"] = req
        return _ok_response()

    monkeypatch.setattr(notif_mod.urllib.request, "urlopen", fake_urlopen)

    title = "Prash: CrashLoopBackOff — api-7f9d"
    message = "production/api-7f9d (restart_count=3). Run `prash fix production/api-7f9d` to diagnose."
    assert SlackNotifier({SLACK_WEBHOOK_KEY: SLACK_URL}).send(title, message) is True

    req = captured["req"]
    assert req.full_url == SLACK_URL
    assert req.method == "POST"
    assert json.loads(req.data.decode("utf-8")) == {"text": f"*{title}*\n{message}"}


def test_discord_send_posts_markdown_payload_and_returns_true(monkeypatch):
    captured: dict = {}

    def fake_urlopen(req, timeout=15):
        captured["req"] = req
        return _ok_response()

    monkeypatch.setattr(notif_mod.urllib.request, "urlopen", fake_urlopen)

    assert DiscordNotifier({DISCORD_WEBHOOK_KEY: DISCORD_URL}).send("Prash", "hello team") is True
    req = captured["req"]
    assert req.full_url == DISCORD_URL
    assert json.loads(req.data.decode("utf-8")) == {"content": "**Prash**\nhello team"}


def test_send_unconfigured_never_touches_the_network(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("must not touch the network")

    monkeypatch.setattr(notif_mod.urllib.request, "urlopen", boom)
    assert SlackNotifier({}).send("title", "message") is False


def test_send_returns_false_when_webhook_rejects_with_http_error(monkeypatch, caplog):
    def fake_urlopen(req, timeout=15):
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {},
            io.BytesIO(b"Webhook message must be 2000 or fewer characters"),
        )

    monkeypatch.setattr(notif_mod.urllib.request, "urlopen", fake_urlopen)

    import logging

    with caplog.at_level(logging.WARNING):
        assert DiscordNotifier({DISCORD_WEBHOOK_KEY: DISCORD_URL}).send("t", "m") is False
    assert "discord: webhook rejected (400)" in caplog.text


def test_send_returns_false_on_network_error(monkeypatch):
    def fake_urlopen(req, timeout=15):
        raise OSError("connection refused")

    monkeypatch.setattr(notif_mod.urllib.request, "urlopen", fake_urlopen)
    assert SlackNotifier({SLACK_WEBHOOK_KEY: SLACK_URL}).send("t", "m") is False


def test_base_notifier_payload_is_not_implemented():
    n = Notifier({})
    try:
        n._payload("t", "m")
    except NotImplementedError:
        return
    raise AssertionError("base Notifier must not silently produce a payload")


# ── team_notifiers / send_team_notifications ─────────────────────────────────

def test_team_notifiers_returns_only_configured_channels():
    names = [n.name for n in team_notifiers({SLACK_WEBHOOK_KEY: SLACK_URL})]
    assert names == ["slack"]


def test_send_team_notifications_pushes_to_every_configured_channel(monkeypatch):
    sent: list = []
    monkeypatch.setattr(notif_mod.urllib.request, "urlopen",
                        lambda req, timeout=15: sent.append(req.full_url) or _ok_response())

    creds = {SLACK_WEBHOOK_KEY: SLACK_URL, DISCORD_WEBHOOK_KEY: DISCORD_URL}
    results = send_team_notifications(creds, "Prash", "hello team")
    assert results == {"slack": True, "discord": True}
    assert set(sent) == {SLACK_URL, DISCORD_URL}


def test_send_team_notifications_empty_when_nothing_configured(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("no channel configured — must not touch the network")

    monkeypatch.setattr(notif_mod.urllib.request, "urlopen", boom)
    assert send_team_notifications({}, "Prash", "hi") == {}


def test_send_team_notifications_surfaces_partial_failure_honestly(monkeypatch):
    def fake_urlopen(req, timeout=15):
        if "discord" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(b"nope"))
        return _ok_response()

    monkeypatch.setattr(notif_mod.urllib.request, "urlopen", fake_urlopen)

    creds = {SLACK_WEBHOOK_KEY: SLACK_URL, DISCORD_WEBHOOK_KEY: DISCORD_URL}
    results = send_team_notifications(creds, "Prash", "hi")
    assert results == {"slack": True, "discord": False}