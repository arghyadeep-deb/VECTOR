"""Network failure injector — blocks ports, adds latency, drops packets."""

from __future__ import annotations

import random
import sys
from typing import Any

from loguru import logger

from .base import FailureInjector
import asyncio


class NetworkChaosInjector(FailureInjector):
    name = "network_chaos"
    description = "Block critical ports or add network latency to test circuit breakers"
    risk_level = "medium"

    def __init__(self):
        self._target_port: int | None = None
        self._is_windows = sys.platform == "win32"

    async def verify_healthy(self) -> bool:
        import httpx
        try:
            # module-level httpx.get() is SYNC -- `await`-ing it raised
            # TypeError on every call, so this always reported unhealthy
            # and run() (base.py) aborted before ever injecting chaos.
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get("http://127.0.0.1:11434/api/tags")
            return r.status_code == 200
        except Exception:
            return False

    async def inject(self) -> None:
        self._target_port = random.choice([11434, 8000, 9001])
        logger.warning("[Chaos] Injecting: block port {}", self._target_port)
        try:
            import subprocess
            if self._is_windows:
                (await asyncio.to_thread(subprocess.run, ["netsh", "advfirewall", "firewall", "add", "rule",
                     f"name=chaos_block_{self._target_port}",
                     "dir=in", "action=block",
                     f"protocol=tcp", f"localport={self._target_port}"],
                    capture_output=True, timeout=10,
                ))
            else:
                (await asyncio.to_thread(subprocess.run, ["iptables", "-A", "INPUT", "-p", "tcp",
                     f"--dport={self._target_port}", "-j", "DROP"],
                    capture_output=True, timeout=5,
                ))
        except Exception as e:
            logger.debug("[Chaos] network inject failed: {}", e)

    async def verify_recovery(self) -> tuple[bool, float]:
        import asyncio
        import httpx
        for attempt in range(10):
            await asyncio.sleep(3)
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    r = await client.get("http://127.0.0.1:11434/api/tags")
                if r.status_code == 200:
                    return True, attempt * 3 + 3
            except Exception:
                continue
        return False, 30.0

    async def cleanup(self) -> None:
        if not self._target_port:
            return
        logger.info("[Chaos] Cleaning up: unblock port {}", self._target_port)
        try:
            import subprocess
            if self._is_windows:
                (await asyncio.to_thread(subprocess.run, ["netsh", "advfirewall", "firewall", "delete", "rule",
                     f"name=chaos_block_{self._target_port}"],
                    capture_output=True, timeout=10,
                ))
            else:
                (await asyncio.to_thread(subprocess.run, ["iptables", "-D", "INPUT", "-p", "tcp",
                     f"--dport={self._target_port}", "-j", "DROP"],
                    capture_output=True, timeout=5,
                ))
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        self._target_port = None
