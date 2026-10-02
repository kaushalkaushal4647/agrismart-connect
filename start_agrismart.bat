@echo off
TITLE AgriSmart Connect — Auto Launcher
COLOR 0A
mode con cols=70 lines=35

:: ── Make sure we run from project root ─────────────────────────────────
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════════════════════════════════╗
echo  ║         AgriSmart Connect  —  Smart Farm-to-Market Platform     ║
echo  ║         Starting all services... Please wait.                   ║
echo  ╚══════════════════════════════════════════════════════════════════╝
echo.

:: ── Give Windows time to finish booting (helpful on auto-start) ────────
:: Skip the wait if user ran the script manually (boot wait env var not set)
if defined AGRISMART_BOOT_WAIT (
    echo  [BOOT] Waiting 15s for Windows services to settle...
    timeout /t 15 /nobreak >nul
)

:: ═══════════════════════════════════════════════════════════════════════
::  STEP 1 — Start PostgreSQL (tries versions 15-18)
:: ═══════════════════════════════════════════════════════════════════════
echo  [1/5] Checking PostgreSQL database service...

set PG_RUNNING=0
for %%V in (18 17 16 15 14) do (
    sc query postgresql-x64-%%V | find "RUNNING" >nul 2>&1
    if !ERRORLEVEL! EQU 0 set PG_RUNNING=1
)

setlocal enabledelayedexpansion
set PG_RUNNING=0
for %%V in (18 17 16 15 14) do (
    sc query postgresql-x64-%%V 2>nul | find "RUNNING" >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set PG_RUNNING=1
        echo       [OK] PostgreSQL %%V is already running.
    )
)

if !PG_RUNNING! EQU 0 (
    echo       PostgreSQL not running — attempting to start...
    for %%V in (18 17 16 15 14) do (
        net start postgresql-x64-%%V >nul 2>&1
    )
    timeout /t 5 /nobreak >nul
    echo       [OK] PostgreSQL start attempted.
)

:: ═══════════════════════════════════════════════════════════════════════
::  STEP 2 — Start Ollama AI Service
:: ═══════════════════════════════════════════════════════════════════════
echo  [2/5] Checking Ollama AI service (llava:7b-v1.6)...

curl -s --max-time 3 http://localhost:11434/api/tags >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo       Starting Ollama background server...
    start "Ollama AI" /min ollama serve
    :: Wait up to 12 seconds for Ollama to come up
    set OLLAMA_READY=0
    for /L %%i in (1,1,6) do (
        timeout /t 2 /nobreak >nul
        curl -s --max-time 2 http://localhost:11434/api/tags >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            set OLLAMA_READY=1
            goto :ollama_done
        )
    )
    :ollama_done
    if !OLLAMA_READY! EQU 1 (
        echo       [OK] Ollama is now online.
    ) else (
        echo       [WARN] Ollama did not respond — AI features may be unavailable.
    )
) else (
    echo       [OK] Ollama already online.
)

:: ═══════════════════════════════════════════════════════════════════════
::  STEP 3 — Validate Razorpay config in .env
:: ═══════════════════════════════════════════════════════════════════════
echo  [3/5] Checking Razorpay payment configuration...

findstr /C:"rzp_test_REPLACE" .env >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo.
    echo   ┌─────────────────────────────────────────────────────────────┐
    echo   │ WARNING: Razorpay keys are still placeholders in .env!     │
    echo   │ Payments will not work until you add real test API keys.   │
    echo   │ Get keys: https://dashboard.razorpay.com/app/keys          │
    echo   └─────────────────────────────────────────────────────────────┘
    echo.
    timeout /t 4 /nobreak >nul
) else (
    echo       [OK] Razorpay credentials configured.
)

:: ═══════════════════════════════════════════════════════════════════════
::  STEP 4 — Database schema + migrations
:: ═══════════════════════════════════════════════════════════════════════
echo  [4/5] Applying database migrations...

python backend/seed_data.py             >nul 2>&1
python run_payment_migration.py         >nul 2>&1
python run_logistics_migration.py       >nul 2>&1
python run_delivery_payouts_migration.py >nul 2>&1

echo       [OK] All migrations applied.

:: ═══════════════════════════════════════════════════════════════════════
::  STEP 5 — Start Flask backend
:: ═══════════════════════════════════════════════════════════════════════
echo  [5/5] Starting AgriSmart Connect Web Server...
echo.
echo  ╔══════════════════════════════════════════════════════════════════╗
echo  ║   AgriSmart Connect is RUNNING  —  http://localhost:5000       ║
echo  ╠══════════════════════════════════════════════════════════════════╣
echo  ║  Portal Links                                                   ║
echo  ║  ─────────────────────────────────────────────────────────────  ║
echo  ║  Home         →  http://localhost:5000                          ║
echo  ║  Consumer     →  http://localhost:5000/consumer.html           ║
echo  ║  Farmer       →  http://localhost:5000/farmer.html             ║
echo  ║  Retailer     →  http://localhost:5000/retailer.html           ║
echo  ║  Restaurant   →  http://localhost:5000/restaurant.html         ║
echo  ║  AI Doctor    →  http://localhost:5000/ai.html                 ║
echo  ║  IoT Hub      →  http://localhost:5000/iot.html                ║
echo  ║  Admin        →  http://localhost:5000/admin.html              ║
echo  ║  Orders       →  http://localhost:5000/orders.html             ║
echo  ║  Delivery     →  http://localhost:5000/delivery.html           ║
echo  ╠══════════════════════════════════════════════════════════════════╣
echo  ║  Keep this window open while using AgriSmart.                  ║
echo  ║  Press CTRL+C to shut down the server.                         ║
echo  ╚══════════════════════════════════════════════════════════════════╝
echo.

:: Open browser to home page (2 second delay to let Flask bind)
start "" /b timeout /t 2 /nobreak >nul
start "" "http://localhost:5000"

:: Run Flask (foreground — logs visible here)
python backend/app.py

echo.
echo  AgriSmart has shut down. Press any key to close this window.
pause >nul
