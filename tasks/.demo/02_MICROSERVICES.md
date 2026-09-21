# Demo Microservices — 5-Service E-Commerce Platform

**Owner:** Anant  
**Time to complete:** ~2 hours (build images + write manifests)  

---

## Architecture

```
          ┌──────────┐
          │ frontend  │ ← nginx, serves static HTML + proxies to checkout-api
          │ :80       │
          └─────┬─────┘
                │ /api/*
                ▼
          ┌──────────┐
          │ checkout  │ ← Python/Flask, main API (existing from k8s-recovery-demo)
          │ api :8080 │    - POST /checkout → validates cart, calls payment + shipping
          │           │    - GET /healthz → DB connectivity check
          └─────┬─────┘
           ┌────┴────┐
           ▼         ▼
     ┌──────────┐ ┌──────────┐
     │ payment  │ │ shipping │
     │ svc :3000│ │ svc :4000│ ← lightweight stubs, return success/failure
     └──────────┘ └──────────┘
                │
                ▼
          ┌──────────┐
          │ postgres  │ ← existing from k8s-recovery-demo
          │ :5432     │
          └──────────┘
```

**Design principle:** Services look real and complex on a dashboard, but are trivially simple internally. The demo's star is Prash, not the app.

---

## Tasks

### T1. `checkout-api` — existing, expand slightly
- [ ] Already exists in `scripts/testing/k8s-recovery-demo/app/`
- [ ] Add `/checkout` endpoint that calls `payment-service` and `shipping-service`
- [ ] Add `/metrics` endpoint returning request count, error rate, latency (for dashboard)
- [ ] Dockerfile: build with `docker build -t checkout-api:demo .`
- [ ] For EKS: push to ECR or use a public Docker Hub image

### T2. `payment-service` — new, lightweight
- [ ] Language: Node.js (simple Express server, <50 lines)
- [ ] `POST /charge` → returns `{"status": "ok", "tx_id": "..."}` after 100-300ms random delay
- [ ] `GET /healthz` → `{"healthy": true}`
- [ ] Dockerfile: `FROM node:20-alpine`, copies `server.js`, exposes 3000
- [ ] Purpose: shows multi-service architecture, can be broken for advanced demo

### T3. `shipping-service` — new, lightweight  
- [ ] Language: Python (Flask, <40 lines)
- [ ] `POST /calculate` → returns `{"cost": 5.99, "estimated_days": 3}` after 50-200ms delay
- [ ] `GET /healthz` → `{"healthy": true}`
- [ ] Dockerfile: `FROM python:3.12-slim`, installs Flask, copies `app.py`, exposes 4000
- [ ] Purpose: another service on the dashboard, different language = looks real

### T4. `frontend` — new, nginx reverse proxy
- [ ] nginx config proxying `/api/*` → `checkout-api:80`
- [ ] Serves a static HTML page with a simple "E-Commerce Demo" splash
- [ ] Purpose: entry point for load generator, makes architecture look complete
- [ ] Dockerfile: `FROM nginx:alpine`, copies `nginx.conf` + `index.html`

### T5. `postgres` — existing
- [ ] Already exists in `scripts/testing/k8s-recovery-demo/manifests/postgres.yaml`
- [ ] `POSTGRES_PASSWORD=demo` (throwaway, local cluster only)
- [ ] No changes needed

### T6. Write Kubernetes manifests

All manifests go in `scripts/demo/manifests/`:

```
scripts/demo/manifests/
  ├── namespace.yaml        # lear-demo namespace
  ├── postgres.yaml         # existing, copied from k8s-recovery-demo
  ├── configmap.yaml        # existing, checkout-api config (DATABASE_HOST, etc.)
  ├── checkout-api.yaml     # existing, expanded
  ├── payment-service.yaml  # new
  ├── shipping-service.yaml # new
  └── frontend.yaml         # new (nginx)
```

- [ ] Every Deployment has: readiness probe, liveness probe, resource limits
- [ ] Resource limits: `requests: 64Mi/100m`, `limits: 128Mi/200m` (realistic, not wasteful)
- [ ] Labels: `app: <name>`, `team: lear-demo`, `env: staging`
- [ ] Services: ClusterIP for internal, LoadBalancer for frontend (or NodePort for Kind)

### T7. Build and push container images

**For EKS (ECR):**
```bash
# Create ECR repos
aws ecr create-repository --repository-name lear-demo/checkout-api
aws ecr create-repository --repository-name lear-demo/payment-service
aws ecr create-repository --repository-name lear-demo/shipping-service
aws ecr create-repository --repository-name lear-demo/frontend

# Build and push
docker build -t <account>.dkr.ecr.us-east-1.amazonaws.com/lear-demo/checkout-api:demo scripts/demo/services/checkout-api/
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/lear-demo/checkout-api:demo
# ... repeat for each service
```

**For Kind (local):**
```bash
# Build locally, load into Kind
docker build -t checkout-api:demo scripts/demo/services/checkout-api/
kind load docker-image checkout-api:demo --name lear-demo
# ... repeat for each service
```

- [ ] All 4 images built successfully
- [ ] Pushed to ECR (or loaded into Kind)
- [ ] `kubectl apply -f scripts/demo/manifests/ -n lear-demo`
- [ ] All pods Running: `kubectl get pods -n lear-demo`

### T8. Source code location

```
scripts/demo/
  ├── manifests/            # K8s YAML
  ├── services/
  │   ├── checkout-api/     # Python/Flask + Dockerfile
  │   ├── payment-service/  # Node.js + Dockerfile
  │   ├── shipping-service/ # Python/Flask + Dockerfile
  │   └── frontend/         # nginx + Dockerfile + index.html
  └── scripts/
      ├── deploy.sh         # One-command deploy to EKS or Kind
      ├── inject-failure.sh # Break things
      └── reset-demo.sh     # Fix things
```

---

## Verification

- [ ] `kubectl get pods -n lear-demo` — 5 pods Running (checkout-api, payment, shipping, frontend, postgres)
- [ ] `kubectl get svc -n lear-demo` — all services have endpoints
- [ ] `curl http://<frontend-ip>/api/healthz` returns healthy
- [ ] Desktop dashboard shows all 5 services with live metrics
- [ ] Prash watcher detects all pods
