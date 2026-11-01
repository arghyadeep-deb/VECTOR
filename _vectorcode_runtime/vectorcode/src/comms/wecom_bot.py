"""WeCom (Enterprise WeChat) adapter — AI Bot WebSocket gateway."""

import json
from typing import Callable, Optional

from loguru import logger

try:
    import aiohttp
    _AIOHTTP = True
except ImportError:
    _AIOHTTP = False

class WeComBot:
    def __init__(self, bot_id: str = "", secret: str = ""):
        self.bot_id = bot_id
        self.secret = secret
        self._callback: Optional[Callable] = None
        self._ws = None

    def on_message(self, callback: Callable):
        self._callback = callback

    async def start(self):
        if not _AIOHTTP: return
        token = await self._get_token()
        if not token: return
        ws_url = f"wss://wss-bot.wecom.tencent.com/websocket?token={token}"
        session = aiohttp.ClientSession()
        self._ws = await session.ws_connect(ws_url)
        logger.info("WeCom connected")

    async def _get_token(self) -> Optional[str]:
        async with aiohttp.ClientSession() as s:
            r = await s.post(f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={self.bot_id}&corpsecret={self.secret}")
            data = await r.json()
            return data.get("access_token")

    async def send(self, user_id: str, text: str):
        logger.info(f"WeCom send to {user_id}: {text[:50]}")

    async def stop(self):
        if self._ws: await self._ws.close()
