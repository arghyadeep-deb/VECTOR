"""Engine stub types."""
from __future__ import annotations
from typing import Any, AsyncIterator, Dict, List

class InferenceEngine:
    """Abstract inference engine."""
    async def generate(self, messages: List[Dict], **kw: Any) -> Dict[str, Any]:
        raise NotImplementedError
    async def stream(self, messages: List[Dict], **kw: Any) -> AsyncIterator[str]:
        raise NotImplementedError
    async def stream_full(self, messages: List[Dict], **kw: Any) -> AsyncIterator[Any]:
        raise NotImplementedError
