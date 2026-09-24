@echo off
title VECTOR - Restart API
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"

echo [1/3] Python syntax check on patched files...
python -m py_compile core\api\routers\control.py core\api\routers\loop.py core\api\routers\commands.py core\api\routers\content.py core\loop\loop_state.py districts\content\video_pipeline.py vectorcode\src\vc_agents\__init__.py
if errorlevel 1 (
    echo [FAIL] Syntax error in patched backend files - NOT restarting.
    pause
    exit /b 1
)

echo [2/3] Stopping old API on :8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1
timeout /t 3 /nobreak >nul

echo [3/3] Starting API...
start "VECTOR API" cmd /k "python run_vector.py api --host 0.0.0.0"
echo Done - API restarting in its own window. This window closes in 8s.
timeout /t 8 >nul
