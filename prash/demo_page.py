"""Lear Interactive Demo Control Center & Storefront.

Serves an executive-grade dashboard allowing presenters to:
  1. Demonstrate the live customer storefront experience and impact of outages.
  2. Inject real Kubernetes failure (ConfigMap break).
  3. Witness real-time detection, Datadog correlation, and DeepSeek AI auto-remediation.
  4. View and dispatch executive HTML alert emails.
"""
from __future__ import annotations

DEMO_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lear | Autonomous SRE Demo & Storefront</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #07090E;
      --surface: #0D111A;
      --surface-border: #1B2333;
      --surface-hover: #141A28;
      --primary: #10B981;
      --primary-glow: rgba(16, 185, 129, 0.25);
      --danger: #F43F5E;
      --danger-glow: rgba(244, 63, 94, 0.25);
      --warning: #F59E0B;
      --cyan: #06B6D4;
      --text-main: #F8FAFC;
      --text-muted: #94A3B8;
      --text-dim: #64748B;
    }
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    body {
      background-color: var(--bg);
      color: var(--text-main);
      font-family: 'Inter', -apple-system, sans-serif;
      overflow-x: hidden;
      min-height: 100vh;
    }
    header {
      background: rgba(13, 17, 26, 0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--surface-border);
      padding: 14px 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .logo-group {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .logo {
      font-size: 20px;
      font-weight: 800;
      letter-spacing: 1px;
      color: #FFF;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .logo span {
      color: var(--primary);
    }
    .status-badge {
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: var(--primary);
      padding: 5px 12px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--primary);
      box-shadow: 0 0 10px var(--primary);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(1.3); }
      100% { opacity: 1; transform: scale(1); }
    }
    .cluster-info {
      font-size: 12px;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .btn-email-preview {
      background: #1E293B;
      border: 1px solid var(--surface-border);
      color: #E2E8F0;
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }
    .btn-email-preview:hover {
      background: #334155;
      border-color: #475569;
    }

    .main-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
      padding: 24px;
      max-width: 1600px;
      margin: 0 auto;
    }

    .pane {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 14px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      box-shadow: 0 8px 30px rgba(0,0,0,0.4);
    }
    .pane-header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--surface-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(20, 26, 40, 0.4);
    }
    .pane-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .pane-subtitle {
      font-size: 12px;
      color: var(--text-muted);
    }
    .pane-body {
      padding: 20px;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    /* Storefront Styles */
    .store-banner {
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(6, 182, 212, 0.05) 100%);
      border: 1px solid rgba(16, 185, 129, 0.2);
      border-radius: 10px;
      padding: 14px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .store-banner.error {
      background: linear-gradient(135deg, rgba(244, 63, 94, 0.15) 0%, rgba(239, 68, 68, 0.05) 100%);
      border-color: rgba(244, 63, 94, 0.4);
    }
    .store-banner h4 {
      font-size: 14px;
      font-weight: 700;
    }
    .store-banner p {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 2px;
    }
    .product-list {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
    }
    .product-card {
      background: #111724;
      border: 1px solid var(--surface-border);
      border-radius: 10px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.2s;
    }
    .product-card:hover {
      border-color: #2D3A54;
      transform: translateY(-2px);
    }
    .product-icon {
      font-size: 28px;
      margin-bottom: 8px;
    }
    .product-name {
      font-size: 13px;
      font-weight: 600;
      color: #E2E8F0;
    }
    .product-price {
      font-size: 15px;
      font-weight: 700;
      color: var(--primary);
      margin: 8px 0;
    }
    .btn-add-cart {
      background: rgba(16, 185, 129, 0.15);
      color: #34D399;
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
    }
    .checkout-box {
      background: #111724;
      border: 1px solid var(--surface-border);
      border-radius: 10px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .checkout-summary {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px dashed var(--surface-border);
      padding-bottom: 12px;
    }
    .checkout-summary .total {
      font-size: 20px;
      font-weight: 800;
      color: #FFF;
    }
    .btn-checkout {
      background: linear-gradient(135deg, #10B981 0%, #059669 100%);
      color: #FFF;
      border: none;
      padding: 14px;
      border-radius: 8px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      box-shadow: 0 4px 15px var(--primary-glow);
      transition: all 0.2s;
    }
    .btn-checkout:hover:not(:disabled) {
      transform: translateY(-1px);
      box-shadow: 0 6px 20px var(--primary-glow);
    }
    .btn-checkout:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    .order-status-feed {
      background: #090C13;
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      padding: 14px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      min-height: 120px;
      max-height: 160px;
      overflow-y: auto;
    }
    .feed-line {
      margin-bottom: 6px;
      display: flex;
      gap: 8px;
    }
    .feed-line.ok { color: #34D399; }
    .feed-line.err { color: #F43F5E; }
    .feed-line.warn { color: #FBBF24; }
    .feed-line.info { color: #94A3B8; }

    /* SRE Engine Controls */
    .service-radar {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }
    .radar-card {
      background: #111724;
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .radar-card.error {
      border-color: rgba(244, 63, 94, 0.6);
      background: rgba(244, 63, 94, 0.08);
    }
    .radar-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .radar-name {
      font-size: 12px;
      font-weight: 700;
      color: #E2E8F0;
    }
    .radar-pill {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
      background: rgba(16, 185, 129, 0.2);
      color: #34D399;
    }
    .radar-card.error .radar-pill {
      background: rgba(244, 63, 94, 0.2);
      color: #FB7185;
    }
    .radar-detail {
      font-size: 11px;
      color: var(--text-dim);
    }

    .control-actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .btn-action {
      padding: 12px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .btn-break {
      background: rgba(244, 63, 94, 0.15);
      border: 1px solid rgba(244, 63, 94, 0.4);
      color: #FB7185;
    }
    .btn-break:hover {
      background: rgba(244, 63, 94, 0.25);
    }
    .btn-fix {
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #34D399;
    }
    .btn-fix:hover {
      background: rgba(16, 185, 129, 0.25);
    }
    .btn-reset {
      background: #1E293B;
      border: 1px solid var(--surface-border);
      color: #E2E8F0;
    }
    .btn-reset:hover {
      background: #334155;
    }
    .btn-traffic {
      background: rgba(6, 182, 212, 0.15);
      border: 1px solid rgba(6, 182, 212, 0.4);
      color: #38BDF8;
    }
    .btn-traffic:hover {
      background: rgba(6, 182, 212, 0.25);
    }

    .terminal-box {
      background: #07090F;
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      padding: 14px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      color: #CBD5E1;
      height: 220px;
      overflow-y: auto;
      line-height: 1.6;
    }
    .term-tag {
      font-weight: 700;
    }
    .tag-brain { color: #818CF8; }
    .tag-k8s { color: #38BDF8; }
    .tag-dd { color: #F472B6; }
    .tag-fix { color: #34D399; }
    .tag-err { color: #F43F5E; }

    /* Modal Styles */
    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.8);
      backdrop-filter: blur(8px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 100;
      padding: 24px;
    }
    .modal-overlay.active {
      display: flex;
    }
    .modal-content {
      background: #0E131F;
      border: 1px solid var(--surface-border);
      border-radius: 14px;
      width: 100%;
      max-width: 760px;
      max-height: 90vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      box-shadow: 0 20px 50px rgba(0,0,0,0.6);
    }
    .modal-header {
      padding: 16px 24px;
      border-bottom: 1px solid var(--surface-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #131A2B;
    }
    .modal-body {
      padding: 0;
      flex: 1;
      overflow-y: auto;
      background: #080B11;
    }
    .email-frame {
      width: 100%;
      height: 520px;
      border: none;
    }
    .modal-footer {
      padding: 14px 24px;
      border-top: 1px solid var(--surface-border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #101624;
    }
    .btn-close {
      background: #1E293B;
      color: #E2E8F0;
      border: 1px solid var(--surface-border);
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
    }

    /* Toast Notification */
    .toast-alert {
      position: fixed;
      top: 76px;
      right: 28px;
      background: #131A2B;
      border: 1px solid var(--danger);
      box-shadow: 0 10px 30px rgba(244, 63, 94, 0.3);
      border-radius: 10px;
      padding: 16px 20px;
      display: none;
      align-items: center;
      gap: 14px;
      z-index: 90;
      animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      max-width: 420px;
    }
    .toast-alert.active {
      display: flex;
    }
    @keyframes slideIn {
      from { transform: translateX(100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    .toast-icon {
      font-size: 24px;
    }
    .toast-title {
      font-size: 14px;
      font-weight: 700;
      color: #F8FAFC;
    }
    .toast-desc {
      font-size: 12px;
      color: #CBD5E1;
      margin-top: 2px;
    }
  </style>
</head>
<body>
  <header>
    <div class="logo-group">
      <div class="logo">LEAR<span>.AI</span></div>
      <div class="status-badge" id="sreBadge">
        <div class="pulse-dot"></div>
        AUTONOMOUS SRE ACTIVE
      </div>
    </div>
    <div class="cluster-info">
      <span>☁️ AWS EKS: <strong>lear-demo</strong> (ap-south-1)</span>
      <span>🧠 Brain: <strong>DeepSeek + Kimi</strong></span>
      <span>📊 Datadog: <strong>Connected</strong></span>
    </div>
    <div class="header-actions">
      <button class="btn-email-preview" onclick="openEmailModal()">
        ✉️ Inspect Alert Email
      </button>
    </div>
  </header>

  <div class="toast-alert" id="incidentToast">
    <div class="toast-icon">🚨</div>
    <div>
      <div class="toast-title" id="toastTitle">CRITICAL INCIDENT DETECTED</div>
      <div class="toast-desc" id="toastDesc">checkout-api CrashLoopBackOff • Email Alert Dispatched</div>
    </div>
    <button class="btn-email-preview" style="padding: 4px 8px; font-size: 11px;" onclick="openEmailModal()">View Email</button>
  </div>

  <div class="main-grid">
    <!-- LEFT PANE: Customer Storefront Experience -->
    <div class="pane">
      <div class="pane-header">
        <div>
          <div class="pane-title">🛒 Customer Storefront ("Lear Hardware")</div>
          <div class="pane-subtitle">Live production e-commerce checkout hitting AWS ELB</div>
        </div>
        <span class="status-badge" id="storeStatusBadge">100% HEALTHY</span>
      </div>
      <div class="pane-body">
        <div class="store-banner" id="storeBanner">
          <div>
            <h4 id="bannerTitle">🟢 Checkout Gateway Online</h4>
            <p id="bannerDesc">Database connected • Payment & Shipping microservices active</p>
          </div>
          <div style="font-size: 13px; font-weight: 700;" id="bannerLatency">18ms</div>
        </div>

        <div class="product-list">
          <div class="product-card">
            <div class="product-icon">🛡️</div>
            <div class="product-name">AI SRE Sentinel Key</div>
            <div class="product-price">$49.99</div>
            <button class="btn-add-cart" onclick="selectItem('AI SRE Sentinel Key', 49.99)">Selected</button>
          </div>
          <div class="product-card">
            <div class="product-icon">⚡</div>
            <div class="product-name">Cloud Edge Appliance</div>
            <div class="product-price">$199.00</div>
            <button class="btn-add-cart" onclick="selectItem('Cloud Edge Appliance', 199.00)">Select</button>
          </div>
          <div class="product-card">
            <div class="product-icon">📦</div>
            <div class="product-name">Enterprise EKS Unit</div>
            <div class="product-price">$499.00</div>
            <button class="btn-add-cart" onclick="selectItem('Enterprise EKS Unit', 499.00)">Select</button>
          </div>
        </div>

        <div class="checkout-box">
          <div class="checkout-summary">
            <div>
              <div style="font-size: 12px; color: var(--text-muted);">Cart Item</div>
              <strong id="cartItemName" style="font-size: 14px;">AI SRE Sentinel Key</strong>
            </div>
            <div style="text-align: right;">
              <div style="font-size: 12px; color: var(--text-muted);">Total Price</div>
              <div class="total" id="cartItemPrice">$49.99</div>
            </div>
          </div>
          <button class="btn-checkout" id="checkoutBtn" onclick="performCustomerCheckout()">
            💳 Place Order & Process Checkout
          </button>
        </div>

        <div>
          <div style="font-size: 12px; font-weight: 700; color: var(--text-muted); margin-bottom: 8px;">
            LIVE CUSTOMER ORDER ACTIVITY STREAM
          </div>
          <div class="order-status-feed" id="orderFeed">
            <div class="feed-line info">[INIT] Storefront loaded. Connected to AWS ELB checkout route.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- RIGHT PANE: Lear Autonomous SRE Control Engine -->
    <div class="pane">
      <div class="pane-header">
        <div>
          <div class="pane-title">⚡ Lear Autonomous SRE Engine</div>
          <div class="pane-subtitle">Live EKS topology, failure injection & DeepSeek diagnosis</div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-muted);">
          <span>Auto-Fix:</span>
          <strong style="color: var(--primary);">ENABLED</strong>
        </div>
      </div>
      <div class="pane-body">
        <div class="service-radar">
          <div class="radar-card" id="cardFrontend">
            <div class="radar-header">
              <span class="radar-name">frontend</span>
              <span class="radar-pill" id="pillFrontend">Running</span>
            </div>
            <span class="radar-detail">nginx :80 (Public ELB)</span>
          </div>
          <div class="radar-card" id="cardCheckout">
            <div class="radar-header">
              <span class="radar-name">checkout-api</span>
              <span class="radar-pill" id="pillCheckout">Running</span>
            </div>
            <span class="radar-detail">FastAPI :8080 (Core)</span>
          </div>
          <div class="radar-card" id="cardPayment">
            <div class="radar-header">
              <span class="radar-name">payment-service</span>
              <span class="radar-pill" id="pillPayment">Running</span>
            </div>
            <span class="radar-detail">Auth Engine :5000</span>
          </div>
          <div class="radar-card" id="cardShipping">
            <div class="radar-header">
              <span class="radar-name">shipping-service</span>
              <span class="radar-pill" id="pillShipping">Running</span>
            </div>
            <span class="radar-detail">Rate Calculator :5001</span>
          </div>
          <div class="radar-card" id="cardPostgres">
            <div class="radar-header">
              <span class="radar-name">postgres</span>
              <span class="radar-pill" id="pillPostgres">Running</span>
            </div>
            <span class="radar-detail">Database :5432</span>
          </div>
          <div class="radar-card" id="cardDatadog">
            <div class="radar-header">
              <span class="radar-name">datadog-agent</span>
              <span class="radar-pill" id="pillDatadog">Active</span>
            </div>
            <span class="radar-detail">DaemonSet (2 nodes)</span>
          </div>
        </div>

        <div class="control-actions">
          <button class="btn-action btn-break" id="btnBreak" onclick="injectFailure()">
            💥 Inject ConfigMap Break
          </button>
          <button class="btn-action btn-fix" id="btnFix" onclick="triggerAutoFix()">
            🧠 Trigger Lear Auto-Fix
          </button>
          <button class="btn-action btn-traffic" id="btnTraffic" onclick="toggleTraffic()">
            🚀 Start Background Traffic
          </button>
          <button class="btn-action btn-reset" onclick="resetCluster()">
            🔄 Reset Cluster to Healthy
          </button>
        </div>

        <div>
          <div style="font-size: 12px; font-weight: 700; color: var(--text-muted); margin-bottom: 8px;">
            LEAR AUTONOMOUS REASONING & SRE TERMINAL
          </div>
          <div class="terminal-box" id="termLog">
            <div><span class="term-tag tag-brain">[BRAIN]</span> DeepSeek AI model engine connected and warm.</div>
            <div><span class="term-tag tag-k8s">[K8S]</span> Watching namespace 'lear-demo' on AWS EKS cluster.</div>
            <div><span class="term-tag tag-dd">[DATADOG]</span> Metric monitor 'Lear Demo: checkout-api health' reporting OK.</div>
            <div><span class="term-tag tag-fix">[READY]</span> Autonomous auto-safe execution circuit active.</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- EMAIL MODAL -->
  <div class="modal-overlay" id="emailModal">
    <div class="modal-content">
      <div class="modal-header">
        <div style="font-weight: 700; font-size: 16px; color: #FFF;">
          ✉️ Dispatched Incident Email Preview
        </div>
        <button class="btn-close" onclick="closeEmailModal()">✕ Close</button>
      </div>
      <div class="modal-body">
        <iframe class="email-frame" id="emailIframe" src="/api/demo/emails/latest"></iframe>
      </div>
      <div class="modal-footer">
        <div style="font-size: 12px; color: var(--text-muted);">
          Recipient: <strong id="emailRecipient">oncall-team@lear-demo.com</strong> (SRE Alert)
        </div>
        <button class="btn-email-preview" onclick="sendRealEmail()">
          🚀 Send To My Email Address
        </button>
      </div>
    </div>
  </div>

  <script>
    let currentItem = { name: "AI SRE Sentinel Key", price: 49.99 };
    let trafficInterval = null;
    let isBroken = false;

    function selectItem(name, price) {
      currentItem = { name, price };
      document.getElementById('cartItemName').innerText = name;
      document.getElementById('cartItemPrice').innerText = '$' + price.toFixed(2);
    }

    function logTerminal(tagClass, tagText, msg) {
      const term = document.getElementById('termLog');
      const div = document.createElement('div');
      const time = new Date().toLocaleTimeString();
      div.innerHTML = `<span style="color: #64748B;">[${time}]</span> <span class="term-tag ${tagClass}">[${tagText}]</span> ${msg}`;
      term.appendChild(div);
      term.scrollTop = term.scrollHeight;
    }

    function logOrder(type, msg) {
      const feed = document.getElementById('orderFeed');
      const div = document.createElement('div');
      div.className = `feed-line ${type}`;
      const time = new Date().toLocaleTimeString();
      div.innerText = `[${time}] ${msg}`;
      feed.prepend(div);
    }

    async function performCustomerCheckout() {
      const btn = document.getElementById('checkoutBtn');
      btn.disabled = true;
      btn.innerText = 'Processing Payment...';
      const t0 = performance.now();

      try {
        const resp = await fetch('/api/demo/customer-checkout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            item: currentItem.name,
            price: currentItem.price
          })
        });
        const elapsed = Math.round(performance.now() - t0);
        const data = await resp.json();

        if (data.status === 'COMPLETED') {
          logOrder('ok', `SUCCESS: Order #${data.order_id} placed for $${currentItem.price} (${elapsed}ms)`);
          document.getElementById('bannerLatency').innerText = `${elapsed}ms`;
        } else {
          logOrder('err', `FAILED: ${data.error || '502 Bad Gateway - Connection Refused'} (${elapsed}ms)`);
          triggerOutageUI();
        }
      } catch (err) {
        logOrder('err', `FAILED: Service Unavailable (${err.message})`);
        triggerOutageUI();
      } finally {
        btn.disabled = false;
        btn.innerText = '💳 Place Order & Process Checkout';
      }
    }

    function triggerOutageUI() {
      isBroken = true;
      document.getElementById('storeStatusBadge').innerText = 'OUTAGE DETECTED';
      document.getElementById('storeStatusBadge').style.borderColor = 'var(--danger)';
      document.getElementById('storeStatusBadge').style.color = 'var(--danger)';
      document.getElementById('storeBanner').classList.add('error');
      document.getElementById('bannerTitle').innerText = '🔴 CHECKOUT PIPELINE FAILING';
      document.getElementById('bannerDesc').innerText = 'Orders blocked: checkout-api cannot connect to PostgreSQL database!';
      document.getElementById('cardCheckout').classList.add('error');
      document.getElementById('pillCheckout').innerText = 'CrashLoop';

      // Show toast
      document.getElementById('incidentToast').classList.add('active');
    }

    function restoreHealthyUI() {
      isBroken = false;
      document.getElementById('storeStatusBadge').innerText = '100% HEALTHY';
      document.getElementById('storeStatusBadge').style.borderColor = 'rgba(16, 185, 129, 0.3)';
      document.getElementById('storeStatusBadge').style.color = 'var(--primary)';
      document.getElementById('storeBanner').classList.remove('error');
      document.getElementById('bannerTitle').innerText = '🟢 Checkout Gateway Online';
      document.getElementById('bannerDesc').innerText = 'Database connected • Payment & Shipping microservices active';
      document.getElementById('cardCheckout').classList.remove('error');
      document.getElementById('pillCheckout').innerText = 'Running';
      document.getElementById('incidentToast').classList.remove('active');
    }

    async function injectFailure() {
      logTerminal('tag-err', 'INJECT', 'Patching ConfigMap checkout-api-config: DATABASE_HOST -> postgres-wrong');
      triggerOutageUI();

      try {
        const res = await fetch('/api/demo/inject-failure', { method: 'POST' });
        const d = await res.json();
        logTerminal('tag-dd', 'DATADOG', 'Datadog synthetic monitor triggered: container count < 1');
        logTerminal('tag-err', 'ALERT', 'Email Alert Dispatched: [CRITICAL] checkout-api CrashLoopBackOff');
        
        // Refresh email iframe
        document.getElementById('emailIframe').src = '/api/demo/emails/latest?t=' + Date.now();
      } catch (e) {
        logTerminal('tag-err', 'ERROR', 'Failure inject call failed: ' + e.message);
      }
    }

    async function triggerAutoFix() {
      logTerminal('tag-brain', 'DEEPSEEK', 'Diagnosing root cause with DeepSeek AI brain...');
      logTerminal('tag-brain', 'MEMORY', 'Episodic memory matched prior incident: ConfigMap database host error');
      logTerminal('tag-fix', 'PLAN', 'Action generated: patch ConfigMap to postgres & rollout restart deployment');

      try {
        const res = await fetch('/api/demo/auto-fix', { method: 'POST' });
        const d = await res.json();
        logTerminal('tag-fix', 'APPLIED', 'ConfigMap patched and checkout-api pod rolled out cleanly.');
        logTerminal('tag-k8s', 'VERIFIED', 'Probe check passed: /healthz 200 OK. Pod 1/1 Running.');
        logTerminal('tag-fix', 'RESOLVED', 'Resolution alert email dispatched. Incident closed.');

        restoreHealthyUI();
        document.getElementById('emailIframe').src = '/api/demo/emails/latest?t=' + Date.now();
        logOrder('ok', 'RECOVERED: Checkout API restored by Lear. Ready for customer orders!');
      } catch (e) {
        logTerminal('tag-err', 'ERROR', 'Auto-fix call failed: ' + e.message);
      }
    }

    async function resetCluster() {
      logTerminal('tag-fix', 'RESET', 'Restoring cluster configuration to baseline...');
      await fetch('/api/demo/reset', { method: 'POST' });
      restoreHealthyUI();
      logTerminal('tag-fix', 'RESET', 'All 5 microservices verified 1/1 Running.');
    }

    function toggleTraffic() {
      const btn = document.getElementById('btnTraffic');
      if (trafficInterval) {
        clearInterval(trafficInterval);
        trafficInterval = null;
        btn.innerText = '🚀 Start Background Traffic';
        btn.style.background = 'rgba(6, 182, 212, 0.15)';
        logTerminal('tag-k8s', 'TRAFFIC', 'Background traffic simulation stopped.');
      } else {
        trafficInterval = setInterval(performCustomerCheckout, 800);
        btn.innerText = '🛑 Stop Traffic';
        btn.style.background = 'rgba(244, 63, 94, 0.2)';
        logTerminal('tag-k8s', 'TRAFFIC', 'Background traffic started (continuous orders).');
      }
    }

    function openEmailModal() {
      document.getElementById('emailIframe').src = '/api/demo/emails/latest?t=' + Date.now();
      document.getElementById('emailModal').classList.add('active');
    }

    function closeEmailModal() {
      document.getElementById('emailModal').classList.remove('active');
    }

    async function sendRealEmail() {
      const to = prompt("Enter the email address to send the incident report to:", "anant@example.com");
      if (to) {
        try {
          const res = await fetch('/api/demo/send-email', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ email: to })
          });
          const d = await res.json();
          alert(d.message || "Email dispatched!");
        } catch (e) {
          alert("Could not send email: " + e.message);
        }
      }
    }

    // Polling pod status periodically
    setInterval(async () => {
      try {
        const res = await fetch('/api/demo/status');
        const d = await res.json();
        if (d.pods) {
          const chk = d.pods.find(p => p.name.includes('checkout-api'));
          if (chk && (chk.status.includes('CrashLoop') || chk.status.includes('Error'))) {
            triggerOutageUI();
          } else if (chk && chk.status === 'Running' && chk.ready && isBroken) {
            restoreHealthyUI();
          }
        }
      } catch (e) {}
    }, 4000);
  </script>
</body>
</html>
"""
