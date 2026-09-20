# Demo Load Generator — Simulated Traffic

**Owner:** Anant  
**Time to complete:** ~30 min  

---

## Goal

Simulated traffic hitting the frontend → checkout-api → payment/shipping → postgres chain. The MD sees "500 users hitting checkout right now" on the dashboard and Datadog.

---

## Tasks

### T1. Choose load generator tool

**Option A: `hey` (HTTP load generator, single binary)**
```bash
# Install
go install github.com/rakyll/hey@latest
# Or download binary from GitHub releases

# Run — 200 concurrent, runs for 600 seconds (duration of demo)
hey -z 600s -c 200 http://<frontend-svc>/api/healthz
```

**Option B: `k6` (deployed as K8s Job inside the cluster)**
```yaml
# k6 runs inside the cluster, no external dependency
apiVersion: batch/v1
kind: Job
metadata:
  name: loadgen
  namespace: lear-demo
spec:
  template:
    spec:
      containers:
        - name: k6
          image: grafana/k6:latest
          args: ["run", "-"]
          stdin: true
          # k6 script injected via ConfigMap
      restartPolicy: Never
```

**Option C: Simple `ab` (Apache Bench, already on most systems)**
```bash
# 200 concurrent, 100000 requests
ab -n 100000 -c 200 http://<frontend-svc>/api/healthz
```

**Recommendation:** Use `hey` or `ab` from your laptop (simplest). If you want it visible on the K8s dashboard as a pod, use a K8s Job with `busybox` running `wget` in a loop.

### T2. K8s-native loadgen pod (looks impressive on dashboard)

```yaml
# scripts/demo/manifests/loadgen.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: loadgen
  namespace: lear-demo
  labels:
    app: loadgen
    team: lear-demo
spec:
  replicas: 1
  selector:
    matchLabels: { app: loadgen }
  template:
    metadata:
      labels: { app: loadgen }
    spec:
      containers:
        - name: loadgen
          image: busybox:1.36
          command:
            - /bin/sh
            - -c
            - |
              while true; do
                wget -q -O /dev/null http://checkout-api/healthz 2>/dev/null &
                wget -q -O /dev/null http://checkout-api/healthz 2>/dev/null &
                wget -q -O /dev/null http://checkout-api/healthz 2>/dev/null &
                wget -q -O /dev/null http://checkout-api/healthz 2>/dev/null &
                wget -q -O /dev/null http://checkout-api/healthz 2>/dev/null &
                sleep 0.1
              done
          resources:
            requests: { memory: "32Mi", cpu: "50m" }
            limits: { memory: "64Mi", cpu: "100m" }
```

- [ ] Loadgen pod deployed and running
- [ ] `kubectl logs -f loadgen-xxx -n lear-demo` shows continuous requests
- [ ] Dashboard shows request rate climbing
- [ ] Datadog shows HTTP metrics from the cluster

### T3. Verify traffic is visible

- [ ] Prash dashboard shows request rate widget for `checkout-api`
- [ ] Datadog container metrics show CPU/memory activity on all pods
- [ ] `kubectl top pods -n lear-demo` shows non-zero CPU usage
- [ ] When `checkout-api` goes down, error rate visible in Datadog

---

## Talking Point

> "500 users are hitting checkout right now. This is a real e-commerce platform on a real AWS cluster. Prash is watching everything."

(The actual number doesn't matter — the loadgen just needs to make metrics look alive and non-zero. 50 req/s is enough to look busy.)
