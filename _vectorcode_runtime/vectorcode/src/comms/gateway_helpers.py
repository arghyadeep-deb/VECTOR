"""Gateway helpers — deduplication, markdown stripping, thread tracking."""

import re
import time
from typing import Optional

class MessageDeduplicator:
    """TTL-based message deduplication cache."""
    def __init__(self, max_size: int = 2000, ttl: float = 300):
        self._seen: dict[str, float] = {}
        self._max_size = max_size
        self._ttl = ttl

    def is_duplicate(self, msg_id: str) -> bool:
        if not msg_id: return False
        now = time.time()
        if msg_id in self._seen:
            if now - self._seen[msg_id] < self._ttl: return True
            del self._seen[msg_id]
        self._seen[msg_id] = now
        if len(self._seen) > self._max_size:
            cutoff = now - self._ttl
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
            while len(self._seen) > self._max_size:
                oldest = min(self._seen, key=self._seen.__getitem__)
                del self._seen[oldest]
        return False

def strip_markdown(text: str) -> str:
    """Strip markdown formatting for plain-text platforms."""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()
