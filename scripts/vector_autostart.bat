@echo off
REM VECTOR autostart launcher — run by the Windows Startup shortcut at logon.
REM Runs the FULL brain + LAN-accessible API in ONE process, bound to 0.0.0.0 so
REM both the laptop and the daily phone can reach VECTOR over the home network.
REM Guards against double-launch: exits if VECTOR is already running.
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

REM Skip if VECTOR is already running (avoid duplicate instances).
wmic process where "name='python.exe'" get commandline 2>nul | findstr /C:"run_vector.py" >nul
if %errorlevel%==0 (
  echo VECTOR already running - skipping autostart.
  exit /b 0
)

set LOGDIR=%USERPROFILE%\.vector_ca\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM VECTOR_API_RUN_LOOP=1 -> the api server also runs the full autonomous brain.
set VECTOR_API_RUN_LOOP=1
python run_vector.py api --host 0.0.0.0 --port 8000 >> "%LOGDIR%\vector_%DATE:/=-%.log" 2>&1
