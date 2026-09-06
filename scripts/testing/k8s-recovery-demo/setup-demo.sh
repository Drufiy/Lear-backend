#!/usr/bin/env bash
# Builds and deploys the checkout-api demo into the local `lear-demo` kind cluster.
set -euo pipefail
cd "$(dirname "$0")"

CLUSTER=lear-demo
NS=lear-demo

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  echo "Creating kind cluster '$CLUSTER'..."
  kind create cluster --name "$CLUSTER"
fi
kubectl config use-context "kind-$CLUSTER" >/dev/null

kubectl get namespace "$NS" >/dev/null 2>&1 || kubectl create namespace "$NS"

echo "Building checkout-api image..."
docker build -t checkout-api:demo ./app

echo "Loading image into kind cluster..."
kind load docker-image checkout-api:demo --name "$CLUSTER"

echo "Applying manifests..."
kubectl apply -f manifests/configmap.yaml
kubectl apply -f manifests/postgres.yaml
kubectl apply -f manifests/checkout-api.yaml

echo "Waiting for postgres..."
kubectl -n "$NS" rollout status deployment/postgres --timeout=90s

echo "Waiting for checkout-api..."
kubectl -n "$NS" rollout status deployment/checkout-api --timeout=90s

echo ""
echo "Demo environment ready. Try:"
echo "  kubectl get pods -n $NS"
