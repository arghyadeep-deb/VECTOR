"""
VECTOR API Cache — module-level TTL caches for expensive endpoint responses.
Reduces DB hits for dashboard polling.
"""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

import time
from typing import Any


class TTLCache:
    """Simple in-memory TTL cache for API responses."""

    def __init__(self, ttl: int = 30, name: str = ""):
        self._cache: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl
        self._name = name

    def get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry and time.time() - entry[1] < self._ttl:
            return entry[0]
        if entry:
            del self._cache[key]  # evict stale
        return None

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, time.time())

    def invalidate(self, key: str = None) -> None:
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


# Module-level caches — shared across all requests
agents_cache = TTLCache(ttl=10, name="agents")        # 10s: agent HP/status
memory_cache = TTLCache(ttl=5, name="memory")         # 5s: recent episodic events
security_cache = TTLCache(ttl=15, name="security")    # 15s: security scan results
goals_cache = TTLCache(ttl=30, name="goals")          # 30s: active goals
health_cache = TTLCache(ttl=3, name="health")         # 3s: CPU/GPU/memory
research_cache = TTLCache(ttl=60, name="research")    # 60s: search results per query


if __name__ == "__main__":
    c = TTLCache(ttl=5)
    c.set("test", {"value": 42})
    assert c.get("test") == {"value": 42}
    print("✅ cache.py OK")
