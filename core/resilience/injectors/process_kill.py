"""Process termination injector — kills specific processes to test recovery."""

from __future__ import annotations

import random
from typing import Any

from loguru import logger

from .base import FailureInjector
import asyncio


class ProcessKillInjector(FailureInjector):
    name = "process_kill"
    description = "Kill a critical process (Ollama) and verify auto-restart"
    risk_level = "medium"

    def __init__(self):
        self._target: str | None = None
        # "voice_ws" used to map here to the bare image name "python" --
        # `taskkill /F /IM python` (no .exe) happened to silently fail to
        # match anything on Windows (the real image name is "python.exe"),
        # which is the ONLY reason this never did real damage. voice_ws is
        # an in-process FastAPI WebSocket route (core/api/routers/voice_ws.py),
        # not a separate OS process -- there is no isolated "voice worker" to
        # safely target here, and "python.exe" is not specific to it: every
        # VECTOR Python process (the autonomous loop, the API server this
        # injector itself may be running inside of) shares that same image
        # name, so a corrected ".exe" suffix would turn an accidental no-op
        # into `taskkill /F /IM python.exe` mass-killing all of them at once.
        self._targets = {
            "ollama": "ollama.exe",
        }

    async def verify_healthy(self) -> bool:
        return True

    async def inject(self) -> None:
        self._target = random.choice(list(self._targets.keys()))
        process_name = self._targets[self._target]
        logger.warning("[Chaos] Injecting: kill {}", process_name)
        try:
            import subprocess
            (await asyncio.to_thread(subprocess.run, ["taskkill", "/F", "/IM", process_name],
                capture_output=True, timeout=5,
            ))
        except Exception as e:
            logger.debug("[Chaos] kill failed: {}", e)

    async def verify_recovery(self) -> tuple[bool, float]:
        import asyncio
        import subprocess
        for attempt in range(15):
            await asyncio.sleep(2)
            try:
                result = (await asyncio.to_thread(subprocess.run, ["tasklist", "/FI", f"IMAGENAME eq {self._targets.get(self._target, '')}"],
                    capture_output=True, text=True, timeout=5,
                ))
                if self._targets.get(self._target, "") in result.stdout:
                    return True, attempt * 2 + 2
            except Exception:
                continue
        return False, 30.0

    async def cleanup(self) -> None:
        self._target = None
