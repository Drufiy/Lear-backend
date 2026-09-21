"""Clean, Realistic Customer Storefront for Lear Demo.

Designed with clean typography, minimalistic cards, real hardware/SaaS items,
and real checkout against the AWS EKS cluster.
Zero AI slop — clean, modern design inspired by Stripe / Linear / Vercel Commerce.
"""

def generate_customer_store_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Lear Edge Systems — Enterprise Hardware & Telemetry</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #FAFAFA;
      --card-bg: #FFFFFF;
      --text: #0F172A;
      --muted: #64748B;
      --border: #E2E8F0;
      --border-focus: #0F172A;
      --primary: #0F172A;
      --primary-hover: #1E293B;
      --accent: #2563EB;
      --accent-light: #EFF6FF;
      --emerald: #059669;
      --rose: #E11D48;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
    }
    header {
      background: #FFFFFF;
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 40;
    }
    .header-inner {
      max-width: 1200px;
      margin: 0 auto;
      padding: 16px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 17px;
      font-weight: 700;
      letter-spacing: -0.5px;
      color: var(--text);
      text-decoration: none;
    }
    .logo-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      font-weight: 600;
      background: #F1F5F9;
      color: #475569;
      padding: 3px 8px;
      border-radius: 6px;
      border: 1px solid var(--border);
    }
    .nav-links {
      display: flex;
      align-items: center;
      gap: 20px;
      font-size: 13px;
      font-weight: 500;
      color: var(--muted);
    }
    .nav-links a {
      color: inherit;
      text-decoration: none;
      transition: color 0.15s;
    }
    .nav-links a:hover { color: var(--text); }
    .btn-admin {
      background: #F8FAFC;
      border: 1px solid var(--border);
      color: #334155;
      font-size: 12px;
      font-weight: 600;
      padding: 7px 14px;
      border-radius: 8px;
      text-decoration: none;
      transition: all 0.15s;
    }
    .btn-admin:hover {
      background: #F1F5F9;
      border-color: #CBD5E1;
      color: #0F172A;
    }
    .hero {
      max-width: 1200px;
      margin: 0 auto;
      padding: 48px 24px 32px 24px;
    }
    .hero-pre {
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--accent);
      margin-bottom: 8px;
    }
    .hero h1 {
      font-size: 32px;
      font-weight: 800;
      letter-spacing: -0.8px;
      color: var(--text);
      margin-bottom: 8px;
    }
    .hero p {
      font-size: 15px;
      color: var(--muted);
      max-width: 620px;
      line-height: 1.5;
    }
    .system-status-banner {
      margin-top: 20px;
      padding: 10px 16px;
      border-radius: 8px;
      font-size: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border: 1px solid var(--border);
      background: #FFFFFF;
    }
    .status-indicator {
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 500;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--emerald);
    }
    .dot.outage {
      background: var(--rose);
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
      0% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(1.2); }
      100% { opacity: 1; transform: scale(1); }
    }
    .grid {
      max-width: 1200px;
      margin: 0 auto;
      padding: 0 24px 64px 24px;
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 32px;
    }
    .catalog {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 20px;
    }
    .product-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.2s;
    }
    .product-card:hover {
      border-color: #CBD5E1;
      box-shadow: 0 8px 24px rgba(0,0,0,0.04);
    }
    .product-badge {
      align-self: flex-start;
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      background: var(--accent-light);
      color: var(--accent);
      padding: 4px 8px;
      border-radius: 6px;
      margin-bottom: 14px;
    }
    .product-title {
      font-size: 16px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 6px;
      letter-spacing: -0.3px;
    }
    .product-desc {
      font-size: 13px;
      color: var(--muted);
      line-height: 1.5;
      margin-bottom: 20px;
    }
    .product-footer {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-top: 16px;
      border-top: 1px solid #F1F5F9;
    }
    .product-price {
      font-size: 18px;
      font-weight: 800;
      color: var(--text);
    }
    .product-price span {
      font-size: 12px;
      font-weight: 500;
      color: var(--muted);
    }
    .btn-buy {
      background: var(--primary);
      color: #FFFFFF;
      border: none;
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
    }
    .btn-buy:hover { background: var(--primary-hover); }

    /* Order Summary Sidebar */
    .cart-pane {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      height: fit-content;
      position: sticky;
      top: 96px;
    }
    .cart-title {
      font-size: 15px;
      font-weight: 700;
      margin-bottom: 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .cart-item {
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      padding: 10px 0;
      border-bottom: 1px solid #F1F5F9;
    }
    .cart-item-name { font-weight: 500; }
    .cart-item-price { font-weight: 600; color: var(--text); }
    .cart-totals {
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .total-row {
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      color: var(--muted);
    }
    .total-row.final {
      font-size: 16px;
      font-weight: 800;
      color: var(--text);
      margin-top: 6px;
      padding-top: 10px;
      border-top: 1px solid #F1F5F9;
    }
    .btn-checkout {
      width: 100%;
      margin-top: 20px;
      background: #0F172A;
      color: #FFFFFF;
      border: none;
      padding: 13px 20px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.15s;
    }
    .btn-checkout:hover {
      background: #1E293B;
      transform: translateY(-1px);
    }
    .btn-checkout:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    /* Modal / Result overlay */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.6);
      backdrop-filter: blur(4px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 50;
      padding: 20px;
    }
    .modal-overlay.active { display: flex; }
    .modal-card {
      background: #FFFFFF;
      border-radius: 14px;
      max-width: 480px;
      width: 100%;
      padding: 32px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.15);
      position: relative;
    }
    .modal-icon {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      margin-bottom: 16px;
    }
    .modal-icon.success { background: #ECFDF5; color: #059669; }
    .modal-icon.error { background: #FFF1F2; color: #E11D48; }
    .modal-title { font-size: 19px; font-weight: 800; margin-bottom: 6px; }
    .modal-desc { font-size: 13px; color: var(--muted); line-height: 1.5; margin-bottom: 20px; }
    .receipt-box {
      background: #F8FAFC;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      margin-bottom: 20px;
      line-height: 1.7;
    }
    .btn-close {
      width: 100%;
      padding: 10px;
      background: #0F172A;
      color: #FFFFFF;
      border: none;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <a href="/store" class="logo">
        <span>LEAR EDGE</span>
        <span class="logo-badge">PROD STOREFRONT</span>
      </a>
      <div class="nav-links">
        <a href="/store">Hardware</a>
        <a href="/store">Cloud Modules</a>
        <a href="/store">Documentation</a>
        <a href="/admin" class="btn-admin">⚙️ Chaos Admin Console</a>
      </div>
    </div>
  </header>

  <div class="hero">
    <div class="hero-pre">Live E-Commerce Demo Environment</div>
    <h1>Enterprise Autonomous Infrastructure</h1>
    <p>
      Customer transactions below directly hit the live <strong>checkout-api</strong> and PostgreSQL clusters running on AWS EKS (Mumbai).
    </p>

    <div class="system-status-banner">
      <div class="status-indicator">
        <span class="dot" id="statusDot"></span>
        <span id="statusText">All Microservices Operational (AWS EKS lear-demo)</span>
      </div>
      <div style="font-size: 11px; color: var(--muted); font-family: 'JetBrains Mono', monospace;" id="clusterTarget">
        ELB Target: ap-south-1:8080
      </div>
    </div>
  </div>

  <div class="grid">
    <!-- Products Catalog -->
    <div class="catalog">
      <div class="product-card">
        <div>
          <span class="product-badge">Edge Compute</span>
          <h3 class="product-title">Lear Tensor Node S4</h3>
          <p class="product-desc">
            4-Core edge accelerator unit with secure enclave and hardware telemetry probe.
          </p>
        </div>
        <div class="product-footer">
          <div class="product-price">$49.99 <span>/unit</span></div>
          <button class="btn-buy" onclick="selectItem('Lear Tensor Node S4', 49.99)">Buy Now</button>
        </div>
      </div>

      <div class="product-card">
        <div>
          <span class="product-badge">Networking</span>
          <h3 class="product-title">Sentinel Gateway Router</h3>
          <p class="product-desc">
            Ultra-low latency edge gateway with real-time eBPF packet inspection and mesh sync.
          </p>
        </div>
        <div class="product-footer">
          <div class="product-price">$89.00 <span>/unit</span></div>
          <button class="btn-buy" onclick="selectItem('Sentinel Gateway Router', 89.00)">Buy Now</button>
        </div>
      </div>

      <div class="product-card">
        <div>
          <span class="product-badge">Storage</span>
          <h3 class="product-title">Quantum NVMe Cache Module</h3>
          <p class="product-desc">
            High-IOPS persistent storage card designed for local episodic memory caching.
          </p>
        </div>
        <div class="product-footer">
          <div class="product-price">$120.00 <span>/unit</span></div>
          <button class="btn-buy" onclick="selectItem('Quantum NVMe Cache Module', 120.00)">Buy Now</button>
        </div>
      </div>

      <div class="product-card">
        <div>
          <span class="product-badge">Security</span>
          <h3 class="product-title">SRE Hardware Sentinel Key</h3>
          <p class="product-desc">
            FIDO2 hardware security key enabling cryptographic approval of autonomous changes.
          </p>
        </div>
        <div class="product-footer">
          <div class="product-price">$35.00 <span>/unit</span></div>
          <button class="btn-buy" onclick="selectItem('SRE Hardware Sentinel Key', 35.00)">Buy Now</button>
        </div>
      </div>
    </div>

    <!-- Live Cart Drawer -->
    <div class="cart-pane">
      <div class="cart-title">
        <span>Order Checkout</span>
        <span style="font-size: 11px; color: var(--muted); font-weight: 500;">Direct Live Ingress</span>
      </div>

      <div id="cartItems">
        <div class="cart-item">
          <span class="cart-item-name" id="cartItemName">Lear Tensor Node S4</span>
          <span class="cart-item-price" id="cartItemPrice">$49.99</span>
        </div>
      </div>

      <div class="cart-totals">
        <div class="total-row">
          <span>Subtotal</span>
          <span id="subTotal">$49.99</span>
        </div>
        <div class="total-row">
          <span>Express Shipping</span>
          <span>$5.99</span>
        </div>
        <div class="total-row final">
          <span>Total Amount</span>
          <span id="grandTotal">$55.98</span>
        </div>
      </div>

      <button class="btn-checkout" id="btnCheckout" onclick="processCheckout()">
        <span id="btnText">Place Order & Process Payment</span>
      </button>

      <div style="margin-top: 14px; font-size: 11px; color: var(--muted); text-align: center; line-height: 1.4;">
        🔒 Encrypted PCI-DSS checkout routed through payment-service and postgres DB.
      </div>
    </div>
  </div>

  <!-- Order Result Modal -->
  <div class="modal-overlay" id="resultModal">
    <div class="modal-card">
      <div class="modal-icon success" id="modalIcon">✓</div>
      <h3 class="modal-title" id="modalTitle">Order Confirmed</h3>
      <p class="modal-desc" id="modalDesc">
        Your order has been authorized and dispatched to shipping-service.
      </p>

      <div class="receipt-box" id="modalReceipt">
        <!-- Receipt details populated by JS -->
      </div>

      <div id="modalFooterActions">
        <button class="btn-close" onclick="closeModal()">Done</button>
      </div>
    </div>
  </div>

  <script>
    let currentItem = "Lear Tensor Node S4";
    let currentPrice = 49.99;

    function selectItem(name, price) {
      currentItem = name;
      currentPrice = price;
      document.getElementById('cartItemName').innerText = name;
      document.getElementById('cartItemPrice').innerText = '$' + price.toFixed(2);
      document.getElementById('subTotal').innerText = '$' + price.toFixed(2);
      document.getElementById('grandTotal').innerText = '$' + (price + 5.99).toFixed(2);
    }

    async function processCheckout() {
      const btn = document.getElementById('btnCheckout');
      const text = document.getElementById('btnText');
      btn.disabled = true;
      text.innerText = 'Authorizing payment via AWS ELB...';

      try {
        const res = await fetch('/api/demo/customer-checkout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item: currentItem, price: currentPrice })
        });

        const data = await res.json();

        if (res.ok && data.status === 'COMPLETED') {
          showModal(true, data);
        } else {
          showModal(false, data);
        }
      } catch (e) {
        showModal(false, { error: e.message, code: 502 });
      } finally {
        btn.disabled = false;
        text.innerText = 'Place Order & Process Payment';
      }
    }

    function showModal(isSuccess, data) {
      const modal = document.getElementById('resultModal');
      const icon = document.getElementById('modalIcon');
      const title = document.getElementById('modalTitle');
      const desc = document.getElementById('modalDesc');
      const receipt = document.getElementById('modalReceipt');
      const footer = document.getElementById('modalFooterActions');

      if (isSuccess) {
        icon.className = 'modal-icon success';
        icon.innerText = '✓';
        title.innerText = 'Payment Authorized & Confirmed';
        desc.innerText = 'Transaction completed with 0 errors across microservices.';
        receipt.innerHTML = 
          '<div><strong>ORDER ID:</strong> ' + (data.order_id || 'ord_live') + '</div>' +
          '<div><strong>PAYMENT:</strong> ' + (data.payment?.tx_id || 'tx_ok') + ' (' + (data.payment?.status || 'success') + ')</div>' +
          '<div><strong>SHIPPING:</strong> ' + (data.shipping?.carrier || 'Standard Express') + ' (Est: ' + (data.shipping?.estimated_days || 3) + ' days)</div>' +
          '<div><strong>PERSISTENCE:</strong> <span style="color:#059669;font-weight:700;">' + (data.database || 'Committed to PostgreSQL') + '</span></div>' +
          '<div><strong>STATUS:</strong> <span style="color:#059669;font-weight:700;">HTTP 200 OK</span></div>';
        footer.innerHTML = '<button class="btn-close" onclick="closeModal()">Done</button>';
      } else {
        icon.className = 'modal-icon error';
        icon.innerText = '✕';
        const code = data.code || 502;
        title.innerText = 'Checkout Failed (HTTP ' + code + ')';
        desc.innerText = 'Real-time transaction aborted due to an active infrastructure anomaly in AWS EKS cluster.';
        receipt.innerHTML = 
          '<div><strong style="color:#E11D48;">ERROR TRACE:</strong></div>' +
          '<div style="color:#E11D48;word-break:break-all;margin:4px 0 8px;font-weight:600;">' + (data.error || 'Connection refused: database unreachable') + '</div>' +
          '<div><strong>SERVICE:</strong> checkout-api (Namespace: lear-demo)</div>' +
          '<div><strong>CLUSTER:</strong> AWS EKS (ap-south-1 Mumbai)</div>' +
          '<div style="margin-top:8px;padding-top:8px;border-top:1px dashed #CBD5E1;color:#2563EB;"><strong>⚡ AUTONOMOUS SRE:</strong> Lear Copilot has detected this incident. Authorize standby failover in Lear Dashboard or War Room to restore service.</div>';
        footer.innerHTML = 
          '<div style="display:flex;gap:8px;width:100%;">' +
          '<button class="btn-close" style="background:#2563EB;flex:1;" onclick="closeModal(); processCheckout();">🔄 Retry Transaction</button>' +
          '<a href="/admin" class="btn-close" style="background:#0F172A;flex:1;text-align:center;text-decoration:none;display:inline-block;padding:10px 0;" target="_blank">⚙️ Admin</a>' +
          '<button class="btn-close" style="background:#64748B;width:80px;" onclick="closeModal()">Dismiss</button>' +
          '</div>';
      }

      modal.classList.add('active');
    }

    function closeModal() {
      document.getElementById('resultModal').classList.remove('active');
    }

    // Live pod health & incident poller
    setInterval(async () => {
      try {
        const res = await fetch('/api/demo/status');
        const data = await res.json();
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        const target = document.getElementById('clusterTarget');
        
        if (data.database_host) {
          target.innerText = 'DB: ' + data.database_host + ':5432 | ELB: ap-south-1:80';
        }

        const isChaos = data.chaos_state && (data.chaos_state.active_error || data.chaos_state.gateway_timeout);
        const hasCrashingPods = data.pods && data.pods.some(p => p.name && p.name.includes('checkout-api') && (p.status.includes('CrashLoop') || p.status.includes('Error') || !p.ready));

        if (isChaos || hasCrashingPods || !data.elb_healthy) {
          dot.className = 'dot outage';
          let errTitle = 'Production Outage: checkout-api degraded';
          if (data.latest_incident && data.latest_incident.title && data.latest_incident.status !== 'RESOLVED') {
            errTitle = data.latest_incident.title;
          } else if (data.chaos_state && data.chaos_state.gateway_timeout) {
            errTitle = '504 Gateway Timeout: Downstream Payment Egress Latency';
          }
          text.innerText = errTitle;
          text.style.color = '#E11D48';
        } else {
          dot.className = 'dot';
          if (data.database_host && data.database_host.includes('replica')) {
            text.innerText = 'All Microservices Operational (Failover Active: ' + data.database_host + ')';
          } else {
            text.innerText = 'All Microservices Operational (AWS EKS lear-demo: postgres:5432)';
          }
          text.style.color = '#059669';
        }
      } catch (e) {}
    }, 3000);
  </script>
</body>
</html>
"""
