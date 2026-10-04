"""WhatsApp adapter — Business API and web-based backends."""

import json
from typing import Callable, Optional

from loguru import logger

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False

class WhatsAppBot:
    def __init__(self, api_key: str = "", phone_id: str = "", backend: str = "business"):
        self.api_key = api_key
        self.phone_id = phone_id
        self.backend = backend
        self._callback: Optional[Callable] = None

    def on_message(self, callback: Callable):
        self._callback = callback

    async def start(self):
        logger.info(f"WhatsApp bot starting ({self.backend} backend)")

    async def send(self, to: str, text: str):
        if not _HTTPX or self.backend != "business":
            return
        async with httpx.AsyncClient() as c:
            await c.post(
                f"https://graph.facebook.com/v18.0/{self.phone_id}/messages",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"messaging_product": "whatsapp", "to": to, "text": {"body": text}},
            )

    async def stop(self):
                logger.debug("[VECTOR][whatsapp_bot] stop called (no-op)")
