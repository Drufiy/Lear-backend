# Demo Infrastructure — EKS Cluster + Kind Fallback

**Owner:** Anant  
**Time to complete:** ~30 min (EKS) or ~5 min (Kind)  
**Cost:** ~$3-5 for the demo day (EKS)  

---

## Primary: AWS EKS

### T1. Create EKS cluster

```bash
# Install eksctl if not present
# choco install eksctl  (Windows)
# brew install eksctl   (macOS)

# Create a minimal cluster — 2 nodes, cheap instance type
eksctl create cluster \
  --name lear-demo \
  --region us-east-1 \
  --nodegroup-name demo-nodes \
  --node-type t3.medium \
  --nodes 2 \
  --nodes-min 2 \
  --nodes-max 2 \
  --managed
```

- [ ] Cluster created (~15-20 min for EKS provisioning)
- [ ] `kubectl get nodes` shows 2 Ready nodes
- [ ] kubeconfig set: `aws eks update-kubeconfig --name lear-demo --region us-east-1`

### T2. Create demo namespace

```bash
kubectl create namespace lear-demo
```

- [ ] `kubectl get ns lear-demo` returns Active

### T3. Set KUBE_CONTEXT in `.env`

```bash
# Add to your .env (or export in shell)
KUBE_CONTEXT=arn:aws:eks:us-east-1:<ACCOUNT_ID>:cluster/lear-demo
KUBE_NAMESPACE=lear-demo
```

- [ ] `prash` can connect to the cluster: `prash investigate lear-demo/<any-pod>`

### T4. Deploy Datadog agent to EKS

See `07_DATADOG_SETUP.md` — the Datadog agent runs as a DaemonSet on EKS nodes.

---

## Fallback: Local Kind Cluster

If EKS has issues on demo day, switch to Kind in 60 seconds:

```bash
# Create Kind cluster
kind create cluster --name lear-demo

# Create namespace
kubectl create namespace lear-demo

# Apply the same manifests (all manifests are cloud-agnostic)
kubectl apply -f scripts/demo/manifests/ -n lear-demo

# Update .env
# KUBE_CONTEXT=kind-lear-demo
# KUBE_NAMESPACE=lear-demo
```

- [ ] Kind cluster tested with same manifests
- [ ] `prash fix` works against Kind cluster
- [ ] Desktop app connects to Kind cluster

---

## Teardown (after demo)

```bash
# EKS — delete to stop charges
eksctl delete cluster --name lear-demo --region us-east-1

# Kind — delete
kind delete cluster --name lear-demo
```

- [ ] Cluster deleted after demo (don't forget — $3/day adds up)

---

## Verification

- [ ] `kubectl get pods -n lear-demo` — all pods Running
- [ ] `kubectl get svc -n lear-demo` — services have ClusterIPs
- [ ] `prash watch` detects pods correctly
- [ ] Desktop dashboard shows connected K8s widgets
