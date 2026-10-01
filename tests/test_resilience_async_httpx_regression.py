"""Regression tests for the `await httpx.get/post(...)` anti-pattern found
repeatedly across core/resilience during the Phase 3 audit (2026-10-01).

httpx's module-level get()/post()/etc. are SYNCHRONOUS convenience
functions, not coroutines. `await httpx.get(...)` raises TypeError on every
real call, which every call site here caught with a bare `except Exception`
and treated as "endpoint unreachable" / "unhealthy" -- so these resilience
primitives never actually worked:
  - HotFailover.send_heartbeat() never delivered a heartbeat to the
    secondary (always returned False).
  - NetworkChaosInjector.verify_healthy() always reported unhealthy, so
    FailureInjector.run() (injectors/base.py) aborted before injecting any
    chaos -- the network chaos experiment never ran.
  - NetworkChaosInjector.verify_recovery() always reported recovery failed.
  - ModelCrashPlaybook.run()/NetworkPartitionPlaybook.run() in
    recovery_playbooks.py always fell into their failure branch.

Existing tests mocked `httpx.post`/`httpx.get` directly as AsyncMock, which
masked the bug (the mock made `await` valid even though real httpx doesn't
support that call shape). These tests instead mock `httpx.AsyncClient`,
matching how the fixed code actually calls httpx.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.resilience.hot_failover import HotFailover
from core.resilience.injectors.network_chaos import NetworkChaosInjector


def _mock_async_client(status_code=200):
    mock_response = AsyncMock()
    mock_response.status_code = status_code
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = False
    return mock_cm, mock_client


@pytest.mark.asyncio
async def test_send_heartbeat_uses_async_client_and_succeeds_on_200():
    hf = HotFailover(is_primary=True)
    await hf.start_primary()
    mock_cm, mock_client = _mock_async_client(status_code=200)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        sent = await hf.send_heartbeat()
    assert sent is True
    mock_client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_heartbeat_false_on_non_200():
    hf = HotFailover(is_primary=True)
    await hf.start_primary()
    mock_cm, _ = _mock_async_client(status_code=503)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        sent = await hf.send_heartbeat()
    assert sent is False


@pytest.mark.asyncio
async def test_network_chaos_verify_healthy_true_on_200():
    injector = NetworkChaosInjector()
    mock_cm, _ = _mock_async_client(status_code=200)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        healthy = await injector.verify_healthy()
    assert healthy is True


@pytest.mark.asyncio
async def test_network_chaos_verify_healthy_false_when_unreachable():
    injector = NetworkChaosInjector()
    with patch("httpx.AsyncClient", side_effect=OSError("connection refused")):
        healthy = await injector.verify_healthy()
    assert healthy is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
