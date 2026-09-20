#!/usr/bin/env bash
set -euo pipefail

NS="lear-demo"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting simulated load generator in namespace '$NS'..."
kubectl apply -f "$DIR/manifests/loadgen.yaml"
kubectl -n "$NS" scale deployment loadgen --replicas=1
kubectl -n "$NS" rollout status deployment/loadgen --timeout=60s

echo "Load generator active! Streaming logs (Ctrl+C to stop viewing):"
kubectl -n "$NS" logs -f -l app=loadgen
