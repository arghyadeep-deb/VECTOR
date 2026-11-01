"""QQ Bot adapter — Tencent QQ channel bot via WebSocket/HTTP."""

import asyncio
import json
from typing import Any, Callable, Optional

from loguru import logger

try:
    import aiohttp
    _AIOHTTP = True
except ImportError:
    _AIOHTTP = False

class QQBot:
    def __init__(self, app_id: str = "", token: str = ""):
        self.app_id = app_id
        self.token = token
        self._ws = None
        self._session = None
        self._running = False
        self._message_callback: Optional[Callable] = None
        self._intents = 1 << 30  # all intents

    def on_message(self, callback: Callable):
        self._message_callback = callback

    async def start(self):
        if not _AIOHTTP: return
        self._running = True
        self._session = aiohttp.ClientSession(headers={
            "Authorization": f"Bot {self.app_id}.{self.token}",
            "X-Union-Appid": self.app_id,
        })
        ws_info = await self._get_ws_endpoint()
        if not ws_info: return
        self._ws = await self._session.ws_connect(ws_info["url"])
        asyncio.create_task(self._heartbeat(ws_info.get("heartbeat", 30)))
        asyncio.create_task(self._receive_loop())
        logger.info(f"QQ bot connected (app_id={self.app_id})")

    async def _get_ws_endpoint(self) -> Optional[dict]:
        r = await self._session.get("https://api.sgroup.qq.com/gateway/bot")
        if r.status != 200: return None
        data = await r.json()
        return {"url": data["url"], "heartbeat": data.get("heartbeat_interval", 30000) // 1000}

    async def _heartbeat(self, interval: int):
        while self._running:
            await asyncio.sleep(interval)
            if self._ws: await self._ws.send_str(json.dumps({"op": 1, "d": None}))

    async def _receive_loop(self):
        while self._running and self._ws:
            msg = await self._ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                op = data.get("op")
                if op == 0 and self._message_callback:
                    await self._message_callback(data.get("d", {}))
                elif op == 7: await self._reconnect()

    async def _reconnect(self):
        await asyncio.sleep(3)
        if self._session and self._running:
            ws_info = await self._get_ws_endpoint()
            if ws_info: self._ws = await self._session.ws_connect(ws_info["url"])

    async def send(self, channel_id: str, text: str):
        if not self._session: return
        await self._session.post(f"https://api.sgroup.qq.com/channels/{channel_id}/messages",
                                json={"content": text})

    async def stop(self):
        self._running = False
        if self._ws: await self._ws.close()
        if self._session: await self._session.close()
