"""DingTalk adapter — Stream Mode via dingtalk-stream SDK."""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import dingtalk_stream
    _DINGTALK = True
except ImportError:
    _DINGTALK = False

class DingTalkBot:
    def __init__(self, client_id: str = "", client_secret: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self._callback: Optional[Callable] = None
        self._client = None

    def on_message(self, callback: Callable):
        self._callback = callback

    async def start(self):
        if not _DINGTALK:
            logger.warning("dingtalk-stream not installed")
            return
        self._client = dingtalk_stream.DingTalkStreamClient(self.client_id, self.client_secret)
        logger.info("DingTalk connected")

    async def send(self, conversation_id: str, text: str):
        logger.info(f"DingTalk send to {conversation_id}: {text[:50]}")

    async def stop(self):
        if self._client: self._client.close()
