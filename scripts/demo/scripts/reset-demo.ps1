# Hard reset script to restore demo microservices to a clean, 100% green state
$NS = "lear-demo"

Write-Host "Resetting demo environment to healthy state..." -ForegroundColor Cyan

# 1. Restore ConfigMap
kubectl -n $NS patch configmap checkout-api-config --type merge -p '{\"data\":{\"DATABASE_HOST\":\"postgres\"}}'

# 2. Restore Resource Limits
kubectl -n $NS patch deployment checkout-api --type merge -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"checkout-api\",\"resources\":{\"requests\":{\"cpu\":\"100m\",\"memory\":\"64Mi\"},\"limits\":{\"cpu\":\"200m\",\"memory\":\"128Mi\"}}}]}}}}'

# 3. Rollout restart
kubectl -n $NS rollout restart deployment/checkout-api
kubectl -n $NS rollout status deployment/checkout-api --timeout=90s

Write-Host "`nEnvironment restored successfully!" -ForegroundColor Green
kubectl -n $NS get pods
