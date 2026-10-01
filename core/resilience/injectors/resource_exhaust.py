"""Resource exhaustion injector — CPU, RAM, disk pressure tests."""

from __future__ import annotations

import asyncio
import random
from typing import Any

from loguru import logger

from .base import FailureInjector


class ResourceExhaustInjector(FailureInjector):
    name = "resource_exhaust"
    description = "Exhaust system resources (RAM, CPU, disk) to test graceful degradation"
    risk_level = "high"

    def __init__(self):
        self._allocations: list[Any] = []
        self._attack_type: str | None = None

    async def verify_healthy(self) -> bool:
        try:
            import psutil
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(".")
            return mem.available > 1 * 1024**3 and disk.free > 2 * 1024**3
        except ImportError:
            return True

    async def inject(self) -> None:
        import time
        self._attack_type = random.choice(["ram", "cpu", "disk"])
        logger.warning("[Chaos] Injecting: {} exhaustion", self._attack_type)

        if self._attack_type == "ram":
            try:
                import psutil
                mem = psutil.virtual_memory()
                target_mb = int(mem.total * 0.6 / 1024 / 1024)
                chunk = bytearray(1024 * 1024)
                for _ in range(min(target_mb, 2000)):
                    self._allocations.append(bytearray(chunk))
                    if len(self._allocations) % 100 == 0:
                        await asyncio.sleep(0)
            except MemoryError:
                logger.debug("[Chaos] RAM exhaustion hit limit")

        elif self._attack_type == "cpu":
            import multiprocessing
            count = multiprocessing.cpu_count()
            self._allocations = []
            for _ in range(count):
                p = multiprocessing.Process(target=_burn_cpu, daemon=True)
                p.start()
                self._allocations.append(p)

        elif self._attack_type == "disk":
            import tempfile
            f = tempfile.NamedTemporaryFile(delete=False, suffix=".chaos")
            try:
                import psutil
                disk = psutil.disk_usage(".")
                target_mb = int(disk.free * 0.7 / 1024 / 1024)
                chunk = b"0" * 1024 * 1024
                for _ in range(min(target_mb, 5000)):
                    f.write(chunk)
                    if _ % 100 == 0:
                        f.flush()
                        await asyncio.sleep(0)
            except (OSError, PermissionError):
                logger.debug("[Chaos] Disk exhaustion hit limit")
            self._allocations.append(f)

    async def verify_recovery(self) -> tuple[bool, float]:
        import asyncio
        await self.cleanup()
        await asyncio.sleep(2)
        try:
            import psutil
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(".")
            ok = mem.available > 512 * 1024**2 and disk.free > 1 * 1024**3
            return ok, 2.0
        except ImportError:
            return True, 2.0

    async def cleanup(self) -> None:
        import os
        for alloc in self._allocations:
            try:
                if hasattr(alloc, "terminate"):
                    alloc.terminate()
                elif hasattr(alloc, "close"):
                    # NamedTemporaryFile(delete=False) -- close() alone
                    # leaves the (up to multi-GB) file on disk forever;
                    # must unlink it explicitly to actually free the space
                    # this injector just consumed.
                    name = getattr(alloc, "name", None)
                    alloc.close()
                    if name:
                        os.unlink(name)
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        self._allocations.clear()
        import gc
        gc.collect()
        logger.info("[Chaos] Cleaned up resource exhaustion")


def _burn_cpu() -> None:
    while True:
        _ = [i**2 for i in range(10000)]
