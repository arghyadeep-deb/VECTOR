@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\force_restart.log"
echo ==== force restart %DATE% %TIME% ==== > "%LOG%"

echo --- netstat before (raw) --- >> "%LOG%"
netstat -ano | findstr :8000 >> "%LOG%" 2>&1

echo --- kill pass 1 --- >> "%LOG%"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
  echo killing PID %%a >> "%LOG%"
  taskkill /f /pid %%a >> "%LOG%" 2>&1
)
timeout /t 3 /nobreak >nul

echo --- netstat after pass 1 --- >> "%LOG%"
netstat -ano | findstr :8000 >> "%LOG%" 2>&1

echo --- kill pass 2 (in case of race/respawn) --- >> "%LOG%"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
  echo killing PID %%a >> "%LOG%"
  taskkill /f /pid %%a >> "%LOG%" 2>&1
)
timeout /t 3 /nobreak >nul

echo --- netstat after pass 2 --- >> "%LOG%"
netstat -ano | findstr :8000 >> "%LOG%" 2>&1

echo --- also killing any stray python.exe running run_vector.py (belt+suspenders) --- >> "%LOG%"
wmic process where "name='python.exe' and commandline like '%%run_vector.py%%'" get processid,commandline >> "%LOG%" 2>&1

echo --- final pre-start netstat check --- >> "%LOG%"
netstat -ano | findstr :8000 >> "%LOG%" 2>&1
echo READY_TO_START >> "%LOG%"

cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python run_vector.py api --host 0.0.0.0
pause
