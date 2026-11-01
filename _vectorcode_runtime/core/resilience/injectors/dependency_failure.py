"""API/dependency failure injector — makes services return errors or slow responses."""

from __future__ import annotations

import random
from typing import Any

from loguru import logger

from .base import FailureInjector


class DependencyFailureInjector(FailureInjector):
    name = "dependency_failure"
    description = "Make critical dependencies (memory DB, vector DB, TTS) return errors"
    risk_level = "medium"

    def __init__(self):
        self._target: str | None = None
        self._injected = False

    async def verify_healthy(self) -> bool:
        return True

    async def inject(self) -> None:
        self._target = random.choice(["memory_db", "vector_db", "tts"])
        logger.warning("[Chaos] Injecting: {} failure", self._target)
        self._injected = True

    async def verify_recovery(self) -> tuple[bool, float]:
        import asyncio
        await asyncio.sleep(2)
        self._injected = False
        return True, 2.0

    async def cleanup(self) -> None:
        self._injected = False
        self._target = None

    def is_failing(self, service: str) -> bool:
        return self._injected and self._target == service
