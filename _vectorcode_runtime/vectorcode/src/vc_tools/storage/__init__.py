# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Storage primitive — persistent searchable storage."""

from __future__ import annotations
from loguru import logger

# Always-available backend
import vectorcode.src.vc_tools.storage.sqlite  # noqa: F401

# Optional backends — import to trigger registration
try:
    import vectorcode.src.vc_tools.storage.bm25  # noqa: F401
except ImportError:
    logger.debug("[VECTOR] optional storage backend unavailable: bm25")

try:
    import vectorcode.src.vc_tools.storage.faiss_backend  # noqa: F401
except ImportError:
    logger.debug("[VECTOR] optional storage backend unavailable: faiss")

try:
    import vectorcode.src.vc_tools.storage.colbert_backend  # noqa: F401
except ImportError:
    logger.debug("[VECTOR] optional storage backend unavailable: colbert")

try:
    import vectorcode.src.vc_tools.storage.hybrid  # noqa: F401
except ImportError:
    logger.debug("[VECTOR] optional storage backend unavailable: hybrid")

try:
    import vectorcode.src.vc_tools.storage.dense  # noqa: F401
except ImportError:
    logger.debug("[VECTOR] optional storage backend unavailable: dense")

from vectorcode.src.vc_tools.storage._abc import MemoryBackend, RetrievalResult
from vectorcode.src.vc_tools.storage.chunking import Chunk, ChunkConfig, chunk_text
from vectorcode.src.vc_tools.storage.context import ContextConfig, inject_context
from vectorcode.src.vc_tools.storage.ingest import ingest_path, read_document

__all__ = [
    "Chunk",
    "ChunkConfig",
    "ContextConfig",
    "MemoryBackend",
    "RetrievalResult",
    "chunk_text",
    "inject_context",
    "ingest_path",
    "read_document",
]
