@echo off
setlocal

set SERVER_DIR=%~dp0..\districts\intelligence\shadowbroker_server
set PORT=8002

echo [VECTOR] Starting Shadowbroker Intelligence Server on port %PORT%...
echo [VECTOR] Server dir: %SERVER_DIR%
echo.

cd /d "%SERVER_DIR%"

:: Install dependencies if needed
pip install apscheduler fastapi uvicorn httpx pydantic pydantic-settings python-dotenv requests orjson slowapi sgp4 yfinance feedparser cryptography PyNaCl cachetools vaderSentiment beautifulsoup4 reverse-geocoder pystac-client --quiet 2>nul

:: Start the server on port 8002 (VECTOR runs on 8000)
set PORT=%PORT%
python main.py

endlocal
