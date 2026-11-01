"""DingTalk adapter — Stream Mode via dingtalk-stream SDK.

FLAG FOR OWNER, not fixed: send() is a no-op stub -- it only logs the
message, it never actually calls anything on self._client to deliver it
("phantom success" shape, the dominant bug class this audit cycle; same
as every send() elsewhere actually making a real network/SDK call).
dingtalk_stream is not installed in this environment and has zero real
callers of this class anywhere (confirmed via repo-wide grep), so the
real fix (wiring the actual SDK send call) can't be verified here --
flagged for whoever activates this channel, not guessed at blindly.
"""

from typing import Callable, Optional

from loguru import logger

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
