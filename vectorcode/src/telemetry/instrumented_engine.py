"""Instrumented engine wrapper."""
from __future__ import annotations
from typing import Any

class InstrumentedEngine:
    """Wraps an inference engine with telemetry collection."""
    def __init__(self, engine: Any, session_id: str = "") -> None:
        self._engine = engine
        self.session_id = session_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)
