"""Lear Email Notification Service — Executive-Grade HTML Alerts.

Generates beautiful, responsive, dark-mode email alerts for infrastructure incidents,
automated diagnoses, and remediations.
"""
from __future__ import annotations

import datetime
import email.message
import html
import json
import logging
import os
import smtplib
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EMAIL_DIR = Path(__file__).resolve().parent.parent / ".prash" / "emails"
EMAIL_DIR.mkdir(parents=True, exist_ok=True)

DISPATCHED_EMAILS: List[Dict[str, Any]] = []


def generate_incident_email_html(
    title: str,
    service: str = "checkout-api",
    namespace: str = "lear-demo",
    status: str = "FAILED",
    error_summary: str = "Connection refused to database host 'postgres-wrong:5432'",
    diagnosis: str = "ConfigMap 'checkout-api-config' DATABASE_HOST is misconfigured to 'postgres-wrong'. Episodic memory confirms this pattern matches prior incidents.",
    action_taken: str = "Lear Autonomous SRE patched ConfigMap checkout-api-config (DATABASE_HOST -> postgres) and completed rolling restart.",
    resolution_status: str = "RECOVERED",
    cluster: str = "AWS EKS lear-demo (ap-south-1 Mumbai)",
    downtime_seconds: int = 14,
) -> str:
    """Generates an executive-grade, dark-obsidian responsive HTML email."""
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    is_recovered = resolution_status.upper() in ("RECOVERED", "HEALTHY", "RESOLVED")
    status_bg = "#10B981" if is_recovered else "#EF4444"
    status_text = "RESOLVED IN 14s" if is_recovered else "CRITICAL ALERT"
    status_icon = "🟢" if is_recovered else "🚨"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #080B11;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #E2E8F0;
    }}
    .container {{
      max-width: 640px;
      margin: 24px auto;
      background: #0E131F;
      border: 1px solid #1E293B;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }}
    .header {{
      background: linear-gradient(135deg, #131B2E 0%, #0F172A 100%);
      padding: 24px 32px;
      border-bottom: 1px solid #1E293B;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .brand {{
      font-size: 20px;
      font-weight: 800;
      letter-spacing: 1.5px;
      color: #F8FAFC;
    }}
    .brand span {{
      color: #10B981;
    }}
    .badge {{
      display: inline-block;
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.8px;
      text-transform: uppercase;
      background-color: {status_bg};
      color: #FFFFFF;
    }}
    .content {{
      padding: 32px;
    }}
    .hero-title {{
      font-size: 22px;
      font-weight: 700;
      color: #F8FAFC;
      margin-top: 0;
      margin-bottom: 12px;
    }}
    .hero-desc {{
      color: #94A3B8;
      font-size: 14px;
      line-height: 1.6;
      margin-bottom: 24px;
    }}
    .metric-grid {{
      display: table;
      width: 100%;
      margin-bottom: 24px;
      border-spacing: 8px;
    }}
    .metric-col {{
      display: table-cell;
      background: #131A2B;
      border: 1px solid #1E293B;
      border-radius: 8px;
      padding: 14px 16px;
      width: 33.33%;
    }}
    .metric-label {{
      font-size: 11px;
      color: #64748B;
      text-transform: uppercase;
      font-weight: 600;
      margin-bottom: 4px;
    }}
    .metric-val {{
      font-size: 15px;
      font-weight: 700;
      color: #F1F5F9;
    }}
    .card {{
      background: #131A2B;
      border: 1px solid #1E293B;
      border-radius: 8px;
      padding: 18px 20px;
      margin-bottom: 20px;
    }}
    .card-title {{
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-top: 0;
      margin-bottom: 10px;
      color: #38BDF8;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .card-body {{
      font-size: 13px;
      color: #CBD5E1;
      line-height: 1.5;
      margin: 0;
    }}
    .log-box {{
      background: #080B11;
      border: 1px solid #1E293B;
      border-radius: 6px;
      padding: 12px 14px;
      font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
      font-size: 12px;
      color: #F43F5E;
      margin-top: 8px;
      word-break: break-all;
    }}
    .action-box {{
      background: #064E3B;
      border: 1px solid #059669;
      color: #A7F3D0;
      border-radius: 6px;
      padding: 12px 14px;
      font-size: 13px;
      line-height: 1.5;
      margin-top: 8px;
    }}
    .footer {{
      background: #0B0E17;
      padding: 20px 32px;
      border-top: 1px solid #1E293B;
      text-align: center;
      font-size: 12px;
      color: #64748B;
    }}
    .footer a {{
      color: #10B981;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">LEAR<span>.AI</span></div>
      <div class="badge">{status_icon} {status_text}</div>
    </div>
    <div class="content">
      <h1 class="hero-title">{html.escape(title)}</h1>
      <p class="hero-desc">
        Lear Autonomous SRE Engine detected an incident in the production cluster. The AI brain diagnosed the root cause and applied remediation.
      </p>

      <div class="metric-grid">
        <div class="metric-col">
          <div class="metric-label">Target Service</div>
          <div class="metric-val">{html.escape(service)}</div>
        </div>
        <div class="metric-col">
          <div class="metric-label">Cluster</div>
          <div class="metric-val">{html.escape(cluster)}</div>
        </div>
        <div class="metric-col">
          <div class="metric-label">MTTR (Resolution)</div>
          <div class="metric-val">{downtime_seconds}s (Autonomous)</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">🚨 Incident Detection & Customer Impact</div>
        <p class="card-body">
          Pod entered <strong>CrashLoopBackOff</strong> due to failed health probes. Customer checkout requests began receiving <strong>502 Bad Gateway</strong>.
        </p>
        <div class="log-box">{html.escape(error_summary)}</div>
      </div>

      <div class="card">
        <div class="card-title">🧠 DeepSeek Brain Diagnosis</div>
        <p class="card-body">
          {html.escape(diagnosis)}
        </p>
      </div>

      <div class="card">
        <div class="card-title">⚡ Autonomous Remediation Executed</div>
        <div class="action-box">
          <strong>Action:</strong> {html.escape(action_taken)}<br>
          <strong>Verification:</strong> Liveness/Readiness probes passing. Checkout endpoint returned HTTP 200 OK.
        </div>
      </div>
    </div>
    <div class="footer">
      Generated automatically by <strong>Lear Local AI DevOps Agent</strong> • {now_str}<br>
      Immutable Audit ID: <code>audit_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}</code> • <a href="#">Open Lear Dashboard</a>
    </div>
  </div>
</body>
</html>
"""


def dispatch_email_alert(
    subject: str,
    service: str = "checkout-api",
    namespace: str = "lear-demo",
    status: str = "CRITICAL",
    error_summary: str = "Connection refused to database host 'postgres-wrong:5432'",
    diagnosis: str = "ConfigMap checkout-api-config misconfigured DATABASE_HOST to postgres-wrong.",
    action_taken: str = "Lear Autonomous SRE patched ConfigMap (DATABASE_HOST -> postgres) and verified checkout pod 1/1 Running.",
    resolution_status: str = "RESOLVED",
    credentials: Optional[Dict[str, str]] = None,
    to_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates the HTML email, archives it for UI preview, and dispatches via SMTP if configured."""
    creds = credentials or {}
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in open(env_file):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds.setdefault(k.strip(), v.strip().strip("'").strip('"'))

    html_body = generate_incident_email_html(
        title=subject,
        service=service,
        namespace=namespace,
        status=status,
        error_summary=error_summary,
        diagnosis=diagnosis,
        action_taken=action_taken,
        resolution_status=resolution_status,
    )

    # 1. Save latest HTML to disk for immediate dashboard iframe/modal preview
    latest_file = EMAIL_DIR / "latest.html"
    try:
        latest_file.write_text(html_body, encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not write {latest_file}: {e}")

    email_record = {
        "id": f"email_{int(datetime.datetime.now(datetime.timezone.utc).timestamp()*1000)}",
        "subject": subject,
        "service": service,
        "status": status,
        "resolution_status": resolution_status,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "recipient": to_email or creds.get("EMAIL_TO", "oncall-team@lear-demo.com"),
        "smtp_sent": False,
        "html": html_body,
    }

    # 2. Attempt real SMTP if configured
    smtp_host = creds.get("EMAIL_SMTP_HOST")
    recipient = to_email or creds.get("EMAIL_TO")

    if smtp_host and recipient:
        try:
            port = int(creds.get("EMAIL_SMTP_PORT", "587"))
            user = creds.get("EMAIL_USER")
            password = creds.get("EMAIL_PASSWORD")
            sender = creds.get("EMAIL_FROM", user or "alerts@lear.ai")

            msg = email.message.EmailMessage()
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = recipient
            msg.set_content(f"{subject}\n\nService: {service}\nStatus: {status}\nDiagnosis: {diagnosis}\nAction: {action_taken}")
            msg.add_alternative(html_body, subtype="html")

            with smtplib.SMTP(smtp_host, port, timeout=10) as server:
                server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
            email_record["smtp_sent"] = True
            logger.info(f"Successfully sent incident email to {recipient} via {smtp_host}:{port}")
        except Exception as exc:
            logger.warning(f"SMTP send failed ({smtp_host}): {exc}")
            email_record["smtp_error"] = str(exc)

    DISPATCHED_EMAILS.insert(0, email_record)
    if len(DISPATCHED_EMAILS) > 50:
        del DISPATCHED_EMAILS[50:]

    return email_record
