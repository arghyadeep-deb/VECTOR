@echo off
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python tools\build_frontend.py > build_frontend.log 2>&1
echo exit=%errorlevel% >> build_frontend.log
