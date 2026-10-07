"""Regression for core/api/routers/health.py:

/health/readiness, /health/hardened-readiness, and /health/doctor are `async def`
endpoints that called the synchronous, blocking `run_dependency_doctor()`
(blocking file I/O + a blocking `urllib.request.urlopen()` call inside
core/runtime/doctor.py) directly in the coroutine body, with no
`asyncio.to_thread()`. On a single-process asyncio event loop, every other
coroutine (other requests, the autonomous loop's own async tasks) is starved
for the full duration of each dependency-doctor run. Fixed by wrapping each
call in `await asyncio.to_thread(...)`, matching the pattern already used
elsewhere in this same file (see the `psutil.cpu_percent` and
`EpisodicMemory().get_stats()` calls).
"""
from __future__ import annotations

import asyncio
import time

import core.runtime.doctor as doctor_module
from core.api.routers import health as health_router


class _FakeReport:
    def to_dict(self):
        return {"required_failed": False, "ok": True}


def _blocking_doctor(*, include_optional=False, hardened=False):
    time.sleep(0.3)
    return _FakeReport()


async def _concurrent_wall_time(endpoint_coro) -> float:
    """Run `endpoint_coro` alongside a 0.24s ticker and return total wall time.

    If the endpoint truly runs the blocking doctor call off-thread (the fix),
    the two run concurrently: total time ~= max(0.3, 0.24) ~= 0.3s. If the
    endpoint blocks the event loop (the bug), the ticker cannot even start
    until the blocking call finishes: total time ~= 0.3 + 0.24 = 0.54s.
    """
    async def ticker():
        for _ in range(12):
            await asyncio.sleep(0.02)

    start = time.monotonic()
    await asyncio.gather(endpoint_coro, ticker())
    return time.monotonic() - start


async def test_readiness_does_not_block_event_loop(monkeypatch):
    monkeypatch.setattr(doctor_module, "run_dependency_doctor", _blocking_doctor)
    elapsed = await _concurrent_wall_time(health_router.readiness())
    assert elapsed < 0.45, (
        f"took {elapsed:.3f}s (expected ~0.3s if concurrent) -- "
        "/health/readiness blocked the event loop during the doctor call"
    )


async def test_hardened_readiness_does_not_block_event_loop(monkeypatch):
    monkeypatch.setattr(doctor_module, "run_dependency_doctor", _blocking_doctor)
    elapsed = await _concurrent_wall_time(health_router.hardened_readiness())
    assert elapsed < 0.45, (
        f"took {elapsed:.3f}s (expected ~0.3s if concurrent) -- "
        "/health/hardened-readiness blocked the event loop during the doctor call"
    )


async def test_doctor_endpoint_does_not_block_event_loop(monkeypatch):
    monkeypatch.setattr(doctor_module, "run_dependency_doctor", _blocking_doctor)
    elapsed = await _concurrent_wall_time(health_router.doctor())
    assert elapsed < 0.45, (
        f"took {elapsed:.3f}s (expected ~0.3s if concurrent) -- "
        "/health/doctor blocked the event loop during the doctor call"
    )
