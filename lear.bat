@echo off
title Lear — Infrastructure Intelligence
color 0A

echo.
echo   ██╗     ███████╗ █████╗ ██████╗
echo   ██║     ██╔════╝██╔══██╗██╔══██╗
echo   ██║     █████╗  ███████║██████╔╝
echo   ██║     ██╔══╝  ██╔══██║██╔══██╗
echo   ███████╗███████╗██║  ██║██║  ██║
echo   ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝
echo.
echo   Infrastructure Intelligence Engine
echo   ====================================
echo.

cd /d "%~dp0"

:: ── Check Python ──
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ and try again.
    pause
    exit /b 1
)

:: ── Check Node ──
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Install Node.js 18+ and try again.
    pause
    exit /b 1
)

:: ── Check if .env exists ──
if not exist ".env" (
    if exist ".env.example" (
        echo [SETUP] No .env found. Copying .env.example as .env...
        copy ".env.example" ".env" >nul
    )
)

:: ── Install Python deps if needed ──
if not exist ".venv" (
    echo [SETUP] Creating Python virtual environment...
    python -m venv .venv
)

echo [SETUP] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [SETUP] Installing Python dependencies...
pip install -e ".[dev]" -q 2>nul

:: ── Install Node deps if needed ──
if not exist "desktop\node_modules" (
    echo [SETUP] Installing frontend dependencies...
    cd desktop
    npm install --silent
    cd ..
)

:: ── Kill any existing processes on our ports ──
echo [CLEANUP] Checking for port conflicts...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000.*LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":1420.*LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo.
echo ══════════════════════════════════════════════
echo   Starting Lear...
echo ══════════════════════════════════════════════
echo.

:: ── Start the FastAPI backend (background) ──
echo [BACKEND]  Starting API server on http://127.0.0.1:8000 ...
start "Lear Backend" /min cmd /c "call .venv\Scripts\activate.bat && python -m uvicorn prash.server:app --host 127.0.0.1 --port 8000 --log-level warning"

:: ── Wait for backend to be ready ──
echo [BACKEND]  Waiting for API server to be ready...
set /a attempts=0
:wait_backend
set /a attempts+=1
if %attempts% gtr 30 (
    echo [ERROR] Backend failed to start after 30 seconds.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
curl -s -o nul -w "" http://127.0.0.1:8000/api/system/version >nul 2>&1
if %errorlevel% neq 0 (
    goto wait_backend
)
echo [BACKEND]  API server is ready!

:: ── Start the Vite frontend (background) ──
echo [FRONTEND] Starting desktop UI on http://localhost:1420 ...
start "Lear Frontend" /min cmd /c "cd /d "%~dp0desktop" && npm run dev"

:: ── Wait for frontend ──
echo [FRONTEND] Waiting for UI to be ready...
set /a attempts=0
:wait_frontend
set /a attempts+=1
if %attempts% gtr 30 (
    echo [WARNING] Frontend may still be starting. Opening browser anyway...
    goto open_browser
)
timeout /t 1 /nobreak >nul
curl -s -o nul -w "" http://localhost:1420 >nul 2>&1
if %errorlevel% neq 0 (
    goto wait_frontend
)
echo [FRONTEND] UI is ready!

:open_browser
echo.
echo ══════════════════════════════════════════════
echo   Lear is running!
echo.
echo   Dashboard:  http://localhost:1420
echo   API Docs:   http://127.0.0.1:8000/docs
echo   API Server: http://127.0.0.1:8000
echo.
echo   Press any key to open in your browser...
echo   Close this window to stop all services.
echo ══════════════════════════════════════════════
echo.

:: ── Open the browser ──
start "" http://localhost:1420

echo Lear is running. Press Ctrl+C or close this window to stop.
echo.

:: ── Keep this window alive and handle cleanup on exit ──
:keepalive
timeout /t 5 /nobreak >nul
:: Check if backend is still running
curl -s -o nul http://127.0.0.1:8000/api/system/version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Backend appears to have stopped. Restarting...
    start "Lear Backend" /min cmd /c "call "%~dp0.venv\Scripts\activate.bat" && python -m uvicorn prash.server:app --host 127.0.0.1 --port 8000 --log-level warning"
)
goto keepalive
