#!/usr/bin/env bash
# Restores DATABASE_HOST to the healthy value and waits for recovery.
set -euo pipefail
NS=lear-demo

kubectl -n "$NS" patch configmap checkout-api-config --type merge -p '{"data":{"DATABASE_HOST":"postgres"}}'
kubectl -n "$NS" rollout restart deployment/checkout-api
kubectl -n "$NS" rollout status deployment/checkout-api --timeout=90s
kubectl -n "$NS" get pods
