"""Thin re-export for backwards compatibility.

Canonical MemoryManager lives in vectorcode.src.memory.manager.
This module exists only so legacy imports still resolve.
"""
from vectorcode.src.memory.manager import (
    MemoryManager,
    StreamingContextScrubber,
    build_memory_context_block,
    sanitize_context,
    get_memory_manager,
    reset_memory_manager,
)

__all__ = [
    "MemoryManager",
    "StreamingContextScrubber",
    "build_memory_context_block",
    "sanitize_context",
    "get_memory_manager",
    "reset_memory_manager",
]
