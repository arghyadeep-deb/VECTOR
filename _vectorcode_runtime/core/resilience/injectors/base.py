"""Base class for all failure injectors."""

from __future__ import annotations

__all__ = [
    "ChaosExperiment",
    "FailureInjector",
]


from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChaosExperiment:
    injector_name: str = ""
    description: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    passed: bool = False
    recovery_time_s: float = 0.0
    error: str = ""
    details: dict = field(default_factory=dict)


class FailureInjector(ABC):
    name: str = "base"
    description: str = ""
    risk_level: str = "low"

    @abstractmethod
    async def verify_healthy(self) -> bool:
        ...

    @abstractmethod
    async def inject(self) -> None:
        ...

    @abstractmethod
    async def verify_recovery(self) -> tuple[bool, float]:
        ...

    @abstractmethod
    async def cleanup(self) -> None:
        ...

    async def run(self) -> ChaosExperiment:
        import time
        exp = ChaosExperiment(injector_name=self.name, description=self.description)
        exp.started_at = time.time()

        try:
            healthy = await self.verify_healthy()
            if not healthy:
                exp.error = "System not healthy before injection"
                exp.passed = False
                return exp

            await self.inject()

            import asyncio
            await asyncio.sleep(1)

            recovered, rec_time = await self.verify_recovery()
            exp.recovery_time_s = rec_time
            exp.passed = recovered
        except Exception as e:
            exp.error = str(e)
            exp.passed = False
        finally:
            await self.cleanup()
            exp.completed_at = time.time()

        return exp
