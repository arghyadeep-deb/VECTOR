"""BlueBubbles iMessage adapter — connects to local macOS BlueBubbles server."""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False


class BlueBubblesBot:
    def __init__(self, server_url: str = "http://localhost:1234", password: str = ""):
        self.server_url = server_url
        self.password = password
        self._callback: Optional[Callable] = None

    def on_message(self, callback: Callable):
        self._callback = callback

    async def start(self):
        logger.info(f"BlueBubbles connecting to {self.server_url}")

    async def send(self, chat_guid: str, text: str):
        if not _HTTPX:
            return
        async with httpx.AsyncClient() as c:
            await c.post(f"{self.server_url}/api/private/chat/send-message", params={"password": self.password}, json={"chatGuid": chat_guid, "text": text})

    async def stop(self):
        pass
