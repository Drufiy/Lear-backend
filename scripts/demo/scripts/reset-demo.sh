#!/usr/bin/env bash
set -euo pipefail

NS="lear-demo"

echo "Resetting demo environment to healthy state..."
kubectl -n "$NS" patch configmap checkout-api-config --type merge -p '{"data":{"DATABASE_HOST":"postgres"}}'
kubectl -n "$NS" patch deployment checkout-api --type merge -p '{"spec":{"template":{"spec":{"containers":[{"name":"checkout-api","resources":{"requests":{"cpu":"100m","memory":"64Mi"},"limits":{"cpu":"200m","memory":"128Mi"}}}]}}}}'
kubectl -n "$NS" rollout restart deployment/checkout-api
kubectl -n "$NS" rollout status deployment/checkout-api --timeout=90s
kubectl -n "$NS" get pods
