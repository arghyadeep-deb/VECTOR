"""Heartbeat-based hot failover for primary → secondary instance."""

from __future__ import annotations

__all__ = [
    "HotFailover",
    "StateDigest",
]


import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any

from loguru import logger

from core.config import CONFIG


@dataclass
class StateDigest:
    timestamp: float = 0.0
    loop_state: dict = field(default_factory=dict)
    active_sessions: list = field(default_factory=list)
    memory_pending: int = 0
    circuit_breaker_states: dict = field(default_factory=dict)
    bulkhead_active_counts: dict = field(default_factory=dict)
    generation: int = 0
    config_hash: str = ""


class HotFailover:
    def __init__(self, is_primary: bool = True):
        config = CONFIG.get("resilience", {}).get("failover", {})
        self.is_primary = is_primary
        self.secondary_url = config.get("secondary_url", "http://127.0.0.1:8001")
        self.heartbeat_interval = config.get("heartbeat_interval", 5.0)
        self.max_missed_heartbeats = config.get("max_missed_heartbeats", 3)
        self.missed_heartbeats = 0
        self.last_digest: StateDigest | None = None
        self._primary_active = False
        self._running = False
        self._state_provider: callable | None = None
        self._on_takeover: list[callable] = []
        self._on_relinquish: list[callable] = []

    async def start_primary(self, state_provider: callable | None = None) -> None:
        self.is_primary = True
        self._state_provider = state_provider
        self._running = True
        logger.info("[HotFailover] Primary mode started — heartbeating to {}", self.secondary_url)

    async def start_secondary(self) -> None:
        self.is_primary = False
        self._running = True
        logger.info("[HotFailover] Secondary mode started — listening for heartbeats")

    async def stop(self) -> None:
        self._running = False

    async def send_heartbeat(self) -> bool:
        if not self._running or not self.is_primary:
            return False
        try:
            import httpx
            digest = await self._build_digest()
            # NOTE: `await httpx.post(...)` is invalid -- the module-level
            # post() is SYNC, not a coroutine, so this raised TypeError on
            # every real call and was silently swallowed below, meaning no
            # heartbeat ever actually reached the secondary.
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.post(
                    f"{self.secondary_url}/api/v1/failover/heartbeat",
                    json=asdict(digest),
                )
            return resp.status_code == 200
        except Exception as e:
            logger.debug("[HotFailover] heartbeat send failed: {}", e)
            return False

    async def receive_heartbeat(self, data: dict) -> bool:
        if self.is_primary:
            return False
        self.missed_heartbeats = 0
        self.last_digest = StateDigest(**data)
        self._primary_active = True
        return True

    async def check_heartbeat(self) -> None:
        if self.is_primary or not self._running:
            return
        self.missed_heartbeats += 1
        if self.missed_heartbeats >= self.max_missed_heartbeats and self._primary_active:
            logger.warning("[HotFailover] Primary heartbeat lost — initiating failover")
            await self.take_over()

    async def take_over(self) -> None:
        logger.info("[HotFailover] Secondary taking over as primary")
        self._primary_active = False
        self.is_primary = True
        for cb in self._on_takeover:
            try:
                await cb(self.last_digest)
            except Exception as e:
                logger.error("[HotFailover] takeover callback failed: {}", e)

    async def relinquish(self) -> None:
        logger.info("[HotFailover] Primary relinquishing to secondary")
        self.is_primary = False
        for cb in self._on_relinquish:
            try:
                await cb()
            except Exception as e:
                logger.error("[HotFailover] relinquish callback failed: {}", e)

    def on_takeover(self, callback: callable) -> None:
        self._on_takeover.append(callback)

    def on_relinquish(self, callback: callable) -> None:
        self._on_relinquish.append(callback)

    async def _build_digest(self) -> StateDigest:
        digest = StateDigest(timestamp=time.time())
        if self._state_provider:
            try:
                state = await self._state_provider()
                if state:
                    for key, val in state.items():
                        if hasattr(digest, key):
                            setattr(digest, key, val)
            except Exception as e:
                logger.debug("[HotFailover] state_provider error: {}", e)
        return digest

    async def heartbeat_loop(self) -> None:
        while self._running:
            if self.is_primary:
                await self.send_heartbeat()
            else:
                await self.check_heartbeat()
            await asyncio.sleep(self.heartbeat_interval)
