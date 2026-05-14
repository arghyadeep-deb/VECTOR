"""WeChat adapter — Tencent iLink Bot API integration."""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class WeChatBot:
    def __init__(self, bot_id: str = "", token: str = ""):
        self.bot_id = bot_id
        self.token = token
        self._callback: Optional[Callable] = None

    def on_message(self, callback: Callable):
        self._callback = callback

    async def start(self):
        logger.info(f"WeChat bot {self.bot_id} starting")

    async def send(self, user_id: str, text: str):
        pass

    async def stop(self):
        pass
