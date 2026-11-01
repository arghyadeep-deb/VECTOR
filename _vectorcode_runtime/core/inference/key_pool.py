"""
VECTOR API key pool — round-robin rotation across multiple keys per provider.

Lets the owner give several keys for one provider to multiply throughput:
    GEMINI_API_KEY=key1,key2,key3

A KeyPool hands out keys round-robin and temporarily benches a key that
returns 429/401 so the next request skips it. Single-key envs are just a
pool of size 1 — fully backward compatible.

Usage:
    pool = get_pool("GEMINI_API_KEY")
    key = pool.next_key()          # round-robin, skips benched keys
    pool.mark_failed(key)          # bench for cooldown_sec after 429/401
"""
from __future__ import annotations

__all__ = ["KeyPool", "get_pool", "reset_pools"]

import os
import threading
import time
from pathlib import Path

from loguru import logger

# Keys may live only in the repo .env — pydantic reads that file for CONFIG
# but never exports to os.environ, so providers saw system-wide keys (e.g.
# GROQ_API_KEY) while .env-only keys (e.g. GEMINI_API_KEY) were invisible.
# load_dotenv fills the gap; existing os.environ values are never overridden.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except Exception:
    logger.debug("[VECTOR][key_pool] .env preload skipped", exc_info=True)


class KeyPool:
    """Round-robin pool of API keys for one provider, with failure cooldown."""

    def __init__(self, keys: list[str], cooldown_sec: float = 300.0) -> None:
        self._keys = [k.strip() for k in keys if k and k.strip()]
        self._cooldown = cooldown_sec
        self._idx = 0
        self._benched: dict[str, float] = {}  # key -> unix ts when it becomes usable again
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return len(self._keys)

    def has_keys(self) -> bool:
        return bool(self._keys)

    def _available(self, now: float) -> list[str]:
        return [k for k in self._keys if self._benched.get(k, 0.0) <= now]

    def next_key(self) -> str:
        """Return the next usable key (round-robin), or '' if the pool is empty.
        If every key is benched, returns the soonest-to-recover key anyway."""
        with self._lock:
            if not self._keys:
                return ""
            now = time.time()
            usable = self._available(now)
            if not usable:
                # all benched — fall back to the one recovering soonest
                return min(self._keys, key=lambda k: self._benched.get(k, 0.0))
            key = usable[self._idx % len(usable)]
            self._idx = (self._idx + 1) % len(usable)
            return key

    def mark_failed(self, key: str, cooldown_sec: float | None = None) -> None:
        """Bench a key after a rate-limit/auth failure so next_key() skips it."""
        if not key:
            return
        with self._lock:
            if key in self._keys:
                self._benched[key] = time.time() + (cooldown_sec or self._cooldown)
                logger.warning(
                    "[VECTOR][key_pool] benched a key for {:.0f}s ({} key(s) in pool)",
                    cooldown_sec or self._cooldown, len(self._keys),
                )


# ── Module registry: one pool per env var, built lazily from os.environ ──────

_pools: dict[str, KeyPool] = {}
_registry_lock = threading.Lock()


def get_pool(env_var: str) -> KeyPool:
    """Lazily build (and cache) the KeyPool for an env var. Comma-splits the value."""
    with _registry_lock:
        pool = _pools.get(env_var)
        if pool is None:
            raw = os.getenv(env_var, "")
            keys = raw.split(",") if raw else []
            pool = KeyPool(keys)
            _pools[env_var] = pool
        return pool


def reset_pools() -> None:
    """Drop cached pools (used by tests after mutating env vars)."""
    with _registry_lock:
        _pools.clear()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    os.environ["TEST_POOL_KEY"] = "alpha,beta,gamma"
    reset_pools()
    p = get_pool("TEST_POOL_KEY")
    assert p.size == 3, p.size
    seq = [p.next_key() for _ in range(4)]
    assert seq == ["alpha", "beta", "gamma", "alpha"], seq

    p.mark_failed("beta")
    seq2 = [p.next_key() for _ in range(4)]
    assert "beta" not in seq2, seq2  # benched key skipped

    os.environ["TEST_SINGLE"] = "solo"
    reset_pools()
    s = get_pool("TEST_SINGLE")
    assert s.next_key() == "solo" and s.next_key() == "solo"

    empty = get_pool("TEST_NONEXISTENT_ENV")
    assert not empty.has_keys() and empty.next_key() == ""

    print("OK key_pool.py — round-robin, cooldown skip, single-key, empty all pass")
