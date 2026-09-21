#!/usr/bin/env bash
set -euo pipefail

NS="lear-demo"
TYPE="${1:-config}"

if [ "$TYPE" = "config" ]; then
  echo "Injecting failure: setting DATABASE_HOST=postgres-wrong"
  kubectl -n "$NS" patch configmap checkout-api-config --type merge -p '{"data":{"DATABASE_HOST":"postgres-wrong"}}'
  kubectl -n "$NS" rollout restart deployment/checkout-api
  echo "checkout-api restarted, entering CrashLoopBackOff"
elif [ "$TYPE" = "oom" ]; then
  echo "Injecting failure: memory limit throttled to 8Mi (OOMKilled)"
  kubectl -n "$NS" patch deployment checkout-api --type merge -p '{"spec":{"template":{"spec":{"containers":[{"name":"checkout-api","resources":{"limits":{"memory":"8Mi"}}}]}}}}'
  echo "checkout-api restarted, will trigger OOMKilled"
else
  echo "Unknown failure type: $TYPE. Supported: config, oom"
fi
