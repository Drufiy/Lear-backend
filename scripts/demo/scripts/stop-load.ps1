# Stop / scale down simulated user load in EKS
$NS = "lear-demo"

Write-Host "Pausing load generator in namespace '$NS'..." -ForegroundColor Yellow
kubectl -n $NS scale deployment loadgen --replicas=0
Write-Host "Load generator paused." -ForegroundColor Green
