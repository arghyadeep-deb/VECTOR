"""Signal messenger adapter — connects to signal-cli daemon HTTP mode."""

import json
from typing import Callable, Optional

from loguru import logger

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

class SignalBot:
    def __init__(self, http_url: str = "http://127.0.0.1:8080", account: str = ""):
        self.http_url = http_url
        self.account = account
        self._callback: Optional[Callable] = None

    def on_message(self, callback: Callable):
        self._callback = callback

    async def start(self):
        if not _HTTPX_AVAILABLE:
            logger.warning("httpx not installed. Run: pip install httpx")
            return
        logger.info(f"Signal bot connecting to {self.http_url}")

    async def send(self, recipient: str, text: str):
        if not _HTTPX_AVAILABLE:
            return
        async with httpx.AsyncClient() as client:
            payload = {
                "jsonrpc": "2.0",
                "method": "send",
                "params": {"recipient": recipient, "message": text},
            }
            await client.post(f"{self.http_url}/api/v1/rpc", json=payload)

    async def stop(self):
                logger.debug("[VECTOR][signal_bot] stop called (no-op)")
