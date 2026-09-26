# lear.ps1 — One-click Lear launcher for PowerShell
# Usage: Right-click → Run with PowerShell, or: .\lear.ps1

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Lear — Infrastructure Intelligence"

Write-Host ""
Write-Host "  ██╗     ███████╗ █████╗ ██████╗ " -ForegroundColor Magenta
Write-Host "  ██║     ██╔════╝██╔══██╗██╔══██╗" -ForegroundColor Magenta
Write-Host "  ██║     █████╗  ███████║██████╔╝" -ForegroundColor Magenta
Write-Host "  ██║     ██╔══╝  ██╔══██║██╔══██╗" -ForegroundColor Magenta
Write-Host "  ███████╗███████╗██║  ██║██║  ██║" -ForegroundColor Magenta
Write-Host "  ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Infrastructure Intelligence Engine" -ForegroundColor DarkGray
Write-Host ""

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# ── Preflight checks ──
function Test-Command($cmd) { $null -ne (Get-Command $cmd -ErrorAction SilentlyContinue) }

if (-not (Test-Command "python")) {
    Write-Host "[ERROR] Python not found. Install Python 3.10+ and try again." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
if (-not (Test-Command "node")) {
    Write-Host "[ERROR] Node.js not found. Install Node.js 18+ and try again." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# ── First-run setup ──
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Write-Host "[SETUP] No .env found. Copying .env.example..." -ForegroundColor Yellow
        Copy-Item ".env.example" ".env"
    }
}

if (-not (Test-Path ".venv")) {
    Write-Host "[SETUP] Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

Write-Host "[SETUP] Activating virtual environment..." -ForegroundColor Cyan
& .\.venv\Scripts\Activate.ps1

Write-Host "[SETUP] Installing Python dependencies (this may take a moment on first run)..." -ForegroundColor Cyan
pip install -e ".[dev]" -q 2>$null

if (-not (Test-Path "desktop\node_modules")) {
    Write-Host "[SETUP] Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location desktop
    npm install --silent 2>$null
    Pop-Location
}

# ── Kill existing processes on our ports ──
Write-Host "[CLEANUP] Checking for port conflicts..." -ForegroundColor DarkGray
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}
Get-NetTCPConnection -LocalPort 1420 -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "══════════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host "  Starting Lear..." -ForegroundColor White
Write-Host "══════════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host ""

# ── Start backend ──
Write-Host "[BACKEND]  Starting API server on http://127.0.0.1:8000 ..." -ForegroundColor Green
$backendJob = Start-Process -NoNewWindow -PassThru -FilePath "cmd.exe" -ArgumentList "/c", "call .venv\Scripts\activate.bat && python -m uvicorn prash.server:app --host 127.0.0.1 --port 8000 --log-level warning" -WindowStyle Hidden

# Wait for backend
Write-Host "[BACKEND]  Waiting for API server..." -ForegroundColor DarkGray
$ready = $false
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/system/version" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {}
    Write-Host "." -NoNewline -ForegroundColor DarkGray
}
Write-Host ""
if ($ready) {
    Write-Host "[BACKEND]  API server is ready!" -ForegroundColor Green
} else {
    Write-Host "[WARNING]  Backend may still be starting..." -ForegroundColor Yellow
}

# ── Start frontend ──
Write-Host "[FRONTEND] Starting desktop UI on http://localhost:1420 ..." -ForegroundColor Green
$frontendJob = Start-Process -NoNewWindow -PassThru -FilePath "cmd.exe" -ArgumentList "/c", "cd /d `"$root\desktop`" && npm run dev" -WindowStyle Hidden

# Wait for frontend
Write-Host "[FRONTEND] Waiting for UI..." -ForegroundColor DarkGray
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:1420" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {}
    Write-Host "." -NoNewline -ForegroundColor DarkGray
}
Write-Host ""
if ($ready) {
    Write-Host "[FRONTEND] UI is ready!" -ForegroundColor Green
} else {
    Write-Host "[FRONTEND] Still warming up, opening anyway..." -ForegroundColor Yellow
}

# ── Open browser ──
Write-Host ""
Write-Host "══════════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "  Lear is running!" -ForegroundColor White
Write-Host ""
Write-Host "  Dashboard:  " -NoNewline -ForegroundColor Gray; Write-Host "http://localhost:1420" -ForegroundColor Magenta
Write-Host "  API Docs:   " -NoNewline -ForegroundColor Gray; Write-Host "http://127.0.0.1:8000/docs" -ForegroundColor Magenta
Write-Host "  API Server: " -NoNewline -ForegroundColor Gray; Write-Host "http://127.0.0.1:8000" -ForegroundColor Magenta
Write-Host ""
Write-Host "══════════════════════════════════════════════" -ForegroundColor DarkCyan
Write-Host ""

Start-Process "http://localhost:1420"

Write-Host "Press Ctrl+C to stop all services." -ForegroundColor DarkGray
Write-Host ""

# ── Cleanup on exit ──
try {
    while ($true) {
        Start-Sleep -Seconds 5
        # Check if backend died
        if ($backendJob.HasExited) {
            Write-Host "[WARNING] Backend stopped. Restarting..." -ForegroundColor Yellow
            $backendJob = Start-Process -NoNewWindow -PassThru -FilePath "cmd.exe" -ArgumentList "/c", "call .venv\Scripts\activate.bat && python -m uvicorn prash.server:app --host 127.0.0.1 --port 8000 --log-level warning" -WindowStyle Hidden
        }
    }
} finally {
    Write-Host ""
    Write-Host "[SHUTDOWN] Stopping Lear services..." -ForegroundColor Yellow
    if (-not $backendJob.HasExited) { Stop-Process -Id $backendJob.Id -Force -ErrorAction SilentlyContinue }
    if (-not $frontendJob.HasExited) { Stop-Process -Id $frontendJob.Id -Force -ErrorAction SilentlyContinue }
    # Also kill any orphaned processes
    Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Get-NetTCPConnection -LocalPort 1420 -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[SHUTDOWN] Done. Goodbye!" -ForegroundColor Green
}
