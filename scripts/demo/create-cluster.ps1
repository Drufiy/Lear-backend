# Automation script to create the EKS demo cluster
$ErrorActionPreference = "Stop"

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Creating EKS cluster 'lear-demo' in ap-south-1..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$clusterYaml = Join-Path $PSScriptRoot "cluster.yaml"
if (-not (Test-Path $clusterYaml)) {
    throw "cluster.yaml not found at $clusterYaml"
}

# Run eksctl create cluster
eksctl create cluster -f $clusterYaml

Write-Host "`nVerifying cluster nodes..." -ForegroundColor Green
kubectl get nodes -o wide

Write-Host "`nEnsuring demo namespace..." -ForegroundColor Green
$nsYaml = Join-Path $PSScriptRoot "manifests\namespace.yaml"
kubectl apply -f $nsYaml

Write-Host "`nNamespace status:" -ForegroundColor Green
kubectl get ns lear-demo

Write-Host "`nEKS cluster provisioned and ready for Lear demo!" -ForegroundColor Green
