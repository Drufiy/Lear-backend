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
    chat_url = f"http://localhost:1420/?tab=chat&session={inc_id}"
    approve_url = f"{base_url}/api/incident/{inc_id}/approve"
    deny_url = f"{base_url}/api/incident/{inc_id}/deny"

    # Action buttons block
    if not is_recovered:
        action_buttons_html = f"""
      <div style="margin: 28px 0; padding: 20px; background: #0E131F; border: 1px solid #1E293B; border-radius: 8px; text-align: center;">
        <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; color: #00F0FF; letter-spacing: 0.5px; margin-bottom: 14px;">
          ⚡ Operational Incident Decision
        </div>
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin: 0 auto; width: 100%;">
          <tr>
            <td align="center" style="padding: 4px;">
              <a href="{chat_url}" target="_blank" style="display: block; background: #00F0FF; color: #041019; font-weight: 700; font-size: 13px; padding: 12px 18px; border-radius: 6px; text-decoration: none; border: 1px solid #38BDF8;">
                💬 Open Incident Chat in Lear
              </a>
            </td>
            <td align="center" style="padding: 4px;">
              <a href="{approve_url}" target="_blank" style="display: block; background: #10B981; color: #041F16; font-weight: 700; font-size: 13px; padding: 12px 18px; border-radius: 6px; text-decoration: none; border: 1px solid #059669;">
                ✅ Approve & Apply Fix
              </a>
            </td>
            <td align="center" style="padding: 4px;">
              <a href="{deny_url}" target="_blank" style="display: block; background: #1E293B; color: #F43F5E; font-weight: 700; font-size: 13px; padding: 12px 18px; border-radius: 6px; text-decoration: none; border: 1px solid #334155;">
                ❌ Deny Changes
              </a>
            </td>
          </tr>
        </table>
        <div style="margin-top: 14px; font-size: 12px; color: #94A3B8; line-height: 1.5;">
          💡 <strong>Direct Email Reply:</strong> You can reply directly to this email with <em>"Approve"</em>, <em>"Deny"</em>, or technical questions. Lear Copilot will respond directly to your email.
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
          <a href="{chat_url}" target="_blank" style="color: #00F0FF; font-size: 13px; text-decoration: underline;">
            View Incident Timeline & Conversation in Lear Dashboard →
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
      background: linear-gradient(135deg, #111622 0%, #080B11 100%);
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
      color: #00F0FF;
    }}
    .brand-sub {{
      font-size: 11px;
      color: #64748B;
      font-weight: 400;
      letter-spacing: 0.5px;
      margin-top: 2px;
    }}
    .badge {{
      background: {status_bg};
      color: #FFFFFF;
      font-size: 11px;
      font-weight: 700;
      padding: 6px 12px;
      border-radius: 9999px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}
    .content {{
      padding: 32px;
    }}
    .hero-title {{
      font-size: 18px;
      font-weight: 700;
      margin: 0 0 12px 0;
      color: #FFFFFF;
      line-height: 1.4;
    }}
    .hero-desc {{
      font-size: 13px;
      color: #94A3B8;
      line-height: 1.6;
      margin: 0 0 24px 0;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 12px;
      margin-bottom: 24px;
    }}
    .metric-col {{
      background: #0B0F19;
      border: 1px solid #1E293B;
      padding: 12px 14px;
      border-radius: 8px;
    }}
    .metric-label {{
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #64748B;
      margin-bottom: 4px;
    }}
    .metric-val {{
      font-size: 13px;
      font-weight: 700;
      color: #E2E8F0;
      font-family: monospace;
    }}
    .card {{
      background: #0B0F19;
      border: 1px solid #1E293B;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
    }}
    .card-title {{
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #38BDF8;
      margin-bottom: 8px;
    }}
    .card-body {{
      font-size: 13px;
      color: #CBD5E1;
      line-height: 1.5;
      margin: 0;
    }}
    .log-box {{
      background: #06090F;
      border: 1px solid #1E293B;
      border-radius: 6px;
      padding: 12px;
      font-family: monospace;
      font-size: 11px;
      color: #F87171;
      overflow-x: auto;
      margin-top: 10px;
      white-space: pre-wrap;
    }}
    .action-box {{
      background: rgba(0, 240, 255, 0.05);
      border: 1px solid rgba(0, 240, 255, 0.2);
      border-radius: 6px;
      padding: 12px;
      font-size: 13px;
      color: #E2E8F0;
      line-height: 1.5;
    }}
    .footer {{
      padding: 20px 32px;
      background: #080B11;
      border-top: 1px solid #1E293B;
      text-align: center;
      font-size: 11px;
      color: #64748B;
      line-height: 1.6;
    }}
    .footer a {{
      color: #00F0FF;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <div class="brand">LEAR<span>.AI</span></div>
        <div class="brand-sub">Infrastructure Intelligence</div>
      </div>
      <div class="badge">{status_icon} {status_text}</div>
    </div>
    <div class="content">
      <h1 class="hero-title">{html.escape(title)}</h1>
      <p class="hero-desc">
        Lear Autonomous SRE Engine detected an operational condition on the production cluster. The AI brain diagnosed the root cause and is standing by for human authorization or autonomous resolution.
      </p>

      <div class="metric-grid">
        <div class="metric-col">
          <div class="metric-label">Incident ID</div>
          <div class="metric-val">{html.escape(inc_id)}</div>
        </div>
        <div class="metric-col">
          <div class="metric-label">Service</div>
          <div class="metric-val">{html.escape(service)}</div>
        </div>
        <div class="metric-col">
          <div class="metric-label">Cluster</div>
          <div class="metric-val">{html.escape(cluster)}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">🚨 Incident Detection & Symptoms</div>
        <p class="card-body">
          Service reported failure during health probe evaluation. Incoming traffic experiencing disruption.
        </p>
        <div class="log-box">{html.escape(error_summary)}</div>
      </div>

      <div class="card">
        <div class="card-title">🧠 DeepSeek AI Root Cause Diagnosis</div>
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
      Incident: <code>{html.escape(inc_id)}</code> • <a href="{chat_url}">Open in Lear Dashboard</a>
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
    """Generates the HTML email, archives it for preview, and dispatches via SMTP directly to the recipient."""
    creds = credentials or {}
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in open(env_file):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds.setdefault(k.strip(), v.strip().strip("'").strip('"'))

    inc_id = incident_id or f"INC-{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}"
    chat_url = f"http://localhost:1420/?tab=chat&session={inc_id}"

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

    recipient = to_email or creds.get("EMAIL_TO") or os.environ.get("EMAIL_TO") or "anantacharya5568@gmail.com"

    email_record = {
        "id": f"email_{int(datetime.datetime.now(datetime.timezone.utc).timestamp()*1000)}",
        "incident_id": inc_id,
        "subject": subject,
        "service": service,
        "status": status,
        "resolution_status": resolution_status,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "recipient": recipient,
        "sender": (creds.get("EMAIL_FROM") or os.environ.get("EMAIL_FROM") or "anantacharya290@gmail.com").strip(),
        "smtp_sent": False,
        "html": html_body,
    }

    # 2. Attempt real SMTP if configured
    user = (creds.get("EMAIL_USER") or os.environ.get("EMAIL_USER") or "").strip()
    password = (creds.get("EMAIL_PASSWORD") or os.environ.get("EMAIL_PASSWORD") or "").strip()
    if password:
        password = password.replace(" ", "").strip()
    sender = (creds.get("EMAIL_FROM") or os.environ.get("EMAIL_FROM") or user or "anantacharya290@gmail.com").strip()
    smtp_host = (creds.get("EMAIL_SMTP_HOST") or os.environ.get("EMAIL_SMTP_HOST") or "").strip()
    if not smtp_host and ("@gmail.com" in user.lower() or "@gmail.com" in sender.lower()):
        smtp_host = "smtp.gmail.com"

    if smtp_host and recipient:
        try:
            port = int(creds.get("EMAIL_SMTP_PORT") or os.environ.get("EMAIL_SMTP_PORT") or "587")

            msg = email.message.EmailMessage()
            msg["Subject"] = subject
            msg["From"] = sender
            msg["To"] = recipient
            msg.set_content(
                f"{subject}\n\nService: {service}\nStatus: {status}\nDiagnosis: {diagnosis}\n"
                f"Action: {action_taken}\n\nOpen Incident Chat: {chat_url}\n"
                f"Approve Fix: {base_url}/api/incident/{inc_id}/approve\n"
                f"Deny Fix: {base_url}/api/incident/{inc_id}/deny\n"
            )
            msg.add_alternative(html_body, subtype="html")

            if port == 465:
                with smtplib.SMTP_SSL(smtp_host, port, timeout=12) as server:
                    if user and password:
                        server.login(user, password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(smtp_host, port, timeout=12) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
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


def generate_copilot_chat_email_html(
    user_query: str,
    copilot_reply: str,
    incident_id: str,
    service: str = "checkout-api",
    status: str = "ACTIVE",
    action: Optional[str] = None,
    base_url: str = "http://localhost:8000",
) -> str:
    """Generates an executive-grade conversational response email from Lear Copilot."""
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    is_resolved = (status or "").upper() in ("RESOLVED", "RECOVERED", "HEALTHY") or action == "approved"
    status_icon = "🟢" if is_resolved else "🚨"
    status_badge = "RECOVERED" if is_resolved else "INCIDENT ACTIVE"
    status_color = "#10B981" if is_resolved else "#EF4444"

    chat_url = f"http://localhost:1420/?tab=chat&session={incident_id}"
    approve_url = f"{base_url}/api/incident/{incident_id}/approve"
    deny_url = f"{base_url}/api/incident/{incident_id}/deny"

    # Action buttons
    if not is_resolved:
        buttons_markup = f"""
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin: 20px auto 0 auto; width: 100%;">
          <tr>
            <td align="center" style="padding: 4px;">
              <a href="{chat_url}" target="_blank" style="display: block; background: #00F0FF; color: #041019; font-weight: 700; font-size: 13px; padding: 12px 16px; border-radius: 6px; text-decoration: none; border: 1px solid #38BDF8;">
                💬 Open Incident Chat in Lear
              </a>
            </td>
            <td align="center" style="padding: 4px;">
              <a href="{approve_url}" target="_blank" style="display: block; background: #10B981; color: #041F16; font-weight: 700; font-size: 13px; padding: 12px 16px; border-radius: 6px; text-decoration: none; border: 1px solid #059669;">
                ✅ Approve & Apply Fix
              </a>
            </td>
            <td align="center" style="padding: 4px;">
              <a href="{deny_url}" target="_blank" style="display: block; background: #1E293B; color: #F43F5E; font-weight: 700; font-size: 13px; padding: 12px 16px; border-radius: 6px; text-decoration: none; border: 1px solid #334155;">
                ❌ Deny Fix
              </a>
            </td>
          </tr>
        </table>
        """
    else:
        buttons_markup = f"""
        <div style="margin-top: 18px; padding: 12px; background: rgba(16, 185, 129, 0.1); border: 1px solid #059669; border-radius: 6px; text-align: center;">
          <a href="{chat_url}" target="_blank" style="color: #00F0FF; font-size: 13px; font-weight: 600; text-decoration: none;">
            ✅ Remediation Deployed — View Timeline in Lear Dashboard →
          </a>
        </div>
        """

    formatted_reply = html.escape(copilot_reply).replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lear Copilot Response</title>
</head>
<body style="margin:0;padding:0;background-color:#080B11;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#E2E8F0;">
  <div style="max-width:640px;margin:24px auto;background:#0E131F;border:1px solid #1E293B;border-radius:12px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,0.5);">
    <!-- Header -->
    <div style="background:linear-gradient(135deg, #111622 0%, #080B11 100%);padding:20px 28px;border-bottom:1px solid #1E293B;display:flex;align-items:center;justify-content:space-between;">
      <div>
        <div style="font-size:18px;font-weight:800;letter-spacing:1.5px;color:#F8FAFC;">
          LEAR<span style="color:#00F0FF;">.AI</span>
        </div>
        <div style="font-size:11px;color:#64748B;letter-spacing:0.5px;margin-top:2px;">Infrastructure Intelligence</div>
      </div>
      <div style="background:{status_color};color:#FFFFFF;font-size:11px;font-weight:700;padding:4px 10px;border-radius:999px;">
        {status_icon} {status_badge}
      </div>
    </div>
    
    <!-- Body -->
    <div style="padding:28px;">
      <!-- Quoted user question -->
      <div style="margin-bottom:20px;padding:12px 16px;background:#0B0F19;border-left:3px solid #00F0FF;border-radius:4px;">
        <div style="font-size:11px;font-weight:700;color:#00F0FF;text-transform:uppercase;margin-bottom:4px;">Your Question</div>
        <div style="font-size:14px;color:#E2E8F0;font-style:italic;">"{html.escape(user_query)}"</div>
      </div>

      <!-- Copilot Answer -->
      <div style="background:#0B0F19;border:1px solid #1E293B;border-radius:8px;padding:20px;margin-bottom:20px;">
        <div style="display:flex;align-items:center;margin-bottom:12px;">
          <span style="font-size:16px;margin-right:8px;">🧠</span>
          <span style="font-size:14px;font-weight:700;color:#F9FAFB;">Lear SRE Copilot</span>
          <span style="margin-left:auto;font-size:11px;color:#6B7280;">{now_str}</span>
        </div>
        <div style="font-size:14px;line-height:1.6;color:#D1D5DB;">
          {formatted_reply}
        </div>
      </div>

      <!-- Incident Metadata Context -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;background:#0A0E17;border:1px solid #1E293B;padding:12px;border-radius:6px;font-size:12px;">
        <div><span style="color:#64748B;">Service:</span> <strong style="color:#E2E8F0;">{html.escape(service)}</strong></div>
        <div><span style="color:#64748B;">Incident:</span> <strong style="color:#E2E8F0;">{html.escape(incident_id)}</strong></div>
      </div>

      <!-- Action Buttons -->
      {buttons_markup}

      <!-- Interactive instructions -->
      <div style="margin-top:20px;padding:12px;background:#06090F;border-radius:6px;border:1px dashed #334155;text-align:center;font-size:12px;color:#94A3B8;">
        💡 <strong>Live Email Chat:</strong> Reply directly to this email with questions or type <em>"Approve"</em> to automatically trigger cluster remediation.
      </div>
    </div>

    <!-- Footer -->
    <div style="background:#080B11;padding:14px;text-align:center;font-size:11px;color:#64748B;border-top:1px solid #1E293B;">
      Lear Autonomous SRE Copilot • EKS Infrastructure Intelligence • <a href="{chat_url}" style="color:#00F0FF;text-decoration:none;">Open in Lear Dashboard</a>
    </div>
  </div>
</body>
</html>
"""


def dispatch_copilot_email_reply(
    to_email: str,
    subject: str,
    user_query: str,
    copilot_reply: str,
    incident_id: str,
    service: str = "checkout-api",
    status: str = "ACTIVE",
    action: Optional[str] = None,
    base_url: str = "http://localhost:8000",
) -> Dict[str, Any]:
    """Dispatches a conversational email reply via Gmail SMTP directly to the recipient."""
    creds = {}
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in open(env_file, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds.setdefault(k.strip(), v.strip().strip("'").strip('"'))

    html_content = generate_copilot_chat_email_html(
        user_query=user_query,
        copilot_reply=copilot_reply,
        incident_id=incident_id,
        service=service,
        status=status,
        action=action,
        base_url=base_url,
    )

    recipient = to_email or creds.get("EMAIL_TO", "anantacharya5568@gmail.com")
    user = (creds.get("EMAIL_USER") or os.environ.get("EMAIL_USER") or "").strip()
    password = (creds.get("EMAIL_PASSWORD") or os.environ.get("EMAIL_PASSWORD") or "").strip()
    if password:
        password = password.replace(" ", "").strip()
    sender = (creds.get("EMAIL_FROM") or os.environ.get("EMAIL_FROM") or user or "anantacharya290@gmail.com").strip()
    smtp_host = (creds.get("EMAIL_SMTP_HOST") or os.environ.get("EMAIL_SMTP_HOST") or "smtp.gmail.com").strip()
    port = int(creds.get("EMAIL_SMTP_PORT") or os.environ.get("EMAIL_SMTP_PORT") or "587")

    email_record = {
        "id": f"email_chat_{int(datetime.datetime.now(datetime.timezone.utc).timestamp()*1000)}",
        "incident_id": incident_id,
        "subject": subject,
        "recipient": recipient,
        "sender": sender,
        "smtp_sent": False,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    try:
        msg = email.message.EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.set_content(
            f"Lear Copilot Response:\n\nIn response to: \"{user_query}\"\n\n{copilot_reply}\n\n"
            f"Open War Room: {base_url}/incident/{incident_id}\n"
            f"Approve Fix: {base_url}/api/incident/{incident_id}/approve\n"
            f"Deny Fix: {base_url}/api/incident/{incident_id}/deny\n"
        )
        msg.add_alternative(html_content, subtype="html")

        if port == 465:
            with smtplib.SMTP_SSL(smtp_host, port, timeout=12) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, port, timeout=12) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        email_record["smtp_sent"] = True
        logger.info(f"Sent Copilot conversational email reply to {recipient} via {smtp_host}")
    except Exception as exc:
        logger.warning(f"SMTP send failed for Copilot reply: {exc}")
        email_record["smtp_error"] = str(exc)

    DISPATCHED_EMAILS.insert(0, email_record)
    return email_record

