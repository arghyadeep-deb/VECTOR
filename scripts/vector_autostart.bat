@echo off
REM VECTOR autostart launcher — run by the Windows Scheduled Task at logon.
REM Guards against double-launch: exits if a run_vector.py loop is already running.
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

REM Skip if VECTOR is already running (avoid duplicate instances).
wmic process where "name='python.exe'" get commandline 2>nul | findstr /C:"run_vector.py" >nul
if %errorlevel%==0 (
  echo VECTOR already running - skipping autostart.
  exit /b 0
)

REM Launch the autonomous loop, log to file (rotated by date).
set LOGDIR=%USERPROFILE%\.vector_ca\logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
python run_vector.py loop >> "%LOGDIR%\vector_%DATE:/=-%.log" 2>&1
