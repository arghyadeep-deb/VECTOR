@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\run_task.log"
schtasks /Run /TN VECTOR > "%LOG%" 2>&1
echo exit=%errorlevel% >> "%LOG%"
