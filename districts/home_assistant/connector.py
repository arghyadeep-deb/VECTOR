from __future__ import annotations

import asyncio
import json
import os
import re
import time
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

import httpx

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG

@dataclass
class HAConfig:
    host: str = ""
    port: int = 8123
    token: str = ""
    use_ssl: bool = False
    rate_limit: int = 10

    def __post_init__(self):
        if not self.host:
            raw = (os.getenv("HASS_URL") or CONFIG.get("home_assistant", {}).get("host", "homeassistant.local")).strip().rstrip("/")
            if "://" not in raw:
                raw = "http://" + raw
            parsed = urlparse(raw)
            # An https:// URL must select TLS; the old string-replace parse
            # dropped the scheme and sent the bearer token in cleartext http.
            self.use_ssl = parsed.scheme == "https"
            self.host = parsed.hostname or "homeassistant.local"
            default_port = 443 if self.use_ssl else 8123
            try:
                self.port = parsed.port or default_port
            except ValueError:
                self.port = default_port
        if not self.token:
            self.token = os.getenv("HASS_TOKEN") or CONFIG.get("home_assistant", {}).get("token", "")

    @property
    def base_url(self) -> str:
        protocol = "https" if self.use_ssl else "http"
        return f"{protocol}://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        protocol = "wss" if self.use_ssl else "ws"
        return f"{protocol}://{self.host}:{self.port}/api/websocket"

_SLUG_RE = re.compile(r"^[a-z0-9_]+$")
_ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


class HARestClient:
    def __init__(self, config: HAConfig):
        self._config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._request_times: List[float] = []

    async def __aenter__(self):
        await self._ensure_client()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url,
                headers=self._headers(),
                timeout=httpx.Timeout(30.0),
            )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._config.token}",
            "Content-Type": "application/json",
        }

    async def _rate_limit(self):
        now = time.monotonic()
        window = 1.0
        self._request_times = [t for t in self._request_times if now - t < window]
        if len(self._request_times) >= self._config.rate_limit:
            sleep_for = self._request_times[0] + window - now
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        self._request_times.append(time.monotonic())

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        await self._ensure_client()
        await self._rate_limit()
        resp = await self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def get_states(self) -> List[Dict[str, Any]]:
        return await self._request("GET", "/api/states")

    async def get_state(self, entity_id: str) -> Dict[str, Any]:
        if not _ENTITY_ID_RE.match(entity_id or ""):
            raise ValueError(f"invalid entity_id: {entity_id!r}")
        return await self._request("GET", f"/api/states/{entity_id}")

    async def call_service(self, domain: str, service: str, data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not (_SLUG_RE.match(domain or "") and _SLUG_RE.match(service or "")):
            raise ValueError(f"invalid service: {domain!r}.{service!r}")
        payload = data or {}
        return await self._request("POST", f"/api/services/{domain}/{service}", json=payload)

    async def get_config(self) -> Dict[str, Any]:
        return await self._request("GET", "/api/config")

    async def get_services(self) -> List[Dict[str, Any]]:
        return await self._request("GET", "/api/services")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

class HAWebSocketClient:
    _BACKOFF_STEPS = [5, 10, 30, 60]

    def __init__(self, config: HAConfig):
        self._config = config
        self._ws = None
        self._msg_id: int = 0
        self._running: bool = False
        self._callbacks: Dict[str, List[Callable]] = {}
        self._pending: Dict[int, asyncio.Future] = {}

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def connect(self) -> bool:
        try:
            import websockets
        except ImportError:
            logger.error("[HA WS] websockets not installed. Run: pip install websockets")
            return False

        if not self._config.token:
            logger.error("[HA WS] No token configured")
            return False

        self._running = True
        backoff_idx = 0

        while self._running:
            try:
                ws = await websockets.connect(self._config.ws_url, ping_interval=30, ping_timeout=10)
                auth_msg = json.loads(await ws.recv())
                if auth_msg.get("type") != "auth_required":
                    logger.error("[HA WS] Expected auth_required, got: {}", auth_msg.get("type"))
                    await ws.close()
                    return False

                await ws.send(json.dumps({"type": "auth", "access_token": self._config.token}))
                auth_result = json.loads(await ws.recv())
                if auth_result.get("type") != "auth_ok":
                    logger.error("[HA WS] Auth failed: {}", auth_result)
                    await ws.close()
                    return False

                self._ws = ws
                logger.info("[HA WS] Connected and authenticated")
                backoff_idx = 0
                asyncio.create_task(self._reader_loop())
                return True

            except Exception as e:
                logger.warning("[HA WS] Connection failed: {}", e)
                if not self._running:
                    return False
                delay = self._BACKOFF_STEPS[min(backoff_idx, len(self._BACKOFF_STEPS) - 1)]
                logger.info("[HA WS] Reconnecting in {}s...", delay)
                await asyncio.sleep(delay)
                backoff_idx += 1

        return False

    async def _reader_loop(self):
        while self._running and self._ws:
            try:
                msg = json.loads(await self._ws.recv())
                msg_type = msg.get("type", "")
                msg_id = msg.get("id")

                if msg_id and msg_id in self._pending:
                    future = self._pending.pop(msg_id)
                    if not future.done():
                        future.set_result(msg)

                if msg_type == "event":
                    event = msg.get("event", {})
                    event_type = event.get("event_type", "")
                    for cb in self._callbacks.get(event_type, []):
                        try:
                            await cb(event)
                        except Exception as e:
                            logger.warning("[HA WS] callback error: {}", e)
                    for cb in self._callbacks.get("*", []):
                        try:
                            await cb(event)
                        except Exception as e:
                            logger.warning("[HA WS] wildcard callback error: {}", e)

            except Exception as e:
                logger.warning("[HA WS] Reader error: {}", e)
                break

        if self._running:
            asyncio.create_task(self.connect())

    async def _send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self._ws:
            raise ConnectionError("WebSocket not connected")
        msg_id = payload.get("id", self._next_id())
        payload["id"] = msg_id
        future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        await self._ws.send(json.dumps(payload))
        result = await asyncio.wait_for(future, timeout=30.0)
        return result

    async def subscribe_events(self, event_type: Optional[str] = None):
        payload = {"type": "subscribe_events"}
        if event_type:
            payload["event_type"] = event_type
        return await self._send(payload)

    async def get_states(self) -> List[Dict[str, Any]]:
        result = await self._send({"type": "get_states"})
        return result.get("result", [])

    async def call_service(self, domain: str, service: str, data: Optional[Dict[str, Any]] = None) -> Any:
        payload: Dict[str, Any] = {
            "type": "call_service",
            "domain": domain,
            "service": service,
        }
        if data:
            payload["service_data"] = data
        result = await self._send(payload)
        if not result.get("success", False):
            raise RuntimeError(f"HA call_service {domain}.{service} failed: {result.get('error')}")
        return result.get("result")

    def on_event(self, event_type: str, callback: Callable):
        if event_type not in self._callbacks:
            self._callbacks[event_type] = []
        self._callbacks[event_type].append(callback)

    async def disconnect(self):
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

class HAConnector:
    def __init__(self, config: HAConfig):
        self._config = config
        self.rest = HARestClient(config)
        self.ws = HAWebSocketClient(config)
        self._connected: bool = False

    async def connect(self) -> bool:
        # Preflight REST: an unreachable HA must report False (callers then say
        # "couldn't reach"), not hang in the WS reconnect loop or claim success.
        try:
            await self.rest._ensure_client()
            await self.rest.get_config()
        except Exception as e:
            logger.error("[VECTOR][ha_connector] Home Assistant unreachable at {}: {}", self._config.base_url, e)
            return False
        try:
            ws_ok = await asyncio.wait_for(self.ws.connect(), timeout=15.0)
        except asyncio.TimeoutError:
            await self.ws.disconnect()  # stops the endless reconnect loop
            ws_ok = False
        except Exception as e:
            logger.warning("[VECTOR][ha_connector] WebSocket connect error: {}", e)
            ws_ok = False
        self._connected = True
        if ws_ok:
            logger.info("[VECTOR][ha_connector] Connected via REST + WebSocket")
        else:
            logger.warning("[VECTOR][ha_connector] WebSocket failed, REST only")
        return True

    async def disconnect(self):
        self._connected = False
        await self.ws.disconnect()
        await self.rest.close()

    async def health(self) -> Dict[str, Any]:
        result = {"rest": False, "ws": False, "config": self._config.base_url}
        try:
            cfg = await self.rest.get_config()
            result["rest"] = bool(cfg.get("version"))
        except Exception as e:
            logger.warning("[VECTOR][ha_connector] health check failed: {}", e)
        result["ws"] = self.ws._ws is not None
        return result
