"""Compatibility adapters for canonical storage chunking utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from vectorcode.src.vc_tools.storage.chunking import (
    Chunk,
    ChunkConfig as CanonicalChunkConfig,
    chunk_text as _chunk_text,
)


@dataclass
class ChunkConfig:
    size: int = 512
    overlap: int = 64

    def to_canonical(self) -> CanonicalChunkConfig:
        return CanonicalChunkConfig(
            chunk_size=self.size,
            chunk_overlap=self.overlap,
            min_chunk_size=1,
        )


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
    """Split text into overlapping chunks, preserving the legacy list[str] API."""
    config = CanonicalChunkConfig(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        min_chunk_size=1,
    )
    return [chunk.content for chunk in _chunk_text(text, config=config)]


__all__ = ["Chunk", "ChunkConfig", "chunk_text"]
