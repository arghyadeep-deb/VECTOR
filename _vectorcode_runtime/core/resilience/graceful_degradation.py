"""Detect resource constraints and degrade functionality gracefully rather than crashing."""

from __future__ import annotations

__all__ = [
    "GracefulDegradation",
    "ServiceTier",
]


import time
from enum import IntEnum
from typing import Any

from loguru import logger

from core.config import CONFIG


class ServiceTier(IntEnum):
    FULL = 5
    REDUCED = 4
    DEGRADED = 3
    MINIMAL = 2
    EMERGENCY = 1
    SURVIVAL = 0


class GracefulDegradation:
    def __init__(self):
        self.current_tier = ServiceTier.FULL
        self._last_tier_change = 0.0
        self._cooldown_sec = CONFIG.get("resilience", {}).get("degradation_cooldown_sec", 60.0)
        self._capabilities: dict[str, bool] = {}
        self._on_change_callbacks: list[callable] = []

    async def evaluate_tier(self) -> ServiceTier:
        gpu_ok = await self._check_gpu()
        ram_ok = await self._check_ram()
        disk_ok = await self._check_disk()
        network_ok = await self._check_network()
        ollama_ok = await self._check_ollama()

        self._capabilities = {
            "gpu_inference": gpu_ok,
            "streaming_tts": gpu_ok and ram_ok,
            "speaker_id": gpu_ok,
            "research_web": network_ok,
            "paper_search": network_ok,
            "voice_pipeline": ollama_ok and ram_ok,
            "memory_writes": disk_ok,
            "full_inference": ollama_ok,
        }

        if not ollama_ok and not network_ok and not ram_ok:
            return ServiceTier.SURVIVAL
        if not ollama_ok and not network_ok:
            return ServiceTier.EMERGENCY
        if not ollama_ok and not ram_ok:
            return ServiceTier.MINIMAL
        if not gpu_ok and not ram_ok:
            return ServiceTier.DEGRADED
        if not gpu_ok or not ram_ok:
            return ServiceTier.REDUCED

        return ServiceTier.FULL

    async def auto_degrade(self) -> ServiceTier | None:
        if time.time() - self._last_tier_change < self._cooldown_sec:
            return None
        new_tier = await self.evaluate_tier()
        if new_tier < self.current_tier:
            old = self.current_tier
            self.current_tier = new_tier
            self._last_tier_change = time.time()
            logger.warning("[GracefulDegradation] {} → {}", old.name, new_tier.name)
            self._notify_change(old, new_tier)
            return new_tier
        return None

    async def auto_escalate(self) -> ServiceTier | None:
        if time.time() - self._last_tier_change < self._cooldown_sec:
            return None
        new_tier = await self.evaluate_tier()
        if new_tier > self.current_tier:
            old = self.current_tier
            self.current_tier = new_tier
            self._last_tier_change = time.time()
            logger.info("[GracefulDegradation] {} → {}", old.name, new_tier.name)
            self._notify_change(old, new_tier)
            return new_tier
        return None

    def get_available_services(self) -> dict[str, bool]:
        return dict(self._capabilities)

    def get_service_limits(self, service: str) -> dict:
        limits = {
            "batch_size": {5: 8, 4: 4, 3: 2, 2: 1, 1: 1, 0: 0},
            "model_size": {5: "full", 4: "full", 3: "medium", 2: "small", 1: "tiny", 0: "none"},
            "timeout_sec": {5: 30, 4: 60, 3: 120, 2: 300, 1: 600, 0: 0},
        }
        tier = int(self.current_tier)
        return {k: v.get(tier, v[0]) for k, v in limits.items()}

    def on_change(self, callback: callable) -> None:
        self._on_change_callbacks.append(callback)

    def _notify_change(self, old: ServiceTier, new: ServiceTier) -> None:
        for cb in self._on_change_callbacks:
            try:
                cb(old, new)
            except Exception as e:
                logger.debug("[GracefulDegradation] callback error: {}", e)

    async def _check_gpu(self) -> bool:
        try:
            import torch
            if torch.cuda.is_available():
                free, total = torch.cuda.mem_get_info(0)
                free_gb = free / 1024**3
                return free_gb > 1.0
            return False
        except ImportError:
            return True

    async def _check_ram(self) -> bool:
        try:
            import psutil
            mem = psutil.virtual_memory()
            return mem.available > 512 * 1024 * 1024
        except ImportError:
            return True

    async def _check_disk(self) -> bool:
        try:
            import psutil
            disk = psutil.disk_usage(".")
            return disk.free > 512 * 1024 * 1024
        except ImportError:
            return True

    async def _check_network(self) -> bool:
        # NOTE: `await httpx.get(...)` was invalid (module-level get is SYNC) —
        # it raised TypeError on every call, so this check returned False
        # forever and pinned the whole brain at EMERGENCY/SURVIVAL tier.
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                # gstatic's connectivity-check endpoint (204, no redirects) —
                # the same probe Android uses; https://1.1.1.1 failed TLS here
                r = await client.get("http://www.gstatic.com/generate_204")
                return r.status_code < 500  # any answer = network up
        except Exception:
            return False

    async def _check_ollama(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{CONFIG['ollama_host']}/api/tags")
                return r.status_code == 200
        except Exception:
            return False
