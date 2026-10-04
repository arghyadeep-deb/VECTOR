"""Home Assistant adapter — WebSocket API for smart home control."""

import json
from typing import Any, Optional

from loguru import logger

try:
    import aiohttp
    _AIOHTTP = True
except ImportError:
    _AIOHTTP = False

class HomeAssistantBot:
    def __init__(self, url: str = "", token: str = ""):
        self.url = url
        self.token = token
        self._ws = None

    async def connect(self):
        if not _AIOHTTP:
            logger.warning("aiohttp not installed")
            return
        ws_url = self.url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
        session = aiohttp.ClientSession()
        self._ws = await session.ws_connect(ws_url)
        auth_msg = json.loads(await self._ws.receive_str())
        await self._ws.send_str(json.dumps({"type": "auth", "access_token": self.token}))
        logger.info("Home Assistant connected")

    async def get_state(self, entity_id: str) -> Optional[dict]:
        if not self._ws: return None
        await self._ws.send_str(json.dumps({"id": 1, "type": "get_states"}))
        resp = json.loads(await self._ws.receive_str())
        for state in resp.get("result", []):
            if state["entity_id"] == entity_id:
                return state
        return None

    async def call_service(self, domain: str, service: str, data: Optional[dict] = None):
        if not self._ws: return
        await self._ws.send_str(json.dumps({
            "id": 2, "type": "call_service",
            "domain": domain, "service": service,
            "service_data": data or {},
        }))
        return json.loads(await self._ws.receive_str())

    async def stop(self):
        if self._ws: await self._ws.close()
