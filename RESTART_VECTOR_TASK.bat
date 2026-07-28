@echo off
REM Restart the VECTOR scheduled task so patched backend code loads.
REM Logs everything to restart_task.log so Claude can read the result.
set "LOG=C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\restart_task.log"
echo ==== VECTOR restart %DATE% %TIME% ==== > "%LOG%"

echo [0] Syntax check on patched files... >> "%LOG%"
cd /d "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase"
python -m py_compile core\api\routers\content.py core\api\routers\control.py core\api\routers\loop.py core\api\routers\commands.py core\loop\loop_state.py core\loop\permission_gateway.py core\voice\stt.py core\control\phone_controller.py core\control\pc_controller.py core\loop\autonomous_loop.py core\city\agent_registry.py districts\content\video_pipeline.py districts\content\phone_poster.py core\city\governor.py core\inference\ollama_safe.py core\api\routers\websocket.py core\memory\episodic.py >> "%LOG%" 2>&1
if errorlevel 1 (
    echo SYNTAX CHECK FAILED - aborting restart >> "%LOG%"
    exit /b 1
)
echo [0b] phone_poster self-test... >> "%LOG%"
python districts\content\phone_poster.py >> "%LOG%" 2>&1
if errorlevel 1 (
    echo SYNTAX CHECK FAILED - aborting restart >> "%LOG%"
    exit /b 1
)
echo syntax ok >> "%LOG%"

echo [1] Killing any stray python run_vector processes... >> "%LOG%"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*run_vector.py*' } | ForEach-Object { Write-Output ('killing pid ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >> "%LOG%" 2>&1

echo [2] Freeing port 8000... >> "%LOG%"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >> "%LOG%" 2>&1

timeout /t 3 /nobreak >nul

echo [3] Ending scheduled task VECTOR... >> "%LOG%"
schtasks /End /TN VECTOR >> "%LOG%" 2>&1

REM 12s: give the dying python time to fully exit, or the autostart guard
REM sees it and skips the relaunch (hit this race on 2026-07-20).
timeout /t 12 /nobreak >nul

echo [4] Running scheduled task VECTOR... >> "%LOG%"
schtasks /Run /TN VECTOR >> "%LOG%" 2>&1

echo [5] Waiting 35s for boot, then probing /status... >> "%LOG%"
timeout /t 35 /nobreak >nul
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/status' -TimeoutSec 10; Write-Output ('STATUS OK uptime_s=' + $r.uptime_seconds + ' loop_running=' + $r.loop_running) } catch { Write-Output ('STATUS PROBE FAILED: ' + $_.Exception.Message) }" >> "%LOG%" 2>&1

echo [6] Probing /loop/status... >> "%LOG%"
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/loop/status' -TimeoutSec 10; Write-Output ('LOOP running=' + $r.running + ' ticks=' + $r.tick_count + ' uptime_s=' + $r.uptime_seconds) } catch { Write-Output ('LOOP PROBE FAILED: ' + $_.Exception.Message) }" >> "%LOG%" 2>&1

echo DONE >> "%LOG%"
