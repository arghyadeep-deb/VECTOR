#!/bin/bash
# Start Shadowbroker Intelligence Server for VECTOR
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$SCRIPT_DIR/../districts/intelligence/shadowbroker_server"
PORT=${PORT:-8002}

echo "[VECTOR] Starting Shadowbroker on port $PORT..."
cd "$SERVER_DIR"

pip install apscheduler fastapi uvicorn httpx pydantic pydantic-settings python-dotenv \
    requests orjson slowapi sgp4 yfinance feedparser cryptography PyNaCl cachetools \
    vaderSentiment beautifulsoup4 reverse-geocoder pystac-client -q

PORT=$PORT python main.py
