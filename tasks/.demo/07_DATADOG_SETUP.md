# Demo Datadog Setup — Container Monitoring + Correlation

**Owner:** Anant  
**Time to complete:** ~45 min  
**Prerequisites:** Datadog account (credentials confirmed), EKS cluster running  

---

## Goal

Datadog container monitoring agent on EKS + a synthetic monitor watching `checkout-api`. When `checkout-api` goes down, BOTH K8s watcher AND Datadog fire — and Prash correlates them into one incident.

---

## Tasks

### T1. Deploy Datadog Agent to EKS via Helm

```bash
# Add Datadog Helm repo
helm repo add datadog https://helm.datadoghq.com
helm repo update

# Create a K8s secret with your API key
kubectl create secret generic datadog-secret \
  -n lear-demo \
  --from-literal=api-key=$DATADOG_API_KEY

# Install the agent
helm install datadog-agent datadog/datadog \
  -n lear-demo \
  --set datadog.apiKey=$DATADOG_API_KEY \
  --set datadog.appKey=$DATADOG_APP_KEY \
  --set datadog.site=datadoghq.com \
  --set datadog.logs.enabled=true \
  --set datadog.logs.containerCollectAll=true \
  --set datadog.apm.enabled=false \
  --set datadog.processAgent.enabled=true \
  --set datadog.containerExclude="name:datadog-agent" \
  --set agents.image.tag=7-jmx
```

- [x] Datadog agent DaemonSet running: `kubectl get ds -n lear-demo`
- [x] Containers visible in Datadog UI: Infrastructure → Containers
- [x] Metrics flowing: `kubernetes.cpu.usage`, `kubernetes.memory.usage`

### T2. Create Datadog Synthetic Monitor

You need a monitor that watches `checkout-api`'s health and fires when it goes down. Options:

**Option A: HTTP check monitor (via API)**
```python
# Use existing break_datadog.py or create via API:
import requests

headers = {
    "DD-API-KEY": os.environ["DATADOG_API_KEY"],
    "DD-APPLICATION-KEY": os.environ["DATADOG_APP_KEY"],
}

# Create a monitor that checks a metric from checkout-api
monitor = {
    "name": "Lear Demo: checkout-api health",
    "type": "metric alert",
    "query": 'avg(last_1m):avg:kubernetes.containers.running{kube_deployment:checkout-api,kube_namespace:lear-demo} < 1',
    "message": "checkout-api is down in lear-demo namespace",
    "tags": ["team:lear-demo", "env:staging"],
    "options": {
        "thresholds": {"critical": 1},
        "notify_no_data": True,
        "no_data_timeframe": 2,
    },
}

resp = requests.post(
    "https://api.datadoghq.com/api/v1/monitor",
    headers=headers,
    json=monitor,
)
print(f"Monitor created: {resp.json().get('id')}")
```

**Option B: Use existing `break_datadog.py`**
- The `break_datadog.py` script already creates/manages a synthetic monitor
- Run it once to set up, then it fires automatically when checkout-api goes down

- [x] Monitor created in Datadog
- [x] Monitor is GREEN when checkout-api is healthy
- [x] Monitor fires RED when checkout-api pods go down
- [x] `break_combined.py` can read both K8s events + Datadog events

### T3. Set environment variables

Ensure these are in your `.env` (or exported in shell):
```bash
DATADOG_API_KEY=<your-key>    # Already confirmed
DATADOG_APP_KEY=<your-key>    # Already confirmed
DATADOG_SITE=datadoghq.com    # Already confirmed
```

- [x] Prash can connect: `prash investigate --provider datadog`
- [x] Desktop Integrations shows Datadog connected (green)

### T4. Verify correlation pipeline

```bash
# 1. With everything healthy, verify baseline
python scripts/testing/break_combined.py --offline  # canned test first

# 2. Live test — inject ConfigMap break, wait for Datadog to fire
./scripts/demo/scripts/inject-configmap-break.sh
# Wait ~1-2 min for Datadog monitor to evaluate
python scripts/testing/break_combined.py --namespace lear-demo --pod checkout-api-xxx

# 3. Verify: should show "1 correlated incident from 2 sources (kubernetes + datadog)"
```

- [x] `break_combined.py` correlates K8s + Datadog events
- [x] Single incident, not two separate alerts
- [x] Prash diagnosis includes evidence from both sources

### T5. Datadog Dashboard tab (for the demo)

Create a simple Datadog dashboard showing:
- Container CPU/memory for `lear-demo` namespace
- Monitor status (green/red)
- Log stream from `checkout-api`

This is optional — only open it during the demo if you want a visual "Datadog also sees the problem" moment.

- [x] Dashboard created in Datadog UI
- [x] Shows live container metrics
- [x] Shows monitor status

---

## Verification

- [x] `kubectl get pods -n lear-demo | grep datadog` — agent running
- [x] Datadog UI shows containers from lear-demo namespace
- [x] Monitor is GREEN with healthy services
- [x] Monitor fires RED when checkout-api goes down
- [x] Prash DatadogConnector reads the monitor status correctly
- [x] Correlation works: K8s + Datadog = one incident

---

## Teardown

```bash
# Remove Datadog agent from cluster
helm uninstall datadog-agent -n lear-demo

# Delete the monitor (optional — it costs nothing to keep)
# Use Datadog UI or API to delete
```

## Cost

- Datadog: Free trial or free tier (up to 5 hosts)
- The agent itself uses ~100-200MB RAM per node
- No ongoing cost if you delete the cluster after the demo
