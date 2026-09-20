# Injects ConfigMap break for live demo
$ErrorActionPreference = "Stop"
$NS = "lear-demo"

Write-Host "[INJECT] Setting DATABASE_HOST to 'postgres-wrong' in ConfigMap checkout-api-config..." -ForegroundColor Red
kubectl -n $NS patch configmap checkout-api-config --type merge -p '{\"data\":{\"DATABASE_HOST\":\"postgres-wrong\"}}'
kubectl -n $NS rollout restart deployment/checkout-api
Write-Host "[OK] Failure injected: checkout-api will CrashLoopBackOff (DATABASE_HOST -> postgres-wrong)" -ForegroundColor Red
Write-Host "Watch pods: kubectl get pods -n $NS -w" -ForegroundColor Yellow
