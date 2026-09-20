# Injects simulated failure for live demo (Scenario A: Database misconfiguration causing CrashLoopBackOff)
param (
    [string]$Type = "config"
)

$NS = "lear-demo"

if ($Type -eq "config") {
    Write-Host "Injecting failure: Setting DATABASE_HOST to 'postgres-wrong'..." -ForegroundColor Red
    kubectl -n $NS patch configmap checkout-api-config --type merge -p '{\"data\":{\"DATABASE_HOST\":\"postgres-wrong\"}}'
    kubectl -n $NS rollout restart deployment/checkout-api
    Write-Host "Injected! checkout-api will now enter CrashLoopBackOff." -ForegroundColor Red
    Write-Host "Run: kubectl get pods -n $NS -w" -ForegroundColor Yellow
} elseif ($Type -eq "oom") {
    Write-Host "Injecting failure: Memory limit throttle to 8Mi (OOMKilled)..." -ForegroundColor Red
    kubectl -n $NS patch deployment checkout-api --type merge -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"checkout-api\",\"resources\":{\"limits\":{\"memory\":\"8Mi\"}}}]}}}}'
    Write-Host "Injected! checkout-api will now trigger OOMKilled." -ForegroundColor Red
} else {
    Write-Host "Unknown failure type: $Type. Supported: config, oom" -ForegroundColor Yellow
}
