"""
VECTOR Smart Routing — Request Deduplication + Response Cache
Python port of ClawRouter/src/dedup.ts + src/response-cache.ts

SHA-256 based request deduplication and 30-second response TTL cache.
Prevents duplicate API calls in agent loops and saves credits on repeated prompts.

Usage:
    cache = RequestCache()
    key = cache.cache_key(messages, model="gpt-4o")
    hit = await cache.get(key)
    if hit:
        return hit
    response = await call_llm(...)
    await cache.set(key, response)
"""
from __future__ import annotations

__all__ = [
    "CacheEntry",
    "get_cache",
    "RequestCache",
]


import asyncio
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

_DEFAULT_TTL_SECONDS = 30.0


@dataclass
class CacheEntry:
    response: dict
    created_at: float
    hits: int = 0


class RequestCache:
    """
    SHA-256 request deduplication + TTL response cache.
    Thread-safe with asyncio.Lock. Module-level singleton via get_cache().

    Prevents double API calls when:
    - Agent loop retries same prompt
    - Multiple concurrent agents send same request
    - Timeout retry logic resends identical request
    """

    def __init__(self, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, CacheEntry] = {}
        self._inflight: dict[str, asyncio.Event] = {}
        self._inflight_results: dict[str, dict | None] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    def cache_key(
        self,
        messages: list[dict],
        model: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        SHA-256 hash of (model + messages + relevant params).
        Excludes non-deterministic params like timestamps.
        """
        payload = {
            "model":       model,
            "messages":    messages,
            "temperature": temperature,
            "max_tokens":  max_tokens,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, key: str) -> dict | None:
        """Return cached response if within TTL, else None."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            age = time.time() - entry.created_at
            if age > self._ttl:
                del self._store[key]
                self._misses += 1
                return None
            entry.hits += 1
            self._hits += 1
            logger.debug("[VECTOR][request_cache] hit key={}... age={:.1f}s", key[:12], age)
            return entry.response

    async def set(self, key: str, response: dict) -> None:
        """Cache a response with current timestamp."""
        async with self._lock:
            self._store[key] = CacheEntry(response=response, created_at=time.time())
            # Notify any waiters
            if key in self._inflight:
                self._inflight_results[key] = response
                self._inflight[key].set()

    async def mark_inflight(self, key: str) -> None:
        """Mark a request as in-flight (being processed)."""
        async with self._lock:
            if key not in self._inflight:
                self._inflight[key] = asyncio.Event()

    async def wait_for_inflight(self, key: str, timeout: float = 60.0) -> dict | None:
        """
        If the same request is already in-flight, wait for its result.
        Returns the response or None on timeout.
        """
        event = self._inflight.get(key)
        if not event:
            return None
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._inflight_results.get(key)
        except asyncio.TimeoutError:
            return None

    async def clear_inflight(self, key: str) -> None:
        """Remove from in-flight tracking (call after set() or on error)."""
        async with self._lock:
            self._inflight.pop(key, None)
            self._inflight_results.pop(key, None)

    def invalidate_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v.created_at > self._ttl]
        for k in expired:
            del self._store[k]
        return len(expired)

    def stats(self) -> dict:
        """Return cache statistics."""
        return {
            "entries":  len(self._store),
            "inflight": len(self._inflight),
            "hits":     self._hits,
            "misses":   self._misses,
            "hit_rate": self._hits / max(self._hits + self._misses, 1),
            "ttl_sec":  self._ttl,
        }

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()
        self._inflight.clear()
        self._inflight_results.clear()


# Module-level singleton
_global_cache: RequestCache | None = None


def get_cache() -> RequestCache:
    global _global_cache
    if _global_cache is None:
        _global_cache = RequestCache()
    return _global_cache


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        cache = RequestCache(ttl_seconds=5.0)

        msgs = [{"role": "user", "content": "hello"}]
        key = cache.cache_key(msgs, model="gpt-4o")

        # Cache miss
        hit = await cache.get(key)
        assert hit is None

        # Set and get
        fake_response = {"choices": [{"message": {"content": "hi"}}]}
        await cache.set(key, fake_response)
        hit = await cache.get(key)
        assert hit == fake_response

        # TTL expiry
        import asyncio
        await asyncio.sleep(6)
        hit = await cache.get(key)
        assert hit is None

        st = cache.stats()
        assert st["hits"] == 1
        assert st["misses"] == 2

        print(f"OK request_cache.py — SHA-256 dedup + {cache._ttl}s TTL cache")
        print(f"  hit_rate={st['hit_rate']:.0%} hits={st['hits']} misses={st['misses']}")

    asyncio.run(_smoke())
