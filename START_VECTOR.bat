@echo off
title VECTOR — Starting...
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

echo [VECTOR] Checking Ollama...
ollama list >nul 2>&1
if errorlevel 1 (
    echo [VECTOR] Starting Ollama...
    start /min ollama serve
    timeout /t 3 /nobreak >nul
)

echo [VECTOR] Running smoke test...
python run_vector.py smoke
if errorlevel 1 (
    echo [VECTOR] Smoke test FAILED. Check your .env and Ollama models.
    pause
    exit /b 1
)

echo [VECTOR] Starting autonomous loop...
title VECTOR — Running
python run_vector.py loop
pause
