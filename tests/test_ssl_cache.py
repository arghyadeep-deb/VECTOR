"""Creating an httpx.AsyncClient must not cost ~300 ms of blocking CPU each time (found 2026-09-27; see core/api/ssl_cache.py)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio

import httpx
import pytest

from core.api import ssl_cache


def test_after_the_first_client_the_next_ones_are_nearly_free():
    assert ssl_cache.install() is True and ssl_cache.installed()
    asyncio.run(_make(1))                       # the first client pays for the CA bundle
    started = time.perf_counter()
    asyncio.run(_make(10))
    per_client_ms = (time.perf_counter() - started) * 1000 / 10
    assert per_client_ms < 40, f"{per_client_ms:.0f} ms per AsyncClient: the SSL context is not being shared"


async def _make(n):
    for _ in range(n):
        client = httpx.AsyncClient(timeout=3)
        await client.aclose()


def test_install_is_idempotent_and_the_context_is_shared():
    import httpx._transports.default as transport

    ssl_cache.install()
    fn = transport.create_ssl_context
    ssl_cache.install()
    assert transport.create_ssl_context is fn
    assert transport.create_ssl_context(True, None, True) is transport.create_ssl_context(True, None, True)


def test_verify_false_and_an_unhashable_argument_still_work():
    import httpx._transports.default as transport

    ssl_cache.install()
    assert transport.create_ssl_context(False, None, True) is not None
    assert transport.create_ssl_context(verify=True, cert=None, trust_env=True) is not None
    assert httpx.Client(verify=False) is not None


def test_cache_key_changes_when_a_configured_ca_file_changes(monkeypatch, tmp_path):
    ca = tmp_path / "ca.pem"
    ca.write_bytes(b"first")
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    first = ssl_cache._context_inputs(True, None, True)
    ca.write_bytes(b"replacement certificate data")
    second = ssl_cache._context_inputs(True, None, True)
    assert first != second


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
