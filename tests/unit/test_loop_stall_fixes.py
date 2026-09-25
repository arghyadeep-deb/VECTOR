"""KNOWN_ISSUES #0 — 'autonomous loop thread stops ticking after several
hours, /health stays 200' — regression tests for the 2026-08-06 root-cause
hunt fixes.

Confirmed root causes fixed here (see each fix's inline comment for the full
trace):

1. core/inference/vectorcode_llm.py::chat() — `with ThreadPoolExecutor() as
   pool:` made `.result(timeout=...)` a FAKE bound: leaving the `with` block
   (even via that same TimeoutError) ran shutdown(wait=True), which re-blocks
   the calling thread — routinely the single autonomous-loop event-loop
   thread, since ~112 district-agent call sites call this sync function
   directly from inside async run() with no `await`/`to_thread` — with NO
   timeout at all, for however long the orphaned background call takes.
2. core/loop/permission_gateway.py's `download_file` action — SSRFGuard(
   resolve_dns=True) called socket.getaddrinfo() synchronously with no
   timeout, directly on the calling coroutine's thread.
3. core/loop/autonomous_loop.py::reflect_loop() — _reflect_tick() had no
   asyncio.timeout coverage at all, unlike observe_tick (15s) and think_tick
   (60s).
4. core/city/governor.py::dispatch() — `await agent.run(task)` (the one call
   on the dispatch hot path reached by every real district task) had no
   timeout of its own.
5. districts/data_analytics/performance_benchmarker.py::run() — called
   several plain-sync, blocking-network benchmark_*() methods directly from
   an async governor-dispatched run(), freezing the event loop for the full
   call duration.

Uses the isolation pattern from tests/unit/test_memory_decay.py -- none of
these tests touch EpisodicMemory or any production DB (PermissionGateway's
__init__ and _execute_action's download_file branch never open the main
vector_memory.db; verified by reading the source directly).
"""
from __future__ import annotations

import asyncio
import time

import pytest

from core.config import CONFIG


pytestmark = pytest.mark.unit


# ── 1. vectorcode_llm.chat() ThreadPoolExecutor shutdown fix ───────────────

class TestVectorcodeLLMChatBounded:
    def test_chat_does_not_block_past_grace_window(self, monkeypatch):
        """A hung provider call must not block the caller past
        timeout + vc_llm_thread_grace_sec. Before the fix, the `with
        ThreadPoolExecutor() as pool:` form's shutdown(wait=True) re-blocked
        the caller for the FULL hang duration regardless of `.result(timeout=)`.
        """
        import core.inference.vectorcode_llm as vc_llm

        _HANG_SEC = 3.0

        async def _hang_forever(*_args, **_kwargs):
            await asyncio.sleep(_HANG_SEC)

            class _R:
                content = "should never be reached in this test"

            return _R()

        # Only the ProviderClient path is under test — make the legacy
        # fallback chain (only reached after ProviderClient fails/times out)
        # instant no-ops so it can't add its own delay to the measurement.
        monkeypatch.setattr(
            "core.inference.provider_client.ProviderClient.chat", _hang_forever
        )
        monkeypatch.setattr(vc_llm, "_try_gemini", lambda *a, **kw: "")
        monkeypatch.setattr(vc_llm, "_try_openrouter", lambda *a, **kw: "")
        monkeypatch.setattr(vc_llm, "_try_ollama", lambda *a, **kw: "")
        monkeypatch.setitem(CONFIG, "vc_llm_thread_grace_sec", 0.3)

        start = time.monotonic()
        result = vc_llm.chat(
            model="vector-fast",
            messages=[{"role": "user", "content": "ping"}],
            timeout=0.2,
        )
        elapsed = time.monotonic() - start

        assert result == ""  # never raises — all providers failed/timed out
        assert elapsed < _HANG_SEC / 2, (
            f"chat() blocked for {elapsed:.2f}s (hang was {_HANG_SEC}s) — "
            "ThreadPoolExecutor shutdown is re-blocking the caller again"
        )

    def test_grace_config_value_present_and_sane(self):
        assert isinstance(CONFIG.get("vc_llm_thread_grace_sec"), (int, float))
        assert 0.0 <= CONFIG["vc_llm_thread_grace_sec"] <= 120.0


# ── 2. permission_gateway download_file SSRF DNS timeout ───────────────────

class TestSSRFDNSResolutionBounded:
    async def test_download_file_bounded_on_dns_hang(self, monkeypatch):
        from core.loop.permission_gateway import PermissionGateway, Action
        import core.security.ssrf_guard as ssrf_guard

        _HANG_SEC = 3.0

        def _slow_getaddrinfo(*_args, **_kwargs):
            time.sleep(_HANG_SEC)
            return [(2, 1, 6, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(ssrf_guard.socket, "getaddrinfo", _slow_getaddrinfo)
        monkeypatch.setitem(CONFIG, "ssrf_dns_resolve_timeout_sec", 0.3)

        gw = PermissionGateway()
        action = Action(
            action_type="download_file",
            params={"url": "http://example.invalid/file.bin"},
            proposed_by="test_agent",
        )

        start = time.monotonic()
        result = await gw._execute_action(action)
        elapsed = time.monotonic() - start

        assert result["status"] == "error"
        assert "timed out" in result["error"].lower()
        assert elapsed < _HANG_SEC / 2, (
            f"_execute_action blocked for {elapsed:.2f}s on a hung DNS "
            f"resolver (hang was {_HANG_SEC}s) — the loop thread would "
            "freeze for the same duration in production"
        )

    def test_ssrf_dns_timeout_config_value_present_and_sane(self):
        assert isinstance(CONFIG.get("ssrf_dns_resolve_timeout_sec"), (int, float))
        assert 0.5 <= CONFIG["ssrf_dns_resolve_timeout_sec"] <= 30.0


# ── 3. autonomous_loop reflect_tick timeout coverage ────────────────────────

class TestReflectTickTimeoutCoverage:
    async def test_reflect_tick_hang_is_bounded_by_configured_timeout(self, monkeypatch):
        """Reproduces exactly what reflect_loop() now does: wrap
        _reflect_tick() in asyncio.timeout(reflect_tick_timeout_sec)."""
        from core.loop.autonomous_loop import AutonomousLoop

        _HANG_SEC = 3.0
        monkeypatch.setitem(CONFIG["loop"], "reflect_tick_timeout_sec", 0.3)

        loop = AutonomousLoop()

        async def _hang(*_a, **_kw):
            await asyncio.sleep(_HANG_SEC)

        monkeypatch.setattr(loop, "_reflect_tick", _hang)

        start = time.monotonic()
        with pytest.raises(asyncio.TimeoutError):
            async with asyncio.timeout(CONFIG["loop"]["reflect_tick_timeout_sec"]):
                await loop._reflect_tick()
        elapsed = time.monotonic() - start

        assert elapsed < _HANG_SEC / 2

    def test_reflect_loop_source_wraps_reflect_tick_in_timeout(self):
        """Static guard: fail loudly if a future edit removes the
        asyncio.timeout wrap around _reflect_tick() inside reflect_loop(),
        since that's the actual fix (this file's dynamic test above only
        proves the mechanism works in isolation, not that reflect_loop()
        uses it)."""
        import inspect
        from core.loop.autonomous_loop import AutonomousLoop

        src = inspect.getsource(AutonomousLoop.reflect_loop)
        assert "asyncio.timeout(CONFIG[\"loop\"][\"reflect_tick_timeout_sec\"])" in src
        assert "await self._reflect_tick()" in src

    def test_reflect_tick_timeout_config_value_present_and_sane(self):
        assert isinstance(CONFIG["loop"].get("reflect_tick_timeout_sec"), (int, float))
        assert 30.0 <= CONFIG["loop"]["reflect_tick_timeout_sec"] <= 3600.0


# ── 4. governor.dispatch() per-agent timeout ────────────────────────────────

class TestGovernorDispatchTimeout:
    def _mocked_governor(self, mock_agent):
        from unittest.mock import MagicMock, AsyncMock
        from core.city.governor import Governor

        g = Governor()
        g._get_registry = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get_by_district.return_value = [mock_agent]
        mock_registry.list_alive.return_value = [mock_agent]
        mock_registry.get_all_agents.return_value = [mock_agent]
        g._get_registry.return_value = mock_registry
        g._llm_classify = MagicMock(return_value="research")
        g._should_convene_council = AsyncMock(return_value=False)
        g._publish_district_event = AsyncMock()
        return g

    async def test_hung_agent_dispatch_is_bounded(self, monkeypatch):
        from unittest.mock import MagicMock

        _HANG_SEC = 3.0
        monkeypatch.setitem(CONFIG["loop"], "agent_dispatch_timeout_sec", 0.3)

        async def _hang(*_a, **_kw):
            await asyncio.sleep(_HANG_SEC)
            return {"status": "ok"}

        mock_agent = MagicMock()
        mock_agent.health_points = 500
        mock_agent.name = "HungTestBot"
        mock_agent.district = "research"
        mock_agent.capabilities = []
        mock_agent.run = _hang

        g = self._mocked_governor(mock_agent)

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "core.metering.rate_limiter.get_rate_limiter"
        ) as mock_rl, __import__("unittest.mock", fromlist=["patch"]).patch(
            "core.metering.budget_meter.get_budget_meter"
        ) as mock_bm:
            mock_rl.return_value.check.return_value = MagicMock(allowed=True, retry_after_secs=0)
            mock_bm.return_value.check_quota.return_value = (True, "ok")

            start = time.monotonic()
            # git_status: a real GREEN task type (an invented name would now be refused before ever reaching the agent).
            result = await g.dispatch({"type": "git_status", "district": "research", "params": {}})
            elapsed = time.monotonic() - start

        assert result.get("status") == "timeout"
        assert elapsed < _HANG_SEC / 2, (
            f"dispatch() blocked for {elapsed:.2f}s on a hung agent.run() "
            f"(hang was {_HANG_SEC}s) — per-agent timeout isn't bounding the wait"
        )

    def test_agent_dispatch_timeout_config_value_present_and_sane(self):
        assert isinstance(CONFIG["loop"].get("agent_dispatch_timeout_sec"), (int, float))
        assert 5.0 <= CONFIG["loop"]["agent_dispatch_timeout_sec"] <= 300.0
        # Must stay under think_tick's own 60s budget so a hung agent is
        # attributed by name before the outer timeout fires anyway.
        assert CONFIG["loop"]["agent_dispatch_timeout_sec"] <= 60.0


# ── 5. performance_benchmarker.run() no longer blocks the event loop ───────

class TestPerformanceBenchmarkerNonBlocking:
    async def test_ollama_benchmark_runs_off_the_event_loop_thread(self, monkeypatch):
        """A slow (mocked) benchmark call must not prevent a concurrently
        scheduled coroutine from making progress -- proof the call actually
        moved off the event-loop thread via asyncio.to_thread."""
        from districts.data_analytics.performance_benchmarker import PerformanceBenchmarker

        agent = PerformanceBenchmarker()

        _SLOW_SEC = 1.0

        def _slow_benchmark(model=None, n=3):
            time.sleep(_SLOW_SEC)
            return {"model": model, "n": n, "avg": 0.01, "p95": 0.02, "p99": 0.03}

        monkeypatch.setattr(agent, "benchmark_ollama_latency", _slow_benchmark)

        ticks = 0

        async def _ticker():
            nonlocal ticks
            for _ in range(20):
                await asyncio.sleep(0.02)
                ticks += 1

        results = await asyncio.gather(
            agent.run({"type": "ollama", "params": {"n": 1}}),
            _ticker(),
        )
        payload = results[0]

        assert payload["status"] == "ok"
        # If the sync call had run directly on the loop thread, the ticker
        # coroutine would have been frozen out and accumulated ~0 ticks
        # during the ~1s of blocking work.
        assert ticks >= 10, (
            f"only {ticks} concurrent ticks during a {_SLOW_SEC}s benchmark call — "
            "benchmark_ollama_latency is still running on the event-loop thread"
        )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
