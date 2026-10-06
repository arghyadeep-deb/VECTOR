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
        self._session = None

    async def connect(self):
        if not _AIOHTTP:
            logger.warning("aiohttp not installed")
            return False
        ws_url = self.url.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(ws_url)
            auth_required = json.loads(await self._ws.receive_str())
            if auth_required.get("type") != "auth_required":
                logger.error("Home Assistant sent an unexpected auth handshake")
                await self.stop()
                return False
            await self._ws.send_str(json.dumps({"type": "auth", "access_token": self.token}))
            auth_result = json.loads(await self._ws.receive_str())
            if auth_result.get("type") != "auth_ok":
                logger.error("Home Assistant authentication failed")
                await self.stop()
                return False
        except Exception:
            logger.opt(exception=True).error("Home Assistant connection failed")
            await self.stop()
            return False
        logger.info("Home Assistant connected")
        return True

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
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._session:
            await self._session.close()
            self._session = None
