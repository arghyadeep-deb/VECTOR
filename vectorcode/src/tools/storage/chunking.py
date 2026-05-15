"""Text chunking utilities."""
from __future__ import annotations
from typing import List

def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
    """Split text into overlapping chunks."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks
from dataclasses import dataclass
@dataclass
class ChunkConfig:
    size: int = 512
    overlap: int = 64

