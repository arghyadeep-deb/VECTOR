@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\langsmith_eval_tier56.log"
echo ==== langsmith eval tier5+6 %DATE% %TIME% ==== > "%LOG%"
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python scripts\langsmith_vector_eval.py tier5 >> "%LOG%" 2>&1
echo exit_tier5=%errorlevel% >> "%LOG%"
python scripts\langsmith_vector_eval.py tier6 >> "%LOG%" 2>&1
echo exit_tier6=%errorlevel% >> "%LOG%"
echo DONE_MARKER >> "%LOG%"
