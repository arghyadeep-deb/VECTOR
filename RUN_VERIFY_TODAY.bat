@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\verify_session_2026_07_29.log"
echo ==== verify 2026-07-29 session fixes %DATE% %TIME% ==== > "%LOG%"
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python scripts\verify_session_2026_07_29.py >> "%LOG%" 2>&1
echo exit=%errorlevel% >> "%LOG%"
echo DONE_MARKER >> "%LOG%"
