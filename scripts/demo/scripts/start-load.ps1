# Start or scale up simulated user load in EKS
$NS = "lear-demo"
$manifest = Join-Path (Split-Path $PSScriptRoot -Parent) "manifests\loadgen.yaml"

Write-Host "Starting simulated load generator in namespace '$NS'..." -ForegroundColor Cyan
kubectl apply -f $manifest
kubectl -n $NS scale deployment loadgen --replicas=1
kubectl -n $NS rollout status deployment/loadgen --timeout=60s

Write-Host "`nLoad generator is active! Streaming real-time traffic logs (Ctrl+C to exit log view):" -ForegroundColor Green
kubectl -n $NS logs -f -l app=loadgen
