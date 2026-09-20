#!/usr/bin/env bash
set -euo pipefail

NS="lear-demo"
echo "Pausing load generator in namespace '$NS'..."
kubectl -n "$NS" scale deployment loadgen --replicas=0
echo "Load generator paused."
