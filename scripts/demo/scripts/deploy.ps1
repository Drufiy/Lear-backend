# Deploy all 5 demo microservices to the lear-demo namespace
$ErrorActionPreference = "Stop"

$NS = "lear-demo"
$manifestsDir = Join-Path (Split-Path $PSScriptRoot -Parent) "manifests"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Deploying Demo Microservices to EKS ($NS)..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Ensure Namespace
Write-Host "`n1. Applying namespace..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $manifestsDir "namespace.yaml")

# 2. Deploy Postgres
Write-Host "`n2. Deploying Postgres..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $manifestsDir "postgres.yaml")

# 3. Deploy Payment Service
Write-Host "`n3. Deploying Payment Service..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $manifestsDir "payment-service.yaml")

# 4. Deploy Shipping Service
Write-Host "`n4. Deploying Shipping Service..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $manifestsDir "shipping-service.yaml")

# 5. Deploy Checkout API
Write-Host "`n5. Deploying Checkout API..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $manifestsDir "checkout-api.yaml")

# 6. Deploy Frontend (nginx)
Write-Host "`n6. Deploying Frontend..." -ForegroundColor Yellow
kubectl apply -f (Join-Path $manifestsDir "frontend.yaml")

# 7. Wait for Rollouts
Write-Host "`n7. Waiting for microservices to reach Ready status..." -ForegroundColor Green
kubectl -n $NS rollout status deployment/postgres --timeout=120s
kubectl -n $NS rollout status deployment/payment-service --timeout=120s
kubectl -n $NS rollout status deployment/shipping-service --timeout=120s
kubectl -n $NS rollout status deployment/checkout-api --timeout=120s
kubectl -n $NS rollout status deployment/frontend --timeout=120s

Write-Host "`nAll 5 microservices successfully deployed and running!" -ForegroundColor Green
kubectl -n $NS get pods -o wide
kubectl -n $NS get svc
