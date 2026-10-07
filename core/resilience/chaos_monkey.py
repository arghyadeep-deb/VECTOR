"""Scheduled chaos engineering engine — inject failures, verify recovery, report."""

from __future__ import annotations

import asyncio
import random
from typing import Any

from loguru import logger

from core.config import CONFIG
from core.resilience.injectors.base import ChaosExperiment, FailureInjector
from core.resilience.injectors.dependency_failure import DependencyFailureInjector
from core.resilience.injectors.network_chaos import NetworkChaosInjector
from core.resilience.injectors.process_kill import ProcessKillInjector
from core.resilience.injectors.resource_exhaust import ResourceExhaustInjector


class ChaosMonkey:
    def __init__(self):
        config = CONFIG.get("resilience", {}).get("chaos", {})
        self.enabled = config.get("enabled", False)
        self.schedule_interval_h = config.get("schedule_interval_h", 24)
        self._running = False
        self.results: list[ChaosExperiment] = []
        self.injectors: list[FailureInjector] = [
            ProcessKillInjector(),
            NetworkChaosInjector(),
            ResourceExhaustInjector(),
            DependencyFailureInjector(),
        ]
        self._on_result: list[callable] = []

    async def run_experiment(self, injector: FailureInjector) -> ChaosExperiment | None:
        if not self.enabled:
            logger.info("[ChaosMonkey] disabled — skipping experiment")
            return None
        logger.info("[ChaosMonkey] Running: {} ({})", injector.name, injector.description)
        result = await injector.run()
        self.results.append(result)
        for cb in self._on_result:
            try:
                cb(result)
            except Exception as e:
                logger.debug("[ChaosMonkey] callback error: {}", e)
        status = "PASSED" if result.passed else "FAILED"
        logger.info("[ChaosMonkey] {}: {} (recovery={:.1f}s)", status, injector.name, result.recovery_time_s)
        return result

    async def run_random_experiment(self) -> ChaosExperiment | None:
        if not self.enabled:
            logger.info("[ChaosMonkey] disabled — skipping random experiment")
            return None
        injector = random.choice(self.injectors)
        return await self.run_experiment(injector)

    async def run_all_experiments(self) -> list[ChaosExperiment]:
        if not self.enabled:
            logger.info("[ChaosMonkey] disabled — skipping all experiments")
            return []
        results = []
        for injector in self.injectors:
            result = await self.run_experiment(injector)
            results.append(result)
            await asyncio.sleep(2)
        return results

    async def run_scheduled(self) -> None:
        if not self.enabled:
            logger.info("[ChaosMonkey] disabled — skipping scheduled run")
            return
        logger.info("[ChaosMonkey] Starting scheduled run ({}h interval)", self.schedule_interval_h)
        await self.run_all_experiments()
        report = self.generate_report()
        logger.info("[ChaosMonkey] Scheduled run complete:\n{}", report)

    def generate_report(self) -> str:
        if not self.results:
            return "No chaos experiments run yet."
        lines = ["# Chaos Monkey Report", ""]
        passed = sum(1 for r in self.results if r.passed)
        lines.append(f"**Pass rate:** {passed}/{len(self.results)} ({passed/len(self.results)*100:.0f}%)")
        lines.append("")
        for r in self.results:
            status = "✅" if r.passed else "❌"
            lines.append(f"{status} **{r.injector_name}**: recovery={r.recovery_time_s:.1f}s")
            if r.error:
                lines.append(f"   Error: {r.error}")
        lines.append("")
        avg_recovery = sum(r.recovery_time_s for r in self.results if r.passed) / max(passed, 1)
        lines.append(f"Average recovery time: {avg_recovery:.1f}s")
        return "\n".join(lines)

    def on_result(self, callback: callable) -> None:
        self._on_result.append(callback)
