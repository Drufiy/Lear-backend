"""Shared Incident War Room Web Interface.

Provides a real-time collaborative incident war room where human on-call engineers
and Lear SRE Copilot coordinate remediation.
Pre-loaded with incident telemetry, inferences, one-click quick-reply chips,
approval/denial workflows, and email-reply simulation.
"""
import json

def generate_incident_war_room_html(incident: dict) -> str:
    inc_id = incident.get("incident_id", "INC-DEMO")
    service = incident.get("service", "checkout-api")
    namespace = incident.get("namespace", "lear-demo")
    status = incident.get("status", "ACTIVE")
    res_status = incident.get("resolution_status", "INVESTIGATING")
    cluster = incident.get("cluster", "AWS EKS lear-demo (ap-south-1)")
    error_summary = incident.get("error_summary", "postgres-wrong:5432 connection failure")
    diagnosis = incident.get("diagnosis", "ConfigMap misconfigured DATABASE_HOST to postgres-wrong")
    proposed_remediation = incident.get("proposed_remediation", "Patch ConfigMap and rollout restart")

    is_resolved = status == "RESOLVED"
    status_class = "status-resolved" if is_resolved else "status-critical"
    status_text = "RESOLVED" if is_resolved else "CRITICAL — ACTION REQUIRED"

    # Format conversation messages
    conversation = incident.get("conversation", [])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>War Room: {inc_id} — Lear Autonomous SRE</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #07090E;
      --surface: #0D111A;
      --surface-border: #1B2333;
      --surface-hover: #141A28;
      --primary: #10B981;
      --primary-glow: rgba(16, 185, 129, 0.2);
      --danger: #F43F5E;
      --danger-glow: rgba(244, 63, 94, 0.2);
      --blue: #3B82F6;
      --cyan: #06B6D4;
      --text-main: #F8FAFC;
      --text-muted: #94A3B8;
      --text-dim: #64748B;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background-color: var(--bg);
      color: var(--text-main);
      font-family: 'Inter', -apple-system, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    header {{
      background: rgba(13, 17, 26, 0.9);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--surface-border);
      padding: 16px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 18px;
      font-weight: 800;
      letter-spacing: 1px;
    }}
    .brand span {{ color: var(--primary); }}
    .inc-tag {{
      background: #1E293B;
      color: #94A3B8;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid var(--surface-border);
    }}
    .status-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.8px;
      text-transform: uppercase;
    }}
    .status-critical {{
      background: rgba(244, 63, 94, 0.15);
      color: var(--danger);
      border: 1px solid var(--danger);
    }}
    .status-resolved {{
      background: rgba(16, 185, 129, 0.15);
      color: var(--primary);
      border: 1px solid var(--primary);
    }}
    .main-grid {{
      flex: 1;
      display: grid;
      grid-template-columns: 480px 1fr;
      overflow: hidden;
      height: calc(100vh - 71px);
    }}
    /* Left Panel: Telemetry & Inferences */
    .left-panel {{
      background: var(--surface);
      border-right: 1px solid var(--surface-border);
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }}
    .card {{
      background: #090D15;
      border: 1px solid var(--surface-border);
      border-radius: 10px;
      padding: 18px;
    }}
    .card-title {{
      font-size: 12px;
      font-weight: 700;
      color: var(--cyan);
      text-transform: uppercase;
      letter-spacing: 0.6px;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .meta-row {{
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      padding: 6px 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
    }}
    .meta-row:last-child {{ border-bottom: none; }}
    .meta-label {{ color: var(--text-dim); }}
    .meta-val {{ font-weight: 600; color: var(--text-main); }}
    .code-box {{
      background: #04060A;
      border: 1px solid #1E2330;
      border-radius: 6px;
      padding: 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: #F43F5E;
      white-space: pre-wrap;
      word-break: break-all;
      max-height: 140px;
      overflow-y: auto;
    }}
    .diff-box {{
      background: #04060A;
      border: 1px solid #1E2330;
      border-radius: 6px;
      padding: 10px 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      line-height: 1.6;
    }}
    .diff-del {{ color: #F43F5E; background: rgba(244, 63, 94, 0.1); padding: 2px 4px; border-radius: 4px; }}
    .diff-add {{ color: #10B981; background: rgba(16, 185, 129, 0.1); padding: 2px 4px; border-radius: 4px; }}

    .action-button-group {{
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-top: 6px;
    }}
    .btn-action {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 12px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      border: none;
      transition: all 0.2s ease;
      text-decoration: none;
    }}
    .btn-approve {{
      background: var(--primary);
      color: #041F16;
      box-shadow: 0 4px 14px var(--primary-glow);
    }}
    .btn-approve:hover {{
      background: #34D399;
      transform: translateY(-1px);
    }}
    .btn-deny {{
      background: rgba(244, 63, 94, 0.15);
      border: 1px solid var(--danger);
      color: var(--danger);
    }}
    .btn-deny:hover {{
      background: rgba(244, 63, 94, 0.25);
    }}
    .btn-sim-email {{
      background: #1E293B;
      border: 1px solid var(--surface-border);
      color: #E2E8F0;
    }}
    .btn-sim-email:hover {{
      background: #334155;
    }}

    /* Right Panel: Shared Conversation */
    .right-panel {{
      display: flex;
      flex-direction: column;
      background: #0A0E17;
      height: 100%;
      overflow: hidden;
    }}
    .chat-header {{
      padding: 16px 24px;
      border-bottom: 1px solid var(--surface-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #0D121E;
    }}
    .chat-title {{
      font-size: 14px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .chat-subtitle {{
      font-size: 12px;
      color: var(--text-dim);
    }}
    .chat-messages {{
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 18px;
    }}
    .msg-bubble {{
      max-width: 80%;
      padding: 14px 18px;
      border-radius: 12px;
      font-size: 13px;
      line-height: 1.6;
      position: relative;
    }}
    .msg-copilot {{
      align-self: flex-start;
      background: #111827;
      border: 1px solid var(--surface-border);
      color: var(--text-main);
    }}
    .msg-user {{
      align-self: flex-end;
      background: #1E3A8A;
      color: #FFFFFF;
      border: 1px solid #2563EB;
    }}
    .msg-sender {{
      font-size: 11px;
      font-weight: 700;
      color: var(--cyan);
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .msg-user .msg-sender {{
      color: #93C5FD;
      justify-content: flex-end;
    }}
    .msg-time {{
      font-size: 10px;
      color: var(--text-dim);
      font-weight: 400;
    }}

    /* Quick Reply Chips */
    .quick-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 12px 24px 0 24px;
      background: #0A0E17;
    }}
    .chip {{
      background: #131B2E;
      border: 1px solid #1E293B;
      color: #93C5FD;
      font-size: 12px;
      font-weight: 600;
      padding: 6px 14px;
      border-radius: 9999px;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .chip:hover {{
      background: #1E2B48;
      border-color: #3B82F6;
      color: #FFFFFF;
      transform: translateY(-1px);
    }}
    .chip-approve {{
      background: rgba(16, 185, 129, 0.15);
      border-color: #059669;
      color: #A7F3D0;
    }}
    .chip-approve:hover {{
      background: rgba(16, 185, 129, 0.25);
      color: #FFFFFF;
    }}

    /* Input Bar */
    .chat-input-bar {{
      padding: 16px 24px 20px 24px;
      display: flex;
      gap: 12px;
      background: #0A0E17;
      border-top: 1px solid var(--surface-border);
    }}
    .chat-input {{
      flex: 1;
      background: #0F1422;
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      padding: 12px 16px;
      color: #FFFFFF;
      font-size: 13px;
      outline: none;
    }}
    .chat-input:focus {{
      border-color: var(--blue);
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }}
    .btn-send {{
      background: var(--blue);
      color: #FFFFFF;
      border: none;
      border-radius: 8px;
      padding: 0 20px;
      font-weight: 700;
      font-size: 13px;
      cursor: pointer;
      transition: background 0.15s;
    }}
    .btn-send:hover {{ background: #2563EB; }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      LEAR<span>.AI</span>
      <span class="inc-tag">{inc_id}</span>
      <span style="font-size: 13px; font-weight: 500; color: var(--text-muted);">Shared Incident War Room</span>
    </div>
    <div style="display: flex; align-items: center; gap: 14px;">
      <a href="/demo" style="color: var(--text-muted); text-decoration: none; font-size: 12px; font-weight: 600;">← Back to Demo Control Center</a>
      <div id="statusBadge" class="status-badge {status_class}">
        {status_text}
      </div>
    </div>
  </header>

  <div class="main-grid">
    <!-- Left Column: Diagnostics & Controls -->
    <div class="left-panel">
      <div class="card">
        <div class="card-title">🎯 Incident Scope</div>
        <div class="meta-row">
          <span class="meta-label">Target Service</span>
          <span class="meta-val">{service}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Namespace</span>
          <span class="meta-val">{namespace}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Cluster</span>
          <span class="meta-val">{cluster}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Severity</span>
          <span class="meta-val" style="color: #F43F5E;">CRITICAL (P1)</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Customer Traffic</span>
          <span class="meta-val" id="trafficState" style="color: {'#10B981' if is_resolved else '#F43F5E'};">
            {'200 OK — Restored' if is_resolved else '502 Bad Gateway — Outage'}
          </span>
        </div>
      </div>

      <div class="card">
        <div class="card-title">🚨 Pod Crash Logs & Error Trace</div>
        <div class="code-box">{error_summary}</div>
      </div>

      <div class="card">
        <div class="card-title">🧠 DeepSeek AI Root Cause Diagnosis</div>
        <p style="font-size: 13px; color: var(--text-muted); line-height: 1.5; margin-bottom: 12px;">
          {diagnosis}
        </p>
        <div class="diff-box">
          <div style="color: var(--text-dim); font-size: 11px; margin-bottom: 4px;">ConfigMap / checkout-api-config:</div>
          <div class="diff-del">- DATABASE_HOST: "postgres-wrong"</div>
          <div class="diff-add">+ DATABASE_HOST: "postgres"</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">⚡ Actions & Authorization</div>
        <div class="action-button-group">
          <button id="btnApprove" class="btn-action btn-approve" onclick="approveRemediation()">
            ✅ Approve & Deploy Fix
          </button>
          <button id="btnDeny" class="btn-action btn-deny" onclick="denyRemediation()">
            ❌ Deny / Escalate to Human
          </button>
          <button class="btn-action btn-sim-email" onclick="simulateEmailReply()">
            ✉️ Simulate Inbound Email Reply
          </button>
        </div>
      </div>
    </div>

    <!-- Right Column: Interactive Copilot Chat -->
    <div class="right-panel">
      <div class="chat-header">
        <div>
          <div class="chat-title">
            <span>🧠</span> Lear SRE Copilot (Active War Room)
          </div>
          <div class="chat-subtitle">Direct interactive session • DeepSeek AI Engine connected</div>
        </div>
        <div style="font-size: 12px; color: var(--text-dim);">
          Incident Channel
        </div>
      </div>

      <div class="chat-messages" id="chatMessages">
        <!-- Messages rendered by script -->
      </div>

      <div class="quick-chips">
        <button class="chip chip-approve" onclick="sendQuickMessage('Approve & Deploy Fix')">✅ Approve & Deploy Fix</button>
        <button class="chip" onclick="sendQuickMessage('What is the customer checkout impact right now?')">❓ Customer Impact?</button>
        <button class="chip" onclick="sendQuickMessage('Show live pod status and restart count')">📊 Pod Status</button>
        <button class="chip" onclick="sendQuickMessage('Explain why postgres-wrong failed to resolve')">🔍 Explain Root Cause</button>
        <button class="chip" style="color: #F43F5E; border-color: rgba(244,63,94,0.3);" onclick="sendQuickMessage('Deny / Halt Changes')">❌ Deny Fix</button>
      </div>

      <div class="chat-input-bar">
        <input type="text" id="chatInput" class="chat-input" placeholder="Type a question, instruction, or reply 'Approve' to deploy fix..." onkeydown="if(event.key==='Enter') sendMessage()" />
        <button class="btn-send" onclick="sendMessage()">Send</button>
      </div>
    </div>
  </div>

  <script>
    const incidentId = "{inc_id}";
    let conversation = {json.dumps(conversation)};

    function renderConversation() {{
      const container = document.getElementById('chatMessages');
      container.innerHTML = '';
      conversation.forEach(item => {{
        const isCopilot = item.sender.includes('Copilot');
        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble ' + (isCopilot ? 'msg-copilot' : 'msg-user');

        const senderDiv = document.createElement('div');
        senderDiv.className = 'msg-sender';
        senderDiv.innerHTML = (item.avatar ? item.avatar + ' ' : '') + item.sender + 
          ' <span class="msg-time">' + (item.timestamp || '') + '</span>';

        const textDiv = document.createElement('div');
        textDiv.style.whiteSpace = 'pre-wrap';
        textDiv.innerHTML = escapeHtml(item.message)
          .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
          .replace(/`(.*?)`/g, '<code style="background:rgba(255,255,255,0.08);padding:2px 4px;border-radius:4px;">$1</code>');

        bubble.appendChild(senderDiv);
        bubble.appendChild(textDiv);
        container.appendChild(bubble);
      }});
      container.scrollTop = container.scrollHeight;
    }}

    function escapeHtml(text) {{
      const div = document.createElement('div');
      div.innerText = text;
      return div.innerHTML;
    }}

    async function approveRemediation() {{
      document.getElementById('btnApprove').innerText = '⏳ Applying Patch...';
      document.getElementById('btnApprove').disabled = true;
      try {{
        const res = await fetch('/api/incident/' + incidentId + '/approve', {{ method: 'POST' }});
        const data = await res.json();
        if (data.success) {{
          updateStatusResolved();
          if (data.incident && data.incident.conversation) {{
            conversation = data.incident.conversation;
            renderConversation();
          }}
        }} else {{
          alert('Failed to approve: ' + (data.error || 'Unknown error'));
        }}
      }} catch (e) {{
        alert('Approval failed: ' + e.message);
      }} finally {{
        document.getElementById('btnApprove').innerText = '✅ Fix Applied & Verified';
      }}
    }}

    async function denyRemediation() {{
      try {{
        const res = await fetch('/api/incident/' + incidentId + '/deny', {{ method: 'POST' }});
        const data = await res.json();
        if (data.success && data.incident) {{
          conversation = data.incident.conversation;
          renderConversation();
          const badge = document.getElementById('statusBadge');
          badge.className = 'status-badge status-critical';
          badge.innerText = 'ESCALATED TO HUMAN';
        }}
      }} catch (e) {{
        alert('Error denying: ' + e.message);
      }}
    }}

    async function sendMessage() {{
      const input = document.getElementById('chatInput');
      const text = input.value.trim();
      if (!text) return;
      input.value = '';

      // Optimistically append user message
      conversation.push({{
        sender: "On-Call Engineer (You)",
        avatar: "👤",
        message: text,
        timestamp: new Date().toLocaleTimeString([], {{hour: '2-digit', minute:'2-digit'}})
      }});
      renderConversation();

      try {{
        const res = await fetch('/api/incident/' + incidentId + '/chat', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ message: text }})
        }});
        const data = await res.json();
        if (data.incident && data.incident.conversation) {{
          conversation = data.incident.conversation;
          renderConversation();
          if (data.action === 'approved') {{
            updateStatusResolved();
          }}
        }}
      }} catch (e) {{
        conversation.push({{
          sender: "Lear SRE Copilot",
          avatar: "⚠️",
          message: "Error contacting agent: " + e.message,
          timestamp: new Date().toLocaleTimeString([], {{hour: '2-digit', minute:'2-digit'}})
        }});
        renderConversation();
      }}
    }}

    function sendQuickMessage(text) {{
      document.getElementById('chatInput').value = text;
      sendMessage();
    }}

    async function simulateEmailReply() {{
      const userReply = prompt(
        "Simulate an inbound email reply to Lear SRE Copilot:\\n(e.g., 'Approve', 'What is the impact?', 'Can you verify postgres is up?')",
        "Approve the patch and deploy it now"
      );
      if (!userReply) return;

      try {{
        const res = await fetch('/api/incident/' + incidentId + '/email-reply', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            from_email: "anantacharya5568@gmail.com",
            subject: "Re: [CRITICAL] checkout-api Incident Alert",
            body: userReply
          }})
        }});
        const data = await res.json();
        if (data.incident && data.incident.conversation) {{
          conversation = data.incident.conversation;
          renderConversation();
          if (data.action === 'approved') updateStatusResolved();
        }}
        alert("Lear Copilot parsed your simulated email reply and generated a response!");
      }} catch (e) {{
        alert("Simulation failed: " + e.message);
      }}
    }}

    function updateStatusResolved() {{
      const badge = document.getElementById('statusBadge');
      badge.className = 'status-badge status-resolved';
      badge.innerText = 'RESOLVED IN 14s';
      const traffic = document.getElementById('trafficState');
      if (traffic) {{
        traffic.innerText = '200 OK — Restored';
        traffic.style.color = '#10B981';
      }}
    }}

    // Initial render
    renderConversation();

    // Auto-polling for external approvals or changes
    setInterval(async () => {{
      try {{
        const res = await fetch('/api/incident/' + incidentId);
        const data = await res.json();
        if (data.incident) {{
          if (data.incident.conversation.length !== conversation.length) {{
            conversation = data.incident.conversation;
            renderConversation();
          }}
          if (data.incident.status === 'RESOLVED') {{
            updateStatusResolved();
          }}
        }}
      }} catch (e) {{}}
    }}, 3000);
  </script>
</body>
</html>
"""
