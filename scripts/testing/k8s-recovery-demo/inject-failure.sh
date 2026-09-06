#!/usr/bin/env bash
# Breaks checkout-api by pointing DATABASE_HOST at a host that doesn't exist.
set -euo pipefail
NS=lear-demo

kubectl -n "$NS" patch configmap checkout-api-config --type merge -p '{"data":{"DATABASE_HOST":"postgres-wrong"}}'
kubectl -n "$NS" rollout restart deployment/checkout-api

echo "Failure injected: DATABASE_HOST=postgres-wrong"
echo "Watch it break with:"
echo "  kubectl get pods -n $NS -w"
