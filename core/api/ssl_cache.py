"""Cache httpx's SSL context so creating an `httpx.AsyncClient` no longer costs ~300 ms of blocking CPU.

Measured 2026-09-27 on this machine: `httpx.AsyncClient(timeout=3)` takes 240-325 ms (every construction loads the certifi CA bundle into a new
SSLContext) and 0-1 ms with `verify=False`. The API builds a client per request in about twenty places (/status, /health/system,
/inference/stats, /media, /mining, the websocket helper, ...) and the HUD polls them every few seconds, so this was a constant
GIL-holding tax on the one event loop that also runs the autonomous loop.

`install()` wraps httpx's own `create_ssl_context` with an LRU cache keyed on its arguments, so the first client pays and the rest share
the context. It is transparent to callers and to tests that replace `httpx.AsyncClient`. Idempotent.
"""
from __future__ import annotations

__all__ = ["install", "installed"]

import functools

_INSTALLED = False


def installed() -> bool:
    return _INSTALLED


def install() -> bool:
    """Returns True if the cache is active after the call."""
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        import httpx._transports.default as transport

        original = transport.create_ssl_context

        @functools.lru_cache(maxsize=16)
        def _cached(verify=True, cert=None, trust_env=True):
            return original(verify=verify, cert=cert, trust_env=trust_env)

        @functools.wraps(original)
        def create_ssl_context(verify=True, cert=None, trust_env=True):
            try:
                return _cached(verify, cert, trust_env)
            except TypeError:                       # an unhashable argument: fall back to the uncached call
                return original(verify=verify, cert=cert, trust_env=trust_env)

        transport.create_ssl_context = create_ssl_context
        _INSTALLED = True
    except Exception:  # noqa: BLE001 -- an httpx internals change must never stop the API from starting
        return False
    return True
