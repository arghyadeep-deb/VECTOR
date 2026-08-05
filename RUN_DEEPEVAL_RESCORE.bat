@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\deepeval_rescore.log"
echo ==== deepeval rescore (harness-fix v2) %DATE% %TIME% ==== > "%LOG%"
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

python scripts\deepeval_score.py >> "%LOG%" 2>&1
echo score_exit=%errorlevel% >> "%LOG%"

echo DONE_MARKER >> "%LOG%"
