# Resets ConfigMap to healthy state
$ErrorActionPreference = "Stop"
$NS = "lear-demo"

Write-Host "[RESET] Restoring DATABASE_HOST to 'postgres' in ConfigMap checkout-api-config..." -ForegroundColor Cyan
kubectl -n $NS patch configmap checkout-api-config --type merge -p '{\"data\":{\"DATABASE_HOST\":\"postgres\"}}'
kubectl -n $NS rollout restart deployment/checkout-api
kubectl -n $NS rollout status deployment/checkout-api --timeout=60s
Write-Host "[OK] Reset: DATABASE_HOST restored to 'postgres'" -ForegroundColor Green
kubectl -n $NS get pods
