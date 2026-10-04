"""Matrix adapter — homeserver-agnostic chat via mautrix SDK."""

from typing import Callable, Optional

from loguru import logger

try:
    from maatrix import MatrixClient as _MC
    _MATRIX = True
except ImportError:
    _MATRIX = False

class MatrixBot:
    def __init__(self, homeserver: str = "", token: str = "", user_id: str = ""):
        self.homeserver = homeserver
        self.token = token
        self.user_id = user_id
        self._callback: Optional[Callable] = None
        self._client = None

    def on_message(self, callback: Callable):
        self._callback = callback

    async def start(self):
        if not _MATRIX:
            logger.warning("maatrix not installed. Run: pip install maatrix")
            return
        self._client = _MC(self.homeserver, self.token)
        await self._client.login()
        logger.info(f"Matrix bot connected as {self.user_id}")

        @self._client.on_event("room.message")
        async def handler(event):
            if self._callback:
                await self._callback(event)

    async def send(self, room_id: str, text: str):
        if self._client:
            await self._client.send_text(room_id, text)

    async def stop(self):
        if self._client:
            await self._client.close()
