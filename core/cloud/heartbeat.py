"""CloudBrainHeartbeat — periodic status push from local VECTOR to cloud brain server."""
from __future__ import annotations

import asyncio
import time

from loguru import logger

try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False


class CloudBrainHeartbeat:
    """Sends periodic heartbeats from local VECTOR to the cloud brain server.

    Enabled only when brain_url is non-empty and httpx is available.
    When disabled all methods are no-ops — zero overhead when not configured.
    """

    def __init__(
        self,
        brain_url: str = "",
        api_key: str = "",
        interval_sec: int = 60,
    ) -> None:
        self._url = (brain_url or "").rstrip("/")
        self._api_key = api_key
        self._interval = interval_sec
        self._running = False

    def is_enabled(self) -> bool:
        return bool(self._url) and _HTTPX_OK

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    def build_payload(self) -> dict:
        """Build the heartbeat payload with current system stats."""
        payload: dict = {"ts": time.time(), "source": "local_legion"}
        try:
            from core.city.agent_registry import AgentRegistry
            agents = AgentRegistry().list_all()
            alive = sum(1 for a in agents if a.get("hp", 0) > 0)
            payload["alive_agents"] = alive
            payload["total_agents"] = len(agents)
        except Exception as e:
            logger.warning("[VECTOR][cloud_heartbeat] agent registry stats unavailable: {}", e)
        try:
            from core.memory.episodic import EpisodicMemory
            stats = EpisodicMemory().get_stats()
            payload["memory_events"] = stats.get("total_events", 0)
        except Exception as e:
            logger.warning("[VECTOR][cloud_heartbeat] episodic memory stats unavailable: {}", e)
        return payload

    async def send(self) -> bool:
        """Send one heartbeat. Returns True on success, False on failure/disabled."""
        if not self.is_enabled():
            return False
        try:
            payload = self.build_payload()
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{self._url}/heartbeat",
                    json=payload,
                    headers=self._headers(),
                )
                ok = r.status_code == 200
                if ok:
                    logger.debug("[VECTOR][cloud_heartbeat] sent ok → {}", self._url)
                else:
                    logger.warning("[VECTOR][cloud_heartbeat] {} → {}", r.status_code, self._url)
                return ok
        except Exception as e:
            logger.debug("[VECTOR][cloud_heartbeat] send failed: {}", e)
            return False

    async def start_loop(self) -> None:
        """Run the heartbeat loop (call as asyncio.create_task — runs until stop())."""
        if not self.is_enabled():
            logger.debug("[VECTOR][cloud_heartbeat] disabled (no brain_url)")
            return
        self._running = True
        logger.info(
            "[VECTOR][cloud_heartbeat] starting → {} (interval={}s)",
            self._url, self._interval,
        )
        while self._running:
            try:
                await self.send()
            except Exception as e:
                logger.error("[VECTOR][cloud_heartbeat] loop error: {}", e)
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._running = False


if __name__ == "__main__":
    hb = CloudBrainHeartbeat(brain_url="")
    print("✅ heartbeat.py OK" if not hb.is_enabled() else "✅ heartbeat.py OK (enabled)")