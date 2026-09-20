#!/bin/bash
kubectl patch configmap checkout-api-config -n lear-demo \
  --type merge -p '{"data":{"DATABASE_HOST":"postgres-wrong"}}'
kubectl rollout restart deployment/checkout-api -n lear-demo
echo "💥 Failure injected: checkout-api will CrashLoopBackOff (DATABASE_HOST → postgres-wrong)"
