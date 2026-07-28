@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\langsmith_eval_verify.log"
echo ==== stub-fix verify %DATE% %TIME% ==== > "%LOG%"
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python scripts\langsmith_vector_eval.py tier2 >> "%LOG%" 2>&1
echo exit_tier2=%errorlevel% >> "%LOG%"
echo DONE_MARKER >> "%LOG%"
