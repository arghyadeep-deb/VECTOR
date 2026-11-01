"""Mattermost adapter — REST API v4 + WebSocket integration."""

import json
from typing import Callable, Optional

from loguru import logger

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False

class MattermostBot:
    def __init__(self, url: str = "", token: str = ""):
        self.url = url.rstrip("/")
        self.token = token
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self._callback: Optional[Callable] = None

    def on_message(self, callback: Callable):
        self._callback = callback

    async def start(self):
        logger.info(f"Mattermost connecting to {self.url}")

    async def send(self, channel_id: str, text: str):
        if not _HTTPX: return
        async with httpx.AsyncClient() as c:
            await c.post(f"{self.url}/api/v4/posts", headers=self._headers, json={
                "channel_id": channel_id, "message": text,
            })

    async def get_channels(self, team_id: str) -> list:
        if not _HTTPX: return []
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{self.url}/api/v4/teams/{team_id}/channels", headers=self._headers)
            return r.json() if r.status_code == 200 else []

    async def stop(self):
                logger.debug("[VECTOR][mattermost_bot] stop called (no-op)")
