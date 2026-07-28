@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\mistral_direct_test.log"
echo ==== mistral direct test %DATE% %TIME% ==== > "%LOG%"
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python scripts\test_mistral_judge_direct.py >> "%LOG%" 2>&1
echo exit=%errorlevel% >> "%LOG%"
echo DONE_MARKER >> "%LOG%"
