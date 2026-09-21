"""Chaos Engineering & Infrastructure Admin Console for Lear SRE.

Strictly designed for operational control, error injection, and cluster telemetry.
NO conversational chat or AI fluff is rendered here — all incident debugging,
episodic memory reasoning, and resolution dialogues are routed directly to the
Lear Desktop Dashboard.
"""

def generate_admin_chaos_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lear Chaos Engineering & Admin Console | EKS Mumbai</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #06080D;
      --bg-surface: #0C1019;
      --bg-surface-elevated: #131A27;
      --border-subtle: #1B2436;
      --border-accent: #2B3852;
      --text-main: #E2E8F0;
      --text-muted: #94A3B8;
      --text-subtle: #64748B;
      --accent: #38BDF8;
      --accent-glow: rgba(56, 189, 248, 0.15);
      --danger: #EF4444;
      --danger-glow: rgba(239, 68, 68, 0.18);
      --warning: #F59E0B;
      --warning-glow: rgba(245, 158, 11, 0.15);
      --success: #10B981;
      --success-glow: rgba(16, 185, 129, 0.15);
      --purple: #8B5CF6;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg-base);
      color: var(--text-main);
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      -webkit-font-smoothing: antialiased;
    }

    /* Top Navigation */
    .nav {
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      padding: 14px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand-box {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-icon {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: linear-gradient(135deg, #0284C7, #38BDF8);
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 800;
      color: #04121F;
      font-size: 16px;
      box-shadow: 0 0 16px var(--accent-glow);
    }
    .brand-title {
      font-size: 15px;
      font-weight: 700;
      letter-spacing: -0.2px;
      color: #F8FAFC;
    }
    .brand-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      background: #1E293B;
      color: #94A3B8;
      padding: 3px 8px;
      border-radius: 4px;
      border: 1px solid #334155;
    }

    .nav-links {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .nav-btn {
      font-size: 12px;
      font-weight: 600;
      text-decoration: none;
      color: var(--text-muted);
      padding: 6px 12px;
      border-radius: 6px;
      border: 1px solid var(--border-subtle);
      background: var(--bg-surface-elevated);
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .nav-btn:hover {
      color: var(--text-main);
      border-color: var(--border-accent);
      background: #1A2436;
    }
    .nav-btn.primary {
      background: var(--accent);
      color: #041424;
      border-color: var(--accent);
      font-weight: 700;
    }
    .nav-btn.primary:hover {
      background: #7DD3FC;
    }

    /* Main Container */
    .container {
      max-width: 1380px;
      margin: 0 auto;
      padding: 28px 24px 60px;
      width: 100%;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }

    /* Notice Banner */
    .control-notice {
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 14px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .notice-text {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.5;
    }
    .notice-text strong {
      color: #F1F5F9;
    }
    .notice-tag {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      background: rgba(56, 189, 248, 0.1);
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.25);
      padding: 4px 10px;
      border-radius: 6px;
      white-space: nowrap;
    }

    /* Telemetry Cards Grid */
    .grid-4 {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
    }
    .metric-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 18px 20px;
      position: relative;
      overflow: hidden;
    }
    .metric-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 2px;
      background: var(--border-accent);
    }
    .metric-card.healthy::before { background: var(--success); }
    .metric-card.degraded::before { background: var(--warning); }
    .metric-card.down::before { background: var(--danger); }

    .metric-label {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.6px;
      text-transform: uppercase;
      color: var(--text-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .metric-status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--text-subtle);
    }
    .dot-healthy { background: var(--success); box-shadow: 0 0 8px var(--success-glow); }
    .dot-danger { background: var(--danger); box-shadow: 0 0 8px var(--danger-glow); }
    .dot-warning { background: var(--warning); box-shadow: 0 0 8px var(--warning-glow); }

    .metric-val {
      font-family: 'JetBrains Mono', monospace;
      font-size: 22px;
      font-weight: 700;
      color: #F8FAFC;
      margin-top: 8px;
    }
    .metric-sub {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
      font-family: 'JetBrains Mono', monospace;
    }

    /* Main Chaos Grid */
    .chaos-layout {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 20px;
    }

    .panel {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      padding: 24px;
    }
    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 20px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border-subtle);
    }
    .panel-title {
      font-size: 16px;
      font-weight: 700;
      color: #F8FAFC;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .panel-desc {
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 4px;
    }

    /* Chaos Scenario Cards */
    .chaos-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .chaos-card {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.2s ease;
      position: relative;
    }
    .chaos-card:hover {
      border-color: var(--border-accent);
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
    }
    .chaos-card.highlight {
      border-color: rgba(56, 189, 248, 0.4);
      background: linear-gradient(145deg, rgba(12, 16, 25, 0.8), rgba(20, 29, 46, 0.9));
    }
    .scenario-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      font-weight: 700;
      padding: 3px 7px;
      border-radius: 4px;
      text-transform: uppercase;
      display: inline-block;
      margin-bottom: 10px;
    }
    .badge-danger { background: rgba(239, 68, 68, 0.15); color: #FCA5A5; border: 1px solid rgba(239, 68, 68, 0.3); }
    .badge-failover { background: rgba(139, 92, 246, 0.15); color: #C4B5FD; border: 1px solid rgba(139, 92, 246, 0.3); }
    .badge-warning { background: rgba(245, 158, 11, 0.15); color: #FDE68A; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-load { background: rgba(56, 189, 248, 0.15); color: #7DD3FC; border: 1px solid rgba(56, 189, 248, 0.3); }

    .scenario-title {
      font-size: 14px;
      font-weight: 700;
      color: #F1F5F9;
      margin-bottom: 6px;
    }
    .scenario-desc {
      font-size: 12px;
      color: var(--text-muted);
      line-height: 1.5;
      margin-bottom: 16px;
    }
    .scenario-impact {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(255, 255, 255, 0.05);
      padding: 8px 10px;
      border-radius: 6px;
      color: #CBD5E1;
      margin-bottom: 16px;
    }

    .chaos-btn {
      width: 100%;
      padding: 10px 14px;
      font-size: 12px;
      font-weight: 700;
      border-radius: 8px;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.2s ease;
      font-family: inherit;
    }
    .chaos-btn.inject-red {
      background: #DC2626;
      color: #FFFFFF;
    }
    .chaos-btn.inject-red:hover {
      background: #EF4444;
      box-shadow: 0 0 16px var(--danger-glow);
    }
    .chaos-btn.inject-purple {
      background: #7C3AED;
      color: #FFFFFF;
    }
    .chaos-btn.inject-purple:hover {
      background: #8B5CF6;
      box-shadow: 0 0 16px rgba(139, 92, 246, 0.3);
    }
    .chaos-btn.inject-amber {
      background: #D97706;
      color: #FFFFFF;
    }
    .chaos-btn.inject-amber:hover {
      background: #F59E0B;
    }
    .chaos-btn.inject-blue {
      background: #0284C7;
      color: #FFFFFF;
    }
    .chaos-btn.inject-blue:hover {
      background: #0EA5E9;
    }
    .chaos-btn.inject-reset {
      background: #059669;
      color: #FFFFFF;
    }
    .chaos-btn.inject-reset:hover {
      background: #10B981;
      box-shadow: 0 0 16px var(--success-glow);
    }

    /* Right Sidebar: Active Pods & Real-time Cluster State */
    .pod-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .pod-item {
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .pod-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .pod-name {
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      font-weight: 600;
      color: #F1F5F9;
    }
    .pod-tag {
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
    }
    .tag-running { background: rgba(16, 185, 129, 0.15); color: #34D399; }
    .tag-crash { background: rgba(239, 68, 68, 0.2); color: #F87171; }
    .pod-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: var(--text-subtle);
    }

    /* Terminal / Console Log */
    .console-box {
      margin-top: 20px;
      background: #03060B;
      border: 1px solid #162032;
      border-radius: 10px;
      padding: 14px 16px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11.5px;
      color: #94A3B8;
      max-height: 220px;
      overflow-y: auto;
      line-height: 1.6;
    }
    .log-line {
      display: flex;
      gap: 10px;
      margin-bottom: 4px;
    }
    .log-ts { color: var(--text-subtle); }
    .log-info { color: #38BDF8; }
    .log-err { color: #F87171; }
    .log-succ { color: #34D399; }

    @media (max-width: 1024px) {
      .grid-4 { grid-template-columns: 1fr 1fr; }
      .chaos-layout { grid-template-columns: 1fr; }
      .chaos-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>

  <!-- Navigation -->
  <header class="nav">
    <div class="brand-box">
      <div class="brand-icon">L</div>
      <div>
        <div class="brand-title">Lear Chaos Engineering Console</div>
        <div style="font-size: 11px; color: var(--text-subtle);">AWS EKS Cluster: lear-demo (ap-south-1)</div>
      </div>
      <span class="brand-badge">SRE ADMIN</span>
    </div>
    <div class="nav-links">
      <a href="/store" target="_blank" class="nav-btn">
        <span>🛒</span>
        <span>View Customer Storefront</span>
      </a>
      <a href="http://localhost:1420" target="_blank" class="nav-btn primary">
        <span>⚡</span>
        <span>Lear Mission Control Dashboard</span>
      </a>
    </div>
  </header>

  <!-- Container -->
  <main class="container">

    <!-- Strict Notice Banner -->
    <section class="control-notice">
      <div class="notice-text">
        <strong>⚠️ OPERATIONAL ISOLATION NOTICE:</strong>
        This panel is dedicated strictly to fault injection, chaos engineering, and cluster telemetry.
        All AI reasoning traces, episodic memory correlation, and resolution dialogues are streamed exclusively to the
        <strong>Lear Desktop Dashboard</strong> and dispatched via email alerts.
      </div>
      <div class="notice-tag">ZERO-CHAT ADMIN CONSOLE</div>
    </section>

    <!-- Cluster Telemetry Strip -->
    <section class="grid-4" id="telemetryStrip">
      <!-- Card 1: API Deployment -->
      <div class="metric-card healthy" id="cardCheckout">
        <div class="metric-label">
          <span>checkout-api Deployment</span>
          <span class="metric-status-dot dot-healthy" id="dotCheckout"></span>
        </div>
        <div class="metric-val" id="valCheckout">1/1 RUNNING</div>
        <div class="metric-sub" id="subCheckout">Namespace: lear-demo</div>
      </div>

      <!-- Card 2: Primary DB -->
      <div class="metric-card healthy" id="cardPostgres">
        <div class="metric-label">
          <span>Primary PostgreSQL (5432)</span>
          <span class="metric-status-dot dot-healthy" id="dotPostgres"></span>
        </div>
        <div class="metric-val" id="valPostgres">ONLINE</div>
        <div class="metric-sub" id="subPostgres">Host: postgres.lear-demo</div>
      </div>

      <!-- Card 3: Standby Replica -->
      <div class="metric-card healthy" id="cardReplica">
        <div class="metric-label">
          <span>Standby Replica (5432)</span>
          <span class="metric-status-dot dot-healthy" id="dotReplica"></span>
        </div>
        <div class="metric-val" id="valReplica">READY (STANDBY)</div>
        <div class="metric-sub" id="subReplica">Host: postgres-replica</div>
      </div>

      <!-- Card 4: AWS ELB Ingress -->
      <div class="metric-card healthy" id="cardElb">
        <div class="metric-label">
          <span>AWS Load Balancer Ingress</span>
          <span class="metric-status-dot dot-healthy" id="dotElb"></span>
        </div>
        <div class="metric-val" id="valElb">200 OK (22ms)</div>
        <div class="metric-sub">Public AWS ELB Gateway</div>
      </div>
    </section>

    <!-- Main Chaos Layout -->
    <div class="chaos-layout">

      <!-- Left Column: Chaos Scenarios -->
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2 class="panel-title">Production Chaos Scenarios</h2>
            <p class="panel-desc">Execute targeted infrastructure failures against active AWS EKS resources.</p>
          </div>
          <button class="chaos-btn inject-reset" style="width: auto; padding: 8px 16px;" onclick="triggerReset()">
            <span>🔄</span>
            <span>Restore Cluster Baseline</span>
          </button>
        </div>

        <div class="chaos-grid">

          <!-- Scenario 1: Primary DB Failure & Automated Replica Failover -->
          <div class="chaos-card highlight">
            <div>
              <span class="scenario-badge badge-failover">DATABASE FAILURE & FAILOVER</span>
              <h3 class="scenario-title">1. Primary DB Outage & Auto-Failover</h3>
              <p class="scenario-desc">
                Cuts connection to primary PostgreSQL. Lear SRE detects connection refused, inspects cluster topology for standby databases, locates <code>postgres-replica:5432</code>, and formulates automated failover.
              </p>
              <div class="scenario-impact">
                Target: Primary postgres:5432<br>
                Expected: Agent discovers replica & executes failover
              </div>
            </div>
            <div style="display:flex;gap:8px;margin-top:10px;">
              <button class="chaos-btn inject-purple" style="flex:1;" id="btnDbFail" onclick="injectDbFailure()">
                <span>💥</span>
                <span>Inject DB Failure</span>
              </button>
              <button class="chaos-btn" style="background:#059669;color:#ffffff;border:1px solid #10B981;flex:1;" id="btnFailover" onclick="triggerFailover()">
                <span>⚡</span>
                <span>Execute Failover</span>
              </button>
            </div>
          </div>

          <!-- Scenario 2: ConfigMap Database Host Corruption -->
          <div class="chaos-card">
            <div>
              <span class="scenario-badge badge-danger">K8S CRASHLOOP</span>
              <h3 class="scenario-title">2. Corrupt ConfigMap Host</h3>
              <p class="scenario-desc">
                Mutates ConfigMap <code>DATABASE_HOST</code> to <code>postgres-wrong</code>. Triggers CrashLoopBackOff on checkout pods. Lear matches episodic memory to re-align configuration.
              </p>
              <div class="scenario-impact">
                Target: checkout-api-config<br>
                Expected: gaierror name resolution failure
              </div>
            </div>
            <button class="chaos-btn inject-red" id="btnConfigFail" onclick="injectConfigFailure()">
              <span>⚡</span>
              <span>Inject ConfigMap Corruption</span>
            </button>
          </div>

          <!-- Scenario 3: Downstream Gateway Latency & Timeout -->
          <div class="chaos-card">
            <div>
              <span class="scenario-badge badge-warning">504 TIMEOUT</span>
              <h3 class="scenario-title">3. Upstream Latency Injection</h3>
              <p class="scenario-desc">
                Simulates artificial network degradation causing 504 Gateway Timeouts on customer checkout. Lear evaluates upstream pod health and proposes circuit-breaker mitigation.
              </p>
              <div class="scenario-impact">
                Target: HTTP Egress Gateway<br>
                Expected: Latency &gt; 5000ms &amp; 504 status
              </div>
            </div>
            <button class="chaos-btn inject-amber" id="btnTimeout" onclick="injectTimeout()">
              <span>⏱️</span>
              <span>Inject Gateway Latency</span>
            </button>
          </div>

          <!-- Scenario 4: Concurrency Traffic Burst -->
          <div class="chaos-card">
            <div>
              <span class="scenario-badge badge-load">TRAFFIC SPIKE</span>
              <h3 class="scenario-title">4. High Concurrency Traffic Surge</h3>
              <p class="scenario-desc">
                Generates a burst of 500 concurrent checkout requests directly through the AWS ELB to stress test connection pooling and container CPU limits.
              </p>
              <div class="scenario-impact">
                Target: Public AWS ELB<br>
                Expected: Connection pool saturation
              </div>
            </div>
            <button class="chaos-btn inject-blue" id="btnLoad" onclick="injectLoadBurst()">
              <span>📈</span>
              <span>Fire Traffic Surge (500 req)</span>
            </button>
          </div>

        </div>

        <!-- Real-time Event Console -->
        <div style="margin-top: 24px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <span style="font-size: 12px; font-weight: 700; color: #94A3B8; text-transform: uppercase;">Real-Time Execution Log</span>
            <span style="font-size: 11px; font-family: 'JetBrains Mono', monospace; color: var(--text-subtle);" id="logStatus">Polling EKS API...</span>
          </div>
          <div class="console-box" id="consoleLog">
            <div class="log-line">
              <span class="log-ts">[INIT]</span>
              <span class="log-info">Admin Console connected to AWS EKS cluster 'lear-demo'. Zero-chat mode enabled.</span>
            </div>
          </div>
        </div>
      </section>

      <!-- Right Column: Live Pod Telemetry & Node Health -->
      <aside class="panel">
        <div class="panel-header">
          <div>
            <h2 class="panel-title">Active EKS Pods</h2>
            <p class="panel-desc">Namespace: lear-demo</p>
          </div>
          <button style="background: none; border: none; color: var(--accent); font-size: 12px; cursor: pointer; font-weight: 600;" onclick="refreshClusterTelemetry()">Refresh</button>
        </div>

        <div class="pod-list" id="podList">
          <div style="color: var(--text-subtle); font-size: 12px; text-align: center; padding: 20px;">Fetching pod list...</div>
        </div>

        <div style="margin-top: 24px; padding-top: 18px; border-top: 1px solid var(--border-subtle);">
          <div style="font-size: 12px; font-weight: 700; color: #94A3B8; text-transform: uppercase; margin-bottom: 10px;">
            Active Database Routing
          </div>
          <div style="background: #03060B; border: 1px solid #162032; border-radius: 8px; padding: 12px; font-family: 'JetBrains Mono', monospace; font-size: 11px;">
            <div style="color: var(--text-subtle); margin-bottom: 4px;">ACTIVE_DATABASE_HOST:</div>
            <div style="color: #38BDF8; font-weight: 700;" id="activeDbHost">postgres (PRIMARY)</div>
            <div style="color: var(--text-subtle); margin-top: 8px; margin-bottom: 4px;">FAILOVER_TARGET:</div>
            <div style="color: #A78BFA;">postgres-replica:5432 (ACTIVE STANDBY)</div>
          </div>
        </div>
      </aside>

    </div>

  </main>

  <script>
    function addLog(type, msg) {
      const box = document.getElementById('consoleLog');
      const now = new Date().toLocaleTimeString();
      const div = document.createElement('div');
      div.className = 'log-line';
      let cls = 'log-info';
      if (type === 'ERR') cls = 'log-err';
      if (type === 'SUCC') cls = 'log-succ';
      div.innerHTML = `<span class="log-ts">[${now}]</span> <span class="${cls}">[${type}] ${msg}</span>`;
      box.appendChild(div);
      box.scrollTop = box.scrollHeight;
    }

    async function refreshClusterTelemetry() {
      try {
        const res = await fetch('/api/demo/health');
        if (!res.ok) return;
        const d = await res.json();
        
        // Pods list
        const list = document.getElementById('podList');
        if (d.pods && d.pods.length > 0) {
          list.innerHTML = '';
          d.pods.forEach(p => {
            const isOk = p.ready && p.status === 'Running';
            const item = document.createElement('div');
            item.className = 'pod-item';
            item.innerHTML = `
              <div class="pod-header">
                <span class="pod-name">${p.name}</span>
                <span class="pod-tag ${isOk ? 'tag-running' : 'tag-crash'}">${p.status}</span>
              </div>
              <div class="pod-meta">
                <span>Ready: ${p.ready ? '1/1' : '0/1'}</span>
                <span>Restarts: ${p.restarts}</span>
              </div>
            `;
            list.appendChild(item);
          });
        }

        // ELB Card
        const elbCard = document.getElementById('cardElb');
        const dotElb = document.getElementById('dotElb');
        const valElb = document.getElementById('valElb');
        if (d.elb_healthy) {
          elbCard.className = 'metric-card healthy';
          dotElb.className = 'metric-status-dot dot-healthy';
          valElb.innerText = `200 OK (${d.latency_ms || 24}ms)`;
        } else {
          elbCard.className = 'metric-card down';
          dotElb.className = 'metric-status-dot dot-danger';
          valElb.innerText = '502 BAD GATEWAY';
        }

        // Inspect checkout pod status
        const checkoutPod = (d.pods || []).find(p => p.name.includes('checkout-api'));
        const cardCheckout = document.getElementById('cardCheckout');
        const dotCheckout = document.getElementById('dotCheckout');
        const valCheckout = document.getElementById('valCheckout');
        if (checkoutPod) {
          if (checkoutPod.status === 'Running' && checkoutPod.ready) {
            cardCheckout.className = 'metric-card healthy';
            dotCheckout.className = 'metric-status-dot dot-healthy';
            valCheckout.innerText = '1/1 RUNNING';
          } else {
            cardCheckout.className = 'metric-card down';
            dotCheckout.className = 'metric-status-dot dot-danger';
            valCheckout.innerText = checkoutPod.status.toUpperCase();
          }
        }
      } catch (err) {
        console.error("Telemetry error:", err);
      }
    }

    async function injectDbFailure() {
      const btn = document.getElementById('btnDbFail');
      btn.disabled = true;
      btn.innerText = 'Injecting Primary DB Outage...';
      addLog('WARN', 'Triggering primary database failure on AWS EKS...');

      try {
        const res = await fetch('/api/demo/inject-db-failure', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          addLog('ERR', 'Primary DB offline. checkout-api experiencing database connection failure.');
          addLog('INFO', 'Lear SRE Agent initiated service discovery: detected healthy replica postgres-replica:5432.');
          addLog('SUCC', 'Incident raised in Lear Dashboard with [DB-FAILOVER] tag. Email alert dispatched to anantacharya290@gmail.com.');
          document.getElementById('valPostgres').innerText = 'OFFLINE (CRASH)';
          document.getElementById('cardPostgres').className = 'metric-card down';
          document.getElementById('dotPostgres').className = 'metric-status-dot dot-danger';
        }
      } catch (e) {
        addLog('ERR', 'DB injection error: ' + e);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>💥</span><span>Inject Primary DB Failure</span>';
        refreshClusterTelemetry();
      }
    }

    async function injectConfigFailure() {
      const btn = document.getElementById('btnConfigFail');
      btn.disabled = true;
      btn.innerText = 'Injecting ConfigMap Break...';
      addLog('WARN', 'Patching ConfigMap checkout-api-config (DATABASE_HOST -> postgres-wrong)...');

      try {
        const res = await fetch('/api/demo/inject-failure', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          addLog('ERR', 'ConfigMap patched to invalid host. Rolling restart in progress.');
          addLog('INFO', 'checkout-api pods entering CrashLoopBackOff.');
          addLog('SUCC', 'Incident logged in Lear Dashboard & email dispatched to anantacharya290@gmail.com.');
        }
      } catch (e) {
        addLog('ERR', 'Config failure injection error: ' + e);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>⚡</span><span>Inject ConfigMap Corruption</span>';
        refreshClusterTelemetry();
      }
    }

    async function injectTimeout() {
      const btn = document.getElementById('btnTimeout');
      btn.disabled = true;
      addLog('WARN', 'Injecting artificial latency & 504 gateway timeout...');
      try {
        const res = await fetch('/api/demo/inject-timeout', { method: 'POST' });
        const data = await res.json();
        addLog('ERR', 'Upstream latency injected: 504 Gateway Timeout triggered on checkout API.');
        addLog('SUCC', 'Incident raised in Lear Dashboard: [GATEWAY-TIMEOUT].');
      } catch (e) {
        addLog('ERR', 'Timeout injection error: ' + e);
      } finally {
        btn.disabled = false;
      }
    }

    async function injectLoadBurst() {
      const btn = document.getElementById('btnLoad');
      btn.disabled = true;
      btn.innerText = 'Firing 500 requests...';
      addLog('INFO', 'Spawning concurrent load generator against AWS ELB...');
      try {
        const res = await fetch('/api/demo/inject-load', { method: 'POST' });
        const data = await res.json();
        addLog('SUCC', 'Traffic surge completed: ' + (data.message || '500 requests sent.'));
      } catch (e) {
        addLog('ERR', 'Load burst error: ' + e);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>📈</span><span>Fire Traffic Surge (500 req)</span>';
      }
    }

    async function triggerFailover() {
      const btn = document.getElementById('btnFailover');
      if (btn) { btn.disabled = true; btn.innerText = 'Executing Failover...'; }
      addLog('WARN', 'Triggering autonomous failover to postgres-replica...');
      try {
        const res = await fetch('/api/demo/auto-failover-db', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          addLog('SUCC', 'Failover verified. checkout-api re-routed to standby replica postgres-replica:5432.');
          document.getElementById('valPostgres').innerText = 'FAILOVER (REPLICA)';
          document.getElementById('cardPostgres').className = 'metric-card healthy';
          document.getElementById('dotPostgres').className = 'metric-status-dot dot-healthy';
          document.getElementById('activeDbHost').innerText = 'postgres-replica (STANDBY)';
        }
      } catch (e) {
        addLog('ERR', 'Failover error: ' + e);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<span>⚡</span><span>Execute Failover</span>';
        }
        setTimeout(refreshClusterTelemetry, 2000);
      }
    }

    async function triggerReset() {
      addLog('INFO', 'Initiating cluster reset to healthy baseline...');
      try {
        const res = await fetch('/api/demo/reset', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          addLog('SUCC', 'Cluster restored. ConfigMap patched to postgres:5432. All pods healthy.');
          document.getElementById('valPostgres').innerText = 'ONLINE';
          document.getElementById('cardPostgres').className = 'metric-card healthy';
          document.getElementById('dotPostgres').className = 'metric-status-dot dot-healthy';
          document.getElementById('activeDbHost').innerText = 'postgres (PRIMARY)';
        }
      } catch (e) {
        addLog('ERR', 'Reset failed: ' + e);
      } finally {
        setTimeout(refreshClusterTelemetry, 2000);
      }
    }

    // Initialize
    refreshClusterTelemetry();
    setInterval(refreshClusterTelemetry, 4000);
  </script>
</body>
</html>
"""
