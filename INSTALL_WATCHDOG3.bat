@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\install_watchdog3.log"
echo ==== install watchdog task (v3, standalone ps1) %DATE% %TIME% ==== > "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\scripts\install_watchdog_task.ps1" >> "%LOG%" 2>&1
echo exit=%errorlevel% >> "%LOG%"
echo DONE_MARKER >> "%LOG%"
