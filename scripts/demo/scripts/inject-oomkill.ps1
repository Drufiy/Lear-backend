# Injects OOMKill failure by restricting memory to 16Mi
$ErrorActionPreference = "Stop"
$NS = "lear-demo"

Write-Host "[INJECT] Throttling memory limits to 16Mi for checkout-api..." -ForegroundColor Red
kubectl set resources deployment/checkout-api -n $NS --limits=memory=16Mi
kubectl -n $NS rollout restart deployment/checkout-api
Write-Host "[OK] Failure injected: checkout-api will OOMKill under load" -ForegroundColor Red
