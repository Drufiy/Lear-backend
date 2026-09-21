"""Slack Alerting Service for Lear Autonomous SRE Incidents.

Dispatches executive Block Kit and mrkdwn alerts to configured Slack incoming webhooks.
Includes one-click buttons / links to:
- Open Shared Incident War Room
- One-Click Approve & Apply Fix
- One-Click Deny / Escalate
"""

import json
import logging
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def dispatch_slack_alert(
    title: str,
    service: str = "checkout-api",
    namespace: str = "lear-demo",
    status: str = "CRITICAL",
    error_summary: str = "",
    diagnosis: str = "",
    action_taken: str = "",
    incident_id: Optional[str] = None,
    base_url: str = "http://localhost:8000",
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Dispatches an incident alert to Slack via incoming webhook if configured."""
    url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.exists():
            for line in open(env_file, encoding="utf-8", errors="ignore"):
                line = line.strip()
                if line.startswith("SLACK_WEBHOOK_URL=") or line.startswith("SLACK_WEBHOOK="):
                    url = line.split("=", 1)[1].strip().strip("'").strip('"')
                    break

    if not url:
        return {"sent": False, "reason": "SLACK_WEBHOOK_URL not configured in environment or .env"}

    inc_id = incident_id or "INC-LIVE"
    chat_url = f"http://localhost:1420/?tab=chat&session={inc_id}"
    approve_url = f"{base_url}/api/incident/{inc_id}/approve"
    deny_url = f"{base_url}/api/incident/{inc_id}/deny"

    is_recovered = status.upper() in ("RESOLVED", "RECOVERED", "HEALTHY")
    icon = "🟢" if is_recovered else "🚨"

    mrkdwn_text = (
        f"{icon} *{title}*\n"
        f"• *Service:* `{service}` (`{namespace}`)\n"
        f"• *Status:* `{status}`\n"
        f"• *Incident ID:* `{inc_id}`\n\n"
        f"*Diagnosis:* {diagnosis}\n"
        f"*Remediation:* {action_taken}\n\n"
        f"<{chat_url}|💬 Open Incident Chat in Lear>  |  <{approve_url}|✅ Approve Fix>  |  <{deny_url}|❌ Deny Fix>"
    )

    payload = {
        "text": mrkdwn_text,
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{icon} Lear SRE: {status} Alert"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*\n\n*Diagnosis:*\n{diagnosis}\n\n*Action Proposed:*\n{action_taken}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Service:*\n`{service}`"},
                    {"type": "mrkdwn", "text": f"*Incident:*\n`{inc_id}`"}
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "💬 Open Incident Chat in Lear"},
                        "url": chat_url,
                        "style": "primary"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve Fix"},
                        "url": approve_url
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Deny"},
                        "url": deny_url,
                        "style": "danger"
                    }
                ]
            }
        ]
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            logger.info(f"Slack webhook dispatched successfully: HTTP {resp.status}")
            return {"sent": True, "status": resp.status, "body": body}
    except urllib.error.HTTPError as he:
        # Fallback to simple text if Block Kit rejected by legacy webhook
        try:
            simple_req = urllib.request.Request(
                url,
                data=json.dumps({"text": mrkdwn_text}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(simple_req, timeout=5) as r2:
                return {"sent": True, "fallback": True, "status": r2.status}
        except Exception:
            pass
        logger.warning(f"Slack webhook HTTP {he.code}: {he.reason}")
        return {"sent": False, "error": f"HTTP {he.code}: {he.reason}"}
    except Exception as exc:
        logger.warning(f"Slack webhook dispatch failed: {exc}")
        return {"sent": False, "error": str(exc)}


def dispatch_slack_chat_response(
    user_name: str,
    user_message: str,
    copilot_reply: str,
    incident_id: Optional[str] = None,
    service: str = "checkout-api",
    status: str = "ACTIVE",
    action: Optional[str] = None,
    base_url: str = "http://localhost:8000",
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Posts an interactive conversational response from Lear Copilot into Slack."""
    url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.exists():
            for line in open(env_file, encoding="utf-8", errors="ignore"):
                line = line.strip()
                if line.startswith("SLACK_WEBHOOK_URL=") or line.startswith("SLACK_WEBHOOK="):
                    url = line.split("=", 1)[1].strip().strip("'").strip('"')
                    break

    if not url:
        return {"sent": False, "reason": "SLACK_WEBHOOK_URL not configured"}

    inc_id = incident_id or "INC-GENERAL"
    chat_url = f"http://localhost:1420/?tab=chat&session={inc_id}"
    approve_url = f"{base_url}/api/incident/{inc_id}/approve"
    deny_url = f"{base_url}/api/incident/{inc_id}/deny"

    status_upper = (status or "ACTIVE").upper()
    is_resolved = status_upper in ("RESOLVED", "RECOVERED", "HEALTHY") or action == "approved"
    icon = "✅" if is_resolved else "🤖"

    header_text = f"{icon} Lear SRE (Live)"
    quoted_user = f"> *<@{user_name}>:* {user_message}"

    blocks: list = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header_text
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": quoted_user
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": copilot_reply
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Service: *{service}*  |  Incident: *{inc_id}*  |  Status: *{status_upper}*"
                }
            ]
        }
    ]

    # Add action buttons
    if inc_id != "INC-GENERAL":
        if not is_resolved:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "💬 Open Incident Chat in Lear"},
                        "url": chat_url,
                        "style": "primary"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve & Apply Fix"},
                        "url": approve_url
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Deny"},
                        "url": deny_url,
                        "style": "danger"
                    }
                ]
            })
        else:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "💬 View Incident Chat in Lear"},
                        "url": chat_url
                    }
                ]
            })

    payload = {
        "text": f"🤖 Lear to @{user_name}: {copilot_reply[:160]}",
        "blocks": blocks
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            logger.info(f"Slack chat message sent to webhook: HTTP {resp.status}")
            return {"sent": True, "status": resp.status, "body": body}
    except urllib.error.HTTPError as he:
        # Fallback to simple mrkdwn
        try:
            simple_text = f"🤖 *Lear* responding to *@{user_name}*:\n\n{copilot_reply}\n\n<{chat_url}|Open Incident Chat in Lear>"
            simple_req = urllib.request.Request(
                url,
                data=json.dumps({"text": simple_text}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(simple_req, timeout=5) as r2:
                return {"sent": True, "fallback": True, "status": r2.status}
        except Exception:
            pass
        return {"sent": False, "error": f"HTTP {he.code}: {he.reason}"}
    except Exception as exc:
        logger.warning(f"Slack chat webhook failed: {exc}")
        return {"sent": False, "error": str(exc)}

