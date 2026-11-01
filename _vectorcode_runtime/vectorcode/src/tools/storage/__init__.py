"""Compatibility package for canonical ``vectorcode.src.vc_tools.storage``."""

from vectorcode.src.tools.storage._abc import MemoryBackend, RetrievalResult
from vectorcode.src.tools.storage.chunking import Chunk, ChunkConfig, chunk_text
from vectorcode.src.tools.storage.ingest import (
    DocumentMeta,
    detect_file_type,
    ingest_documents,
    ingest_path,
    read_document,
)

__all__ = [
    "Chunk",
    "ChunkConfig",
    "DocumentMeta",
    "MemoryBackend",
    "RetrievalResult",
    "chunk_text",
    "detect_file_type",
    "ingest_documents",
    "ingest_path",
    "read_document",
]
