"""Thin re-export for backwards compatibility.

Canonical MemoryProvider lives in vectorcode.src.memory.provider.
This module exists only so legacy imports still resolve.
"""
from vectorcode.src.memory.provider import (
    MemoryProvider,
    VectorBuiltinMemoryProvider,
    _extract_learnings,
)

__all__ = ["MemoryProvider", "VectorBuiltinMemoryProvider", "_extract_learnings"]
