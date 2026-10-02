"""BlueBubbles iMessage adapter — connects to local macOS BlueBubbles server.

NOTE: a second, separate BlueBubbles implementation exists at
vectorcode/src/comms/bluebubbles.py (BlueBubblesChannel, registered on
ChannelRegistry) -- this BlueBubblesBot class has zero real callers
anywhere (confirmed via repo-wide grep). Same unexplained-duplication
shape as the owner's jcode/vectorcode question this cycle; flagged, not
resolved here.
"""

from typing import Callable, Optional

from loguru import logger

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

    async def send(self, chat_guid: str, text: str) -> bool:
        if not _HTTPX:
            return False
        try:
            async with httpx.AsyncClient() as c:
                resp = await c.post(
                    f"{self.server_url}/api/private/chat/send-message",
                    params={"password": self.password},
                    json={"chatGuid": chat_guid, "text": text},
                )
                return resp.status_code < 300
        except Exception as e:
            logger.warning("[VECTOR][bluebubbles_bot] send failed: {}", e)
            return False

    async def stop(self):
        logger.debug("[VECTOR][bluebubbles_bot] stop called (no-op)")
