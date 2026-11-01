"""Compatibility adapters for canonical storage ingestion."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from vectorcode.src.vc_tools.storage.ingest import (
    DocumentMeta,
    detect_file_type,
    ingest_path as _ingest_path,
    read_document,
)
from vectorcode.src.vc_tools.storage.chunking import ChunkConfig


def ingest_path(path) -> int:
    """Ingest a path and return the number of chunks, preserving legacy API."""
    return len(_ingest_path(Path(path), config=ChunkConfig(min_chunk_size=1)))


def ingest_documents(paths: Iterable) -> int:
    """Ingest multiple paths and return the total chunk count."""
    return sum(ingest_path(path) for path in paths)


__all__ = [
    "DocumentMeta",
    "detect_file_type",
    "ingest_documents",
    "ingest_path",
    "read_document",
]
