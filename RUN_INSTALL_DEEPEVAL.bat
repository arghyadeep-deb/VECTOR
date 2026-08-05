@echo off
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\install_deepeval.log"
echo ==== install deepeval %DATE% %TIME% ==== > "%LOG%"
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python -m pip install --upgrade deepeval >> "%LOG%" 2>&1
echo pip_exit=%errorlevel% >> "%LOG%"
python -c "import deepeval; print('DEEPEVAL_VERSION', deepeval.__version__)" >> "%LOG%" 2>&1
echo verify_exit=%errorlevel% >> "%LOG%"
echo DONE_MARKER >> "%LOG%"
