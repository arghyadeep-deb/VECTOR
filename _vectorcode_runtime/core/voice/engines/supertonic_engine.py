"""Lazy optional Supertonic live-TTS adapter/benchmark seam."""
from __future__ import annotations

import time
from dataclasses import dataclass

__all__ = ["SupertonicConfig", "SupertonicEngine"]


@dataclass(frozen=True)
class SupertonicConfig:
    enabled: bool = False
    model_path: str = ""
    live_allowed: bool = False


class SupertonicEngine:
    def __init__(self, config: SupertonicConfig | None = None):
        self.config = config or SupertonicConfig()
        self._engine = None

    def available(self) -> bool:
        if not self.config.enabled:
            return False
        try:
            import supertonic  # noqa: F401
            return True
        except Exception:
            return False

    def synthesize(self, text: str, language: str = "en") -> dict:
        if not self.available():
            return {"status": "unavailable", "engine": "supertonic"}
        started = time.perf_counter()
        return {
            "status": "not_implemented_live",
            "engine": "supertonic",
            "language": language,
            "text_chars": len(text),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
