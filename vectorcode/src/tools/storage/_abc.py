"""Tool storage stub types."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List, Optional

@dataclass
class RetrievalResult:
    content: str = ""
    score: float = 0.0
    metadata: Optional[Any] = None

class MemoryBackend:
    """Abstract memory backend."""
    def store(self, key: str, value: str) -> str: raise NotImplementedError
    def retrieve(self, query: str, k: int = 5) -> List[RetrievalResult]: raise NotImplementedError
    def delete(self, key: str) -> bool: raise NotImplementedError
