"""Compatibility shim for canonical storage backend types."""

from vectorcode.src.vc_tools.storage._abc import MemoryBackend, RetrievalResult

__all__ = ["MemoryBackend", "RetrievalResult"]
