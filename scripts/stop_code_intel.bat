@echo off
REM Stop the local Qdrant started by start_code_intel.bat (indexes stay on disk).
taskkill /im qdrant.exe /f >nul 2>&1
echo Qdrant stopped.
