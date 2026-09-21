# Resets memory limits to normal
$ErrorActionPreference = "Stop"
$NS = "lear-demo"

Write-Host "[RESET] Restoring memory limits for checkout-api to 128Mi..." -ForegroundColor Cyan
kubectl set resources deployment/checkout-api -n $NS --limits=memory=128Mi --requests=memory=64Mi
kubectl -n $NS rollout restart deployment/checkout-api
kubectl -n $NS rollout status deployment/checkout-api --timeout=60s
Write-Host "[OK] Reset: memory limits restored to 128Mi" -ForegroundColor Green
kubectl -n $NS get pods
