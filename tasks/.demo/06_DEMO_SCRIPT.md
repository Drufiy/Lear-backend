# Demo Script — Minute-by-Minute Presenter Guide

**For:** Gradup Capital MD  
**Duration:** 12 minutes + Q&A  
**Presenter:** Anant  

---

## Before You Start

```bash
# Terminal 1 — verify everything is healthy
kubectl get pods -n lear-demo         # All Running
kubectl top pods -n lear-demo         # Non-zero CPU (load is hitting)

# Terminal 2 — start watcher
prash watch --provider kubernetes

# Desktop — open Lear app
# Dashboard should show green widgets for all services

# Browser tab — Datadog dashboard (optional, for correlation act)
```

**Have ready in separate terminal tabs:**
- Tab 1: `prash watch` (running)
- Tab 2: Ready to type `prash fix` commands
- Tab 3: Ready to run `inject-configmap-break.sh`

---

## ACT 1: "The Platform" (0:00 - 2:00)

### 0:00 — Open Lear Desktop

> **Say:** "Let me show you what Lear sees right now."

**Do:** Show the Dashboard. Point to:
- Pod health widgets (all green)
- CPU/memory metrics (non-zero, live)
- Request rate (loadgen is running)

### 0:30 — Show Integrations

**Do:** Click Integrations page.

> **Say:** "We're connected to Kubernetes, Datadog, and GitHub. These are real connections — real API keys on this machine. They never touch our servers."

### 1:00 — Show the load & live traffic

> **Say:** "Simulated users are hitting checkout right now. This is running on our live AWS EKS cluster in Mumbai."

**Do:** Show `kubectl get pods -n lear-demo`, or hit the public ELB live:
```bash
# Live AWS ELB checkout invocation:
curl.exe -s -X POST http://a4131978a1f9447f29e142dc50cba962-1618812194.ap-south-1.elb.amazonaws.com/api/checkout -H "Content-Type: application/json" -d "{\"cart_id\": \"live-demo\", \"user_id\": \"gradup-md\", \"items\": [{\"id\": \"item-1\", \"price\": 49.99}]}"
# Returns: {"order_id": "...", "status": "COMPLETED", "payment": {"status": "success"}, "shipping": {...}}
```

### 1:30 — Show the watcher

**Do:** Point to the terminal running `prash watch`.

> **Say:** "Prash is watching every service. It polls every 30 seconds. Right now everything is healthy."

---

## ACT 2: "The Break" (2:00 - 6:00) — THE MONEY SHOT

### 2:00 — Inject the failure

> **Say:** "Let me break something."

**Do:** In Tab 3, run:
```powershell
# PowerShell (Windows):
powershell -ExecutionPolicy Bypass -File .\scripts\demo\scripts\inject-configmap-break.ps1

# Or Bash (Linux/Mac):
./scripts/demo/scripts/inject-configmap-break.sh
```

> **Say:** "I just corrupted the database config. The checkout service can't reach Postgres anymore."

### 2:15-2:30 — Wait for detection

**Do:** Watch the terminal running `prash watch`. Within 15-30 seconds:
- Desktop notification pops up: 🔴 "checkout-api: CrashLoopBackOff"
- Watcher terminal prints the detection
- Dashboard goes red

> **Say:** "Prash detected it. 15 seconds. No human checked anything."

### 2:45 — Run diagnosis

**Do:** In Tab 2:
```bash
prash fix lear-demo/checkout-api-<TAB-complete-the-pod-name>
```

> **Say:** "Now let's see if Prash can figure out what went wrong."

### 3:00-3:15 — Diagnosis appears

**Wait for the diagnosis panel.** It should show:
- Category: `runtime`
- Root cause: ConfigMap `DATABASE_HOST` points to `postgres-wrong`
- Confidence: ~90%
- Recommended: `edit-configmap`

> **Say:** "Root cause in 10 seconds. It read the pod logs, the events, the ConfigMap, and figured out that DATABASE_HOST is wrong. 92% confidence."

### 3:15 — Options menu

Prash shows options:
1. ✅ Edit ConfigMap to fix DATABASE_HOST [APPROVAL]
2. Restart pod [SAFE]
3. Investigate further

> **Say:** "It's giving me choices. Option 1 is the real fix — it needs my approval because it's modifying a ConfigMap. Option 2 is a restart, which is safe-tier and could run automatically. Prash knows the difference."

### 3:30 — Approve

**Do:** Select option 1 (or type `1`).

> **Say:** "Approved."

### 3:45 — Execution and verification

Watch Prash:
1. Patch the ConfigMap
2. Restart the deployment
3. Wait for the pod to come back
4. Verify: readiness probe passes

> **Say:** "It fixed the ConfigMap, restarted the deployment, and verified the pod is healthy. Under 60 seconds from break to recovery."

### 4:15 — Show the audit log

**Do:**
```bash
prash audit
```

> **Say:** "Every action is logged. Append-only — Prash can never rewrite its own history. This is the immutable audit trail that enterprise compliance requires."

### 4:30 — Show notification

> **Say:** "The team got a Slack notification when it broke, and another when it recovered. If this happened at 3am, the on-call engineer would have woken up to a solved problem."

---

## ACT 3: "The Memory" (6:00 - 8:00)

### 6:00 — Reset, then break again

**Do:**
```powershell
# PowerShell:
powershell -ExecutionPolicy Bypass -File .\scripts\demo\scripts\reset-configmap.ps1
# Wait 10 seconds for pod to recover
powershell -ExecutionPolicy Bypass -File .\scripts\demo\scripts\inject-configmap-break.ps1

# Or Bash:
./scripts/demo/scripts/reset-configmap.sh
./scripts/demo/scripts/inject-configmap-break.sh
```

*(Tip: You can also pre-seed or reset memory with `.\scripts\demo\seed-memory.ps1` or `.\scripts\demo\reset-memory.ps1`)*

> **Say:** "Same failure. Different time. Let's see if Prash remembers."

### 6:30 — Run fix again

**Do:**
```bash
prash fix lear-demo/checkout-api-<pod>
```

The diagnosis should now show the **REPO MEMORY** section:
- "This matches a previous verified fix (92% confidence)"
- Same root cause, same recommended action

> **Say:** "It remembers. Same root cause, same fix, previously verified. AWS's team called this 'episodic memory' — if the agent solved it before and nothing changed, replay the proven fix instead of re-deriving from scratch."

### 7:00 — Approve and fix

> **Say:** "This time it's faster because it's not guessing. It's replaying a verified solution."

### 7:30 — Show the second audit entry

> **Say:** "Two entries. Two incidents. Both logged. Both verified."

---

## ACT 4: "The Safety Rails" (8:00 - 10:00)

### 8:00 — Permission system

**Do:**
```bash
prash config
```

> **Say:** "Five permission modes. Right now we're in 'ask' — Prash always asks before acting. For production, you can set 'environment-scoped': automatic on staging, always asks on prod. For a compliance audit: 'read-only' — Prash can't touch anything."

### 8:30 — Circuit breaker

**Do:**
```bash
prash circuit status
```

> **Say:** "If Prash restarts a pod and it crashes again, and it restarts again — after 5 actions in 60 seconds, the circuit breaker trips. It stops, escalates to a human, and refuses to act until manually reset. No runaway loops."

### 9:00 — Credential security

> **Say:** "Every API key — AWS, Kubernetes, Datadog — stays on this machine. Our servers never see them, never touch them, never store them. That's not a feature. That's the architecture."

**Do:** Show Settings → credential masking in the desktop app.

---

## ACT 5: "The Desktop" (10:00 - 11:00)

### 10:00 — Conversational AI

**Do:** Open the Chatbot. Type:

```
what happened to checkout-api in the last 10 minutes?
```

> **Say:** "Natural language. The team doesn't need to learn CLI commands."

### 10:30 — Dashboard widgets

> **Say:** "AI-generated dashboard. It looks at what's connected and builds the widgets automatically."

---

## CLOSE: "The Moat" (11:00 - 12:00)

> **Say each point clearly. This is what the MD remembers.**

1. > "AWS DevOps Guru tells you something is wrong. We diagnose why and fix it — with your approval."

2. > "We're not competing with monitoring. Monitoring is a commodity. We're competing with the 3am on-call engineer who has to wake up, open 4 tools, figure out what happened, and type the fix. We do that in 60 seconds."

3. > "Credentials never leave the machine. That's not just trust — it's the only way enterprise will let an AI agent touch their infrastructure."

4. > "Start read-only. Give it to a team for two months. They build confidence. Then flip the switch to auto-safe. That's how trust is earned, not declared."

5. > "Target customer: the 20-50 engineer startup that can't hire a 5th DevOps engineer but needs to run like they have 10."

---

## If Something Goes Wrong

| Problem | What to do | What to say |
|---|---|---|
| Watcher doesn't detect | Run `prash fix` manually | "Let me show you the diagnosis directly" |
| Diagnosis takes >30s | Wait patiently | "It's reading logs and events from the cluster" |
| Wrong diagnosis | Show it's uncertain | "Notice it's 65% confidence — it's telling us it's not sure" |
| Pod won't recover | Run `reset-demo.sh` | "Let me reset the environment" |
| Desktop won't connect | Use CLI only | "The CLI is the core product — the desktop is the experience layer" |
| Datadog down | Skip correlation | "Let me show the K8s-native flow" |
