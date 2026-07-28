@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\verify_issue37.log"
echo ==== verify issue 37 %DATE% %TIME% ==== > "%LOG%"
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python scripts\verify_issue37_voice.py >> "%LOG%" 2>&1
echo exit=%errorlevel% >> "%LOG%"
echo DONE_MARKER >> "%LOG%"
