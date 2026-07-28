@echo off
REM VECTOR desktop launcher: ensure the brain+API is running, then open the HUD
REM fullscreen in app mode. Voice ("Hey Vector") is always listening while the
REM server runs; the HUD also exposes in-browser push-to-talk / duplex voice.
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

REM --- 1. Start VECTOR if it isn't already running -----------------------------
REM errorlevel := count of listeners on :8000 (0 = not running). Port-based, NOT
REM CommandLine-based: VECTOR now runs ELEVATED, and a normal-integrity process
REM cannot read an elevated process's CommandLine — that check always came back
REM "not running" and re-triggered the task every time (2026-07-17).
powershell -NoProfile -Command "exit @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).Count"
if %errorlevel%==0 (
  echo Starting VECTOR...
  REM Prefer the ELEVATED scheduled task (admin + desktop session + single-
  REM instance via MultipleInstances=IgnoreNew). Register it once with:
  REM   scripts\install_vector_admin.ps1  (as Administrator)
  REM Falls back to a plain non-elevated launch if the task isn't registered.
  schtasks /query /tn VECTOR >nul 2>&1
  if not errorlevel 1 (
    schtasks /run /tn VECTOR >nul 2>&1
  ) else (
    powershell -NoProfile -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','\"%CD%\scripts\vector_autostart.bat\"' -WindowStyle Hidden"
  )
  REM wait up to ~80s for /health to answer 200
  powershell -NoProfile -Command "for($i=0;$i -lt 40;$i++){ try{ if((Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200){exit 0} }catch{}; Start-Sleep 2 }; exit 1"
)

REM --- 2. Read the API key from .env (grants HUD asset access + sets cookie) ----
REM regex match (no pipes -> avoids for/f caret-escaping pitfalls)
for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command "[regex]::Match((Get-Content '.env' -Raw),'VECTOR_API_KEY=(\S+)').Groups[1].Value"`) do set "VKEY=%%K"
set "URL=http://127.0.0.1:8000/hud/?key=%VKEY%"

REM --- 3. ONE HUD ONLY: focus an existing window, otherwise open one -----------
REM One system = one HUD. Clicking the icon used to stack a new chrome --app
REM window every time (2026-07-17 owner report).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0vector_focus_hud.ps1" -Deliberate >nul 2>&1
if not errorlevel 1 (
  echo HUD already open - focused it.
  exit /b 0
)

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "EDGE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if exist "%CHROME%" (
  start "" "%CHROME%" --app=%URL% --start-fullscreen
) else (
  start "" "%EDGE%" --app=%URL% --start-fullscreen
)
exit /b 0
