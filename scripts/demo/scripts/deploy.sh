#!/usr/bin/env bash
set -euo pipefail

NS="lear-demo"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFESTS="$DIR/manifests"

echo "=== Deploying Demo Microservices to EKS ($NS) ==="
kubectl apply -f "$MANIFESTS/namespace.yaml"
kubectl apply -f "$MANIFESTS/postgres.yaml"
kubectl apply -f "$MANIFESTS/payment-service.yaml"
kubectl apply -f "$MANIFESTS/shipping-service.yaml"
kubectl apply -f "$MANIFESTS/checkout-api.yaml"
kubectl apply -f "$MANIFESTS/frontend.yaml"

echo "Waiting for rollouts..."
kubectl -n "$NS" rollout status deployment/postgres --timeout=120s
kubectl -n "$NS" rollout status deployment/payment-service --timeout=120s
kubectl -n "$NS" rollout status deployment/shipping-service --timeout=120s
kubectl -n "$NS" rollout status deployment/checkout-api --timeout=120s
kubectl -n "$NS" rollout status deployment/frontend --timeout=120s

echo "All services running:"
kubectl -n "$NS" get pods -o wide
