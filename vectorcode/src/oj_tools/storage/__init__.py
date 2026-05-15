# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/tools/storage/__init__.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Storage primitive — persistent searchable storage."""

from __future__ import annotations

# Always-available backend
import vectorcode.src.oj_tools.storage.sqlite  # noqa: F401

# Optional backends — import to trigger registration
try:
    import vector.tools.storage.bm25  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.storage.faiss_backend  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.storage.colbert_backend  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.storage.hybrid  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.storage.dense  # noqa: F401
except ImportError:
    pass

from vectorcode.src.oj_tools.storage._stubs import MemoryBackend, RetrievalResult
from vectorcode.src.oj_tools.storage.chunking import Chunk, ChunkConfig, chunk_text
from vectorcode.src.oj_tools.storage.context import ContextConfig, inject_context
from vectorcode.src.oj_tools.storage.ingest import ingest_path, read_document

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
