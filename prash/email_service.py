"""Executive HTML Email Alerting and Autonomous SRE Dispatch Service.

Generates responsive dark-obsidian HTML email reports for production incidents,
containing:
1. Executive Incident Summary & Severity Badge
2. DeepSeek AI Root Cause Diagnosis & Code/Config Diff
3. Three Interactive Action Buttons:
   - Button 1: [💬 Open Shared Incident War Room] (Direct shared conversation with Copilot)
   - Button 2: [✅ Approve & Apply Fix] (One-click instant auto-remediation)
   - Button 3: [❌ Deny / Escalate] (One-click reject / human handoff)
4. Inbound Email Reply Instructions for bidirectional agent communication.
"""

import datetime
import email.message
import html
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
    action_taken: str = "Lear Autonomous SRE proposes: Patch ConfigMap checkout-api-config (DATABASE_HOST -> postgres) and trigger rolling restart.",
    resolution_status: str = "INVESTIGATING",
    cluster: str = "AWS EKS lear-demo (ap-south-1 Mumbai)",
    downtime_seconds: int = 14,
    incident_id: Optional[str] = None,
    base_url: str = "http://localhost:8000",
    **kwargs: Any,
) -> str:
    """Generates an executive-grade, interactive dark-obsidian responsive HTML email."""
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    is_recovered = resolution_status.upper() in ("RECOVERED", "HEALTHY", "RESOLVED")
    status_bg = "#10B981" if is_recovered else "#EF4444"
    status_text = f"RESOLVED IN {downtime_seconds}s" if is_recovered else "CRITICAL ALERT — ACTION REQUIRED"
    status_icon = "🟢" if is_recovered else "🚨"

    inc_id = incident_id or f"INC-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"
    war_room_url = f"{base_url}/incident/{inc_id}"
    approve_url = f"{base_url}/api/incident/{inc_id}/approve"
    deny_url = f"{base_url}/api/incident/{inc_id}/deny"

    # Action buttons block
    if not is_recovered:
        action_buttons_html = f"""
      <div style="margin: 28px 0; padding: 20px; background: #131A2B; border: 1px solid #1E293B; border-radius: 8px; text-align: center;">
        <div style="font-size: 13px; font-weight: 700; text-transform: uppercase; color: #38BDF8; letter-spacing: 0.5px; margin-bottom: 14px;">
          ⚡ Interactive Incident Actions (One-Click)
        </div>
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin: 0 auto; width: 100%;">
          <tr>
            <td align="center" style="padding: 4px;">
              <a href="{war_room_url}" target="_blank" style="display: block; background: #2563EB; color: #FFFFFF; font-weight: 700; font-size: 13px; padding: 12px 18px; border-radius: 6px; text-decoration: none; border: 1px solid #3B82F6;">
                💬 Open Shared War Room
              </a>
            </td>
            <td align="center" style="padding: 4px;">
              <a href="{approve_url}" target="_blank" style="display: block; background: #059669; color: #FFFFFF; font-weight: 700; font-size: 13px; padding: 12px 18px; border-radius: 6px; text-decoration: none; border: 1px solid #10B981;">
                ✅ Approve & Apply Fix
              </a>
            </td>
            <td align="center" style="padding: 4px;">
              <a href="{deny_url}" target="_blank" style="display: block; background: #DC2626; color: #FFFFFF; font-weight: 700; font-size: 13px; padding: 12px 18px; border-radius: 6px; text-decoration: none; border: 1px solid #EF4444;">
                ❌ Deny / Escalate
              </a>
            </td>
          </tr>
        </table>
        <div style="margin-top: 14px; font-size: 12px; color: #94A3B8; line-height: 1.5;">
          💡 <strong>Email Quick-Reply:</strong> You can also reply directly to this email with <em>"Approve"</em>, <em>"Deny"</em>, or ask technical questions. Lear Copilot will analyze your message and send back an auto-generated reply!
        </div>
      </div>
        """
    else:
        action_buttons_html = f"""
      <div style="margin: 28px 0; padding: 16px; background: rgba(16, 185, 129, 0.1); border: 1px solid #059669; border-radius: 8px; text-align: center;">
        <span style="font-size: 14px; font-weight: 700; color: #10B981;">
          ✅ Autonomous Remediation Completed & Verified
        </span>
        <div style="margin-top: 8px;">
          <a href="{war_room_url}" target="_blank" style="color: #38BDF8; font-size: 13px; text-decoration: underline;">
            View Incident Post-Mortem & Timeline in War Room →
          </a>
        </div>
      </div>
        """

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
      display: flex;
      gap: 12px;
      margin-bottom: 24px;
    }}
    .metric-col {{
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
      line-height: 1.6;
    }}
    .footer {{
      padding: 24px 32px;
      background: #090D16;
      border-top: 1px solid #1E293B;
      font-size: 12px;
      color: #64748B;
      text-align: center;
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
        Lear Autonomous SRE Engine detected an incident in the production cluster. The AI brain diagnosed the root cause and is standing by for authorization or autonomous remediation.
      </p>

      <div class="metric-grid">
        <div class="metric-col">
          <div class="metric-label">Incident ID</div>
          <div class="metric-val">{html.escape(inc_id)}</div>
        </div>
        <div class="metric-col">
          <div class="metric-label">Target Service</div>
          <div class="metric-val">{html.escape(service)}</div>
        </div>
        <div class="metric-col">
          <div class="metric-label">Cluster</div>
          <div class="metric-val">{html.escape(cluster)}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">🚨 Incident Detection & Customer Impact</div>
        <p class="card-body">
          Pod entered <strong>CrashLoopBackOff</strong> due to failed database connection. Customer checkout requests are currently receiving <strong>502 Bad Gateway</strong>.
        </p>
        <div class="log-box">{html.escape(error_summary)}</div>
      </div>

      <div class="card">
        <div class="card-title">🧠 DeepSeek AI Brain Diagnosis</div>
        <p class="card-body">
          {html.escape(diagnosis)}
        </p>
      </div>

      <div class="card">
        <div class="card-title">⚡ Autonomous Remediation Plan</div>
        <div class="action-box">
          <strong>Action:</strong> {html.escape(action_taken)}<br>
          <strong>Safety Check:</strong> Zero code change; configuration merge patch only; rollback safe.
        </div>
      </div>

      {action_buttons_html}

    </div>
    <div class="footer">
      Generated automatically by <strong>Lear Local AI DevOps Agent</strong> • {now_str}<br>
      Incident: <code>{html.escape(inc_id)}</code> • <a href="{war_room_url}">Open Incident War Room</a>
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
    downtime_seconds: int = 14,
    incident_id: Optional[str] = None,
    base_url: str = "http://localhost:8000",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Generates the HTML email, archives it for preview, and dispatches via SMTP if configured."""
    creds = credentials or {}
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in open(env_file):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds.setdefault(k.strip(), v.strip().strip("'").strip('"'))

    inc_id = incident_id or f"INC-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"

    html_body = generate_incident_email_html(
        title=subject,
        service=service,
        namespace=namespace,
        status=status,
        error_summary=error_summary,
        diagnosis=diagnosis,
        action_taken=action_taken,
        resolution_status=resolution_status,
        downtime_seconds=downtime_seconds,
        incident_id=inc_id,
        base_url=base_url,
    )

    # 1. Save latest HTML to disk for immediate dashboard iframe/modal preview
    latest_file = EMAIL_DIR / "latest.html"
    inc_file = EMAIL_DIR / f"{inc_id}.html"
    try:
        latest_file.write_text(html_body, encoding="utf-8")
        inc_file.write_text(html_body, encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not write email file: {e}")

    recipient = to_email or creds.get("EMAIL_TO", "anantacharya290@gmail.com")

    email_record = {
        "id": f"email_{int(datetime.datetime.now(datetime.timezone.utc).timestamp()*1000)}",
        "incident_id": inc_id,
        "subject": subject,
        "service": service,
        "status": status,
        "resolution_status": resolution_status,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "recipient": recipient,
        "sender": creds.get("EMAIL_FROM", "anantacharya5568@gmail.com"),
        "smtp_sent": False,
        "html": html_body,
    }

    # 2. Attempt real SMTP if configured
    smtp_host = creds.get("EMAIL_SMTP_HOST")
    if smtp_host and recipient:
        try:
            port = int(creds.get("EMAIL_SMTP_PORT", "587"))
            user = creds.get("EMAIL_USER")
            password = creds.get("EMAIL_PASSWORD")
            sender = creds.get("EMAIL_FROM", "anantacharya5568@gmail.com")

            msg = email.message.EmailMessage()
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = recipient
            msg.set_content(
                f"{subject}\n\nService: {service}\nStatus: {status}\nDiagnosis: {diagnosis}\n"
                f"Action: {action_taken}\n\nOpen War Room: {base_url}/incident/{inc_id}\n"
                f"Approve Fix: {base_url}/api/incident/{inc_id}/approve\n"
                f"Deny Fix: {base_url}/api/incident/{inc_id}/deny\n"
            )
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
