@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\deepeval_smoke.log"
echo ==== deepeval smoke test %DATE% %TIME% ==== > "%LOG%"
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python scripts\deepeval_smoke_test.py >> "%LOG%" 2>&1
echo exit=%errorlevel% >> "%LOG%"
echo DONE_MARKER >> "%LOG%"
