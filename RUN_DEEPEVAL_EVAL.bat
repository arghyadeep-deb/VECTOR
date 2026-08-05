@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\deepeval_eval.log"
echo ==== deepeval full eval %DATE% %TIME% ==== > "%LOG%"
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

echo --- PHASE A: collect real VECTOR responses --- >> "%LOG%"
python scripts\deepeval_collect.py >> "%LOG%" 2>&1
echo collect_exit=%errorlevel% >> "%LOG%"

echo --- PHASE B: score via local DeepEval judge --- >> "%LOG%"
python scripts\deepeval_score.py >> "%LOG%" 2>&1
echo score_exit=%errorlevel% >> "%LOG%"

echo DONE_MARKER >> "%LOG%"
