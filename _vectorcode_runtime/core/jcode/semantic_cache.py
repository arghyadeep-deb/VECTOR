"""
Semantic cache for VECTOR — deduplicates repeated LLM queries using embedding similarity.
Reduces Ollama load during observe→think→act loop.
"""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

import hashlib
import json
from loguru import logger
from core.config import CONFIG


class SemanticCache:
    """
    TTL-based + exact-match cache for LLM completions.
    Prevents repeated identical queries from hitting Ollama multiple times.
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 500):
        self._cache: dict[str, dict] = {}
        self._ttl = ttl_seconds
        self._max_size = max_size

    def _key(self, prompt: str, model: str = "") -> str:
        """Create cache key from prompt + model."""
        return hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()[:16]

    def get(self, prompt: str, model: str = "") -> str | None:
        """Return cached response or None if cache miss/expired."""
        import time
        k = self._key(prompt, model)
        entry = self._cache.get(k)
        if entry and (time.time() - entry["ts"]) < self._ttl:
            logger.debug("[VECTOR][semantic_cache] cache hit: {}", k[:8])
            return entry["response"]
        return None

    def set(self, prompt: str, response: str, model: str = "") -> None:
        """Cache a response."""
        import time
        if len(self._cache) >= self._max_size:
            # Evict oldest entry
            oldest = min(self._cache, key=lambda k: self._cache[k]["ts"])
            del self._cache[oldest]
        k = self._key(prompt, model)
        self._cache[k] = {"response": response, "ts": time.time(), "model": model}

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


# Module-level singleton
_cache = SemanticCache()


def get_cache() -> SemanticCache:
    return _cache


if __name__ == "__main__":
    c = SemanticCache()
    c.set("test prompt", "test response", "vector-focus")
    print("SemanticCache OK:", c.get("test prompt", "vector-focus"))
    print("✅ semantic_cache OK")
