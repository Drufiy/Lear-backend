# Clear/reset episodic memory for a fresh unseeded run
$ErrorActionPreference = "Stop"

$memoryFile = Join-Path $PSScriptRoot "..\..\.prash\memory.json"
if (Test-Path $memoryFile) {
    Remove-Item -Path $memoryFile -Force
    Write-Host "[RESET] Episodic memory reset (.prash/memory.json removed)" -ForegroundColor Yellow
} else {
    Write-Host "[INFO] No episodic memory file found at $memoryFile" -ForegroundColor Cyan
}
