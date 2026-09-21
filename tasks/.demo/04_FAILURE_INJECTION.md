# Demo Failure Injection — Pre-Scripted Breaks & Resets

**Owner:** Anant  
**Time to complete:** ~1 hour (scripts + testing)  

---

## Failure Catalog

Three pre-scripted failures, each designed to show a different Prash capability. Only **Failure 1** is needed for the core demo. The others are backup/advanced.

---

### Failure 1: ConfigMap Break (PRIMARY — use this in the demo)

**What breaks:** `checkout-api` ConfigMap `DATABASE_HOST` is patched from `postgres` to `postgres-wrong`. Pod can't reach the database, enters `CrashLoopBackOff`.

**Why this one:** Already proven — this is the exact scenario the `edit-configmap` action was built and live-verified against. Zero risk of it not working.

**Inject:**
```bash
# scripts/demo/scripts/inject-configmap-break.sh
kubectl patch configmap checkout-api-config -n lear-demo \
  --type merge -p '{"data":{"DATABASE_HOST":"postgres-wrong"}}'
kubectl rollout restart deployment/checkout-api -n lear-demo
echo "💥 Failure injected: checkout-api will CrashLoopBackOff (DATABASE_HOST → postgres-wrong)"
```

**What Prash does:**
1. Watcher detects CrashLoopBackOff (~15-30s)
2. `prash fix lear-demo/checkout-api-xxx` diagnoses: "ConfigMap DATABASE_HOST points to nonexistent host"
3. Recommends `edit-configmap` (APPROVAL tier)
4. On approval: patches ConfigMap back to `postgres`, restarts deployment
5. Verifies: pod recovers, readiness probe passes

**Reset:**
```bash
# scripts/demo/scripts/reset-configmap.sh
kubectl patch configmap checkout-api-config -n lear-demo \
  --type merge -p '{"data":{"DATABASE_HOST":"postgres"}}'
kubectl rollout restart deployment/checkout-api -n lear-demo
echo "✅ Reset: DATABASE_HOST restored to 'postgres'"
```

**Tested:** ✅ Live-verified against real Kind cluster (see `k8s-recovery-demo/README.md`)

---

### Failure 2: OOMKill (BACKUP — shows different failure type)

**What breaks:** `checkout-api` memory limit set to 16Mi. Under load, pod gets OOMKilled.

**Inject:**
```bash
# scripts/demo/scripts/inject-oomkill.sh
kubectl set resources deployment/checkout-api -n lear-demo \
  --limits=memory=16Mi
echo "💥 Failure injected: checkout-api will OOMKill under load"
```

**What Prash does:**
1. Watcher detects OOMKilled
2. Diagnosis: "Container killed by OOM (memory limit 16Mi too low for workload)"
3. Recommends: restart-pod (SAFE) or investigate further
4. Shows the brain reasoning through resource constraints

**Reset:**
```bash
# scripts/demo/scripts/reset-oomkill.sh
kubectl set resources deployment/checkout-api -n lear-demo \
  --limits=memory=128Mi --requests=memory=64Mi
echo "✅ Reset: memory limits restored to 128Mi"
```

---

### Failure 3: Combined K8s + Datadog Correlation (ADVANCED — if time permits)

**What breaks:** ConfigMap break on `checkout-api` (Failure 1) + Datadog synthetic monitor fires because the service stops responding.

**Inject:**
```bash
# scripts/demo/scripts/inject-combined.sh

# 1. Break the K8s service
./inject-configmap-break.sh

# 2. The Datadog synthetic monitor watching checkout-api will auto-fire
#    because the service stops responding to its health check.
#    (No manual Datadog break needed — the K8s break cascades.)

echo "💥 Combined failure: K8s CrashLoopBackOff + Datadog synthetic alert"
```

**What Prash does:**
1. Watcher detects BOTH: K8s CrashLoopBackOff AND Datadog monitor alert
2. Correlation module merges them: "One incident, one root cause"
3. Shows unified diagnosis with evidence from both sources
4. Fix resolves both: ConfigMap fix → pod recovers → Datadog monitor clears

**Prerequisites:** 
- Datadog agent deployed on EKS nodes
- Synthetic monitor watching `checkout-api` health endpoint
- `break_datadog.py` run beforehand to set up the monitor

---

## Master Scripts

### `scripts/demo/scripts/deploy.sh`
One-command full deployment:
```bash
#!/bin/bash
set -e
echo "🚀 Deploying Lear Demo Platform..."
kubectl create namespace lear-demo --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f scripts/demo/manifests/ -n lear-demo
echo "⏳ Waiting for all pods to be ready..."
kubectl wait --for=condition=ready pod -l team=lear-demo -n lear-demo --timeout=120s
echo "✅ All services running!"
kubectl get pods -n lear-demo
```

### `scripts/demo/scripts/teardown.sh`
Clean everything:
```bash
#!/bin/bash
kubectl delete namespace lear-demo --ignore-not-found
echo "🗑️ Demo namespace deleted"
```

---

## Verification

For each failure:
- [x] Inject script runs without error (`inject-configmap-break.ps1` tested on AWS EKS)
- [x] Prash watcher detects the problem within 30 seconds (pod logs show connection error, status reaches CrashLoopBackOff in 21s)
- [x] `prash fix` produces correct diagnosis (`DATABASE_HOST` mismatch evidenced in logs)
- [x] Fix executes and pod recovers (readiness probe passes, 1/1 Running)
- [x] Reset script restores health (`reset-configmap.ps1` restored pod in 7s)
- [x] Can re-inject the same failure (for episodic memory demo)

**Full cycle time:** Inject → detect → diagnose → fix → verify tested at **under 60 seconds**. Rehearsal passed.
