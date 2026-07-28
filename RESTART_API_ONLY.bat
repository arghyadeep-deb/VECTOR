@echo off
title VECTOR API — Restart
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
echo [1/3] Syntax check on patched avatar layer...
python -m py_compile core\avatar\avatar_voice.py core\city\governor.py core\api\routers\commands.py core\api_manager.py core\city\prompt_agent.py districts\memory_curator\pattern_finder.py districts\memory_curator\consolidation_bot.py districts\skills\skill_mapper.py districts\skills\mastery_tracker.py districts\data_analytics\__init__.py districts\pattern_detective\habit_finder.py districts\pattern_detective\behavior_analyst.py districts\relationships\communication_analyst.py districts\privacy\privacy_enforcer.py districts\research\deep_researcher.py core\voice\tts.py core\voice\realtime.py core\voice\ambient_listener.py core\api\routers\voice_ws.py
if errorlevel 1 (
    echo [FAIL] Syntax error - NOT restarting.
    pause
    exit /b 1
)
echo [2/3] Stopping old API on :8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1
timeout /t 3 /nobreak >nul
echo [3/3] Starting API with patched code...
python run_vector.py api --host 0.0.0.0
pause
