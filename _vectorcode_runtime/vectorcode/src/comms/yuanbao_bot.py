"""Yuanbao adapter — WebSocket gateway with AUTH_BIND and heartbeat."""

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any, Callable, Optional

from loguru import logger

try:
    import aiohttp
    _AIOHTTP = True
except ImportError:
    _AIOHTTP = False

class YuanbaoBot:
    def __init__(self, app_id: str = "", app_secret: str = "", bot_id: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self.bot_id = bot_id
        self._ws = None
        self._running = False
        self._callback: Optional[Callable] = None
        self._session: Optional[aiohttp.ClientSession] = None

    def on_message(self, callback: Callable):
        self._callback = callback

    async def start(self):
        if not _AIOHTTP:
            logger.warning("aiohttp not installed")
            return
        self._running = True
        self._session = aiohttp.ClientSession()
        timestamp = str(int(time.time()))
        sig = hmac.new(self.app_secret.encode(), (timestamp + self.app_id).encode(), hashlib.sha256).hexdigest()
        ws_url = f"wss://wss-bot.ys7.com/ws?app_id={self.app_id}&timestamp={timestamp}&sign={sig}"
        self._ws = await self._session.ws_connect(ws_url)
        await self._ws.send_str(json.dumps({"type": "AUTH_BIND", "data": {"bot_id": self.bot_id}}))
        asyncio.create_task(self._heartbeat())
        asyncio.create_task(self._receive_loop())
        logger.info("Yuanbao connected")

    async def _heartbeat(self):
        while self._running:
            await asyncio.sleep(30)
            if self._ws: await self._ws.send_str(json.dumps({"type": "PING"}))

    async def _receive_loop(self):
        while self._running and self._ws:
            msg = await self._ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("type") == "T05" and self._callback:
                    await self._callback(data.get("data", {}))
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                break

    async def send(self, user_id: str, text: str):
        if self._ws:
            await self._ws.send_str(json.dumps({"type": "T06", "data": {"to": user_id, "content": text}}))

    async def stop(self):
        self._running = False
        if self._ws: await self._ws.close()
        if self._session: await self._session.close()
