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

echo [VECTOR] Starting HTTP API server in its own window...
REM 2026-07-22 KNOWN_ISSUES #17: `loop` and `api` are two separate processes
REM in run_vector.py — `loop` runs the autonomous sense/act loop but NEVER
REM binds the HTTP server, so /health and /command were dead after a normal
REM start (the backend "looked up" in its window while the API was simply not
REM running). Launch the API in its own window BEFORE the loop so the endpoints
REM the HUD and eval harness depend on are actually online.
start "VECTOR API" cmd /k "cd /d ""C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"" && python run_vector.py api --host 0.0.0.0"
timeout /t 5 /nobreak >nul

echo [VECTOR] Starting autonomous loop...
title VECTOR — Running
python run_vector.py loop
pause
