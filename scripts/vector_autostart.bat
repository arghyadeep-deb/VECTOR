@echo off
REM VECTOR autostart launcher — run by the Windows Startup shortcut at logon.
REM Runs the FULL brain + LAN-accessible API in ONE process, bound to 0.0.0.0 so
REM both the laptop and the daily phone can reach VECTOR over the home network.
REM Guards against double-launch: exits if VECTOR is already running.
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

REM Skip only if VECTOR is actually SERVING on port 8000 — matching on process
REM command line alone (the old check) false-positives on a stale/loop-only
REM process that never bound the port, permanently blocking every future
REM autostart. A LISTENING socket is the real signal that VECTOR is up.
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if not %errorlevel%==0 (
  echo VECTOR already running on port 8000 - skipping autostart.
  exit /b 0
)

set "LOGDIR=%USERPROFILE%\.vector_ca\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM VECTOR_API_RUN_LOOP=1 -> the api server also runs the full autonomous brain.
REM VECTOR_ENV=vector  -> hardened runtime mode (the former "production" mode) (also set in .env; belt+braces). The HUD is always
REM frontend\VECTOR.html; there is no separate "VECTOR Production" page any more (removed 2026-09-25).
set VECTOR_API_RUN_LOOP=1
set VECTOR_ENV=vector

REM ── Log rotation ────────────────────────────────────────────────────────
REM 2026-08-05: this log had no rotation and was found at 671 MB (last 3000
REM lines archived to vector_autostart.log.lasttail-20260805.txt before this
REM fix). Keep exactly one generation of history: once the live log exceeds
REM ~50MB, roll it to .log.1 (overwriting any previous .log.1) before this
REM run starts appending to a fresh file. Plain cmd, no PowerShell needed.
set "LOGFILE=%LOGDIR%\vector_autostart.log"
set LOGSIZE=0
if exist "%LOGFILE%" for %%A in ("%LOGFILE%") do set LOGSIZE=%%~zA
if %LOGSIZE% GTR 52428800 (
  if exist "%LOGFILE%.1" del /f /q "%LOGFILE%.1"
  ren "%LOGFILE%" "vector_autostart.log.1"
)

python run_vector.py api --host 0.0.0.0 --port 8000 >> "%LOGDIR%\vector_autostart.log" 2>&1
