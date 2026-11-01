"""Growth Engine conductor — two never-die asyncio arms.

ARM A (content/brand) ticks on a daily cadence; ARM B (software factory) ticks
per validated market issue. Each arm is wrapped so an exception backs off and
retries but never kills the loop (``code_style.md`` never-die rule). The whole
engine is gated by ``CONFIG["growth"]["enabled"]`` (default False) — it idles
until the owner switches it on.

Integration: ``run_forever()`` is launched as a background task by the autonomous
loop when enabled. ``run_for(ticks=N)`` is the bounded runner used by tests.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

from core.config import CONFIG


class GrowthOrchestrator:
    """Runs ARM A + ARM B as independent never-die coroutines."""

    def __init__(self) -> None:
        self._backoff_s = 5.0
        # cadences (seconds); content daily, software polls for issues more often
        self._content_interval_s = 24 * 60 * 60
        self._software_interval_s = 30 * 60

    # ── public entry points ──────────────────────────────────────────
    async def run_forever(self) -> None:
        """Production loop — both arms forever. No-ops until growth is enabled."""
        if not CONFIG["growth"].get("enabled", False):
            logger.info("[VECTOR][growth] disabled (CONFIG.growth.enabled=False) — orchestrator idle")
            return
        logger.info("[VECTOR][growth] orchestrator starting (ARM A + ARM B)")
        await asyncio.gather(self._content_loop(), self._software_loop())

    async def run_for(self, ticks: int = 1) -> None:
        """Bounded runner (tests + manual): tick both arms ``ticks`` times,
        surviving any per-tick exception."""
        for _ in range(ticks):
            await self._safe_tick(self._content_tick)
            await self._safe_tick(self._software_tick)

    # ── never-die wrappers ───────────────────────────────────────────
    async def _safe_tick(self, tick) -> None:
        try:
            await tick()
        except Exception as exc:
            logger.error("[VECTOR][growth] tick error (loop survives): {}", exc)
            if self._backoff_s:
                await asyncio.sleep(self._backoff_s)

    async def _content_loop(self) -> None:
        while True:
            await self._safe_tick(self._content_tick)
            await asyncio.sleep(self._content_interval_s)

    async def _software_loop(self) -> None:
        while True:
            await self._safe_tick(self._software_tick)
            await asyncio.sleep(self._software_interval_s)

    # ── arm ticks ────────────────────────────────────────────────────
    async def _content_tick(self) -> None:
        from districts.growth.content_arm import ContentArm
        await ContentArm().run_once()

    async def _software_tick(self) -> None:
        issue = self._next_validated_issue()
        if not issue:
            return
        from districts.growth.software_arm import SoftwareArm
        await SoftwareArm().run_once(issue)

    def _next_validated_issue(self) -> "dict | None":
        """Ask market_scanner + idea_validator for a software-solvable issue."""
        try:
            from districts.startups.market_scanner import MarketScanner   # reuse
            from districts.startups.idea_validator import IdeaValidator   # reuse
            return None  # wired to real scan/validate output as the loop matures
        except Exception:
            return None


def get_orchestrator() -> GrowthOrchestrator:
    return GrowthOrchestrator()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(GrowthOrchestrator().run_for(ticks=1))
    print("growth_orchestrator OK")
