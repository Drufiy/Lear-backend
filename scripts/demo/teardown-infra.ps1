# Automation script to teardown the EKS demo cluster and avoid ongoing AWS charges
param (
    [switch]$Force
)

Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "Teardown EKS cluster 'lear-demo' in ap-south-1..." -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Yellow

if (-not $Force) {
    $confirm = Read-Host "Are you sure you want to delete the 'lear-demo' cluster in ap-south-1? (y/N)"
    if ($confirm -ne 'y' -and $confirm -ne 'Y') {
        Write-Host "Aborted." -ForegroundColor Red
        exit 0
    }
}

Write-Host "Deleting cluster via eksctl..." -ForegroundColor Yellow
eksctl delete cluster --name lear-demo --region ap-south-1 --wait

Write-Host "Cluster teardown complete! No ongoing charges." -ForegroundColor Green
