@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\watchdog_functional_test.log"
echo ==== watchdog functional test %DATE% %TIME% ==== > "%LOG%"
echo [1/3] killing whatever is on port 8000 to simulate a dead/hung backend... >> "%LOG%"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >> "%LOG%" 2>&1
timeout /t 3 /nobreak >nul
echo [2/3] confirming port 8000 is now down... >> "%LOG%"
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { 'STILL UP' } else { 'CONFIRMED DOWN' }" >> "%LOG%" 2>&1
echo [3/3] running WATCHDOG_CHECK.bat (this is what the scheduled task runs every 5 min)... >> "%LOG%"
call "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\WATCHDOG_CHECK.bat"
echo watchdog invocation done, sleeping 35s for restart to boot... >> "%LOG%"
timeout /t 35 /nobreak >nul
echo checking health now... >> "%LOG%"
powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 8 | ConvertTo-Json } catch { Write-Output \"ERROR: $_\" }" >> "%LOG%" 2>&1
echo DONE_MARKER >> "%LOG%"
