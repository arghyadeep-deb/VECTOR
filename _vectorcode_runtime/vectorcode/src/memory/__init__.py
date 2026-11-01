"""VectorCode memory package — FAISS index, pattern store, auto-bridge, provider, manager."""

from .provider import MemoryProvider, VectorBuiltinMemoryProvider
from .manager import MemoryManager, get_memory_manager, reset_memory_manager

__all__ = [
    "MemoryProvider",
    "VectorBuiltinMemoryProvider",
    "MemoryManager",
    "get_memory_manager",
    "reset_memory_manager",
]
