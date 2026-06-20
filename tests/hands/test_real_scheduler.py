"""Task 1.6 of plans/wire-absorbed-repos-autonomy.md — APScheduler
AsyncIOScheduler is the real callable scheduler. core.scheduler.TaskScheduler
is prompt/LLM-agent-based (create_task -> _execute_task -> system.ask) and
has no add_job/schedule/register/add — _try_register silently no-ops
against it, meaning neither the ~12 pre-existing cron jobs nor the new Hands
have ever actually fired. This proves the real fix against a genuine
AsyncIOScheduler, not a fake.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
async def real_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    sched = AsyncIOScheduler()
    sched.start(paused=True)
    yield sched
    sched.shutdown(wait=False)


@pytest.mark.asyncio
async def test_register_default_jobs_against_real_apscheduler(real_scheduler):
    """Exact count, not just '>0' — before the fix, only the one interval
    job (subconscious-loop) registered; all 12 cron-cadence jobs silently
    failed with 'scheduler API mismatch'. A weak >0 check would pass for
    the wrong reason."""
    from core.loop.cron_jobs import register_default_jobs
    n = register_default_jobs(real_scheduler)
    assert n == 13, f"expected 12 cron jobs + 1 interval job = 13, got {n}"
    assert len(real_scheduler.get_jobs()) == 13


@pytest.mark.asyncio
async def test_hands_register_against_real_apscheduler(real_scheduler):
    from hands.runner import HandRunner
    n = HandRunner().register_all(real_scheduler)
    assert n == 7
    assert len(real_scheduler.get_jobs()) == 7


@pytest.mark.asyncio
async def test_registered_job_actually_invokes_the_callable(real_scheduler):
    """The real proof: a manually-triggered registered job calls the real
    Python function, not a no-op."""
    from core.loop.cron_jobs import _try_register

    side_effect = {"called": False}

    def fn():
        side_effect["called"] = True

    ok = _try_register(real_scheduler, "test-job", "cron", "0 8 * * *", fn)
    assert ok is True

    job = real_scheduler.get_job("test-job")
    assert job is not None
    job.func()  # manually invoke, same as APScheduler would on trigger
    assert side_effect["called"] is True


@pytest.mark.asyncio
async def test_interval_job_registers_against_real_apscheduler(real_scheduler):
    from core.loop.cron_jobs import _try_register_interval

    def fn():
        pass

    ok = _try_register_interval(real_scheduler, "test-interval", 30, fn)
    assert ok is True
    assert real_scheduler.get_job("test-interval") is not None


if __name__ == "__main__":
    print("✅ test_real_scheduler.py module loads")
