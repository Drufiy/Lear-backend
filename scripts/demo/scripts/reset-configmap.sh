#!/bin/bash
kubectl patch configmap checkout-api-config -n lear-demo \
  --type merge -p '{"data":{"DATABASE_HOST":"postgres"}}'
kubectl rollout restart deployment/checkout-api -n lear-demo
echo "✅ Reset: DATABASE_HOST restored to 'postgres'"
