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
    assert n == 18, f"expected 16 cron jobs + 2 interval jobs... = 18 (13 + content-plan, OAuth refresh, cloud heartbeat added 2026-09-24, agent-gym added 2026-09-26), got {n}"
    assert len(real_scheduler.get_jobs()) == 18


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


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    import core.memory.episodic as ep
    ep.close_db_connection()
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "listener_test.db"))
    yield ep
    try:
        ep.close_db_connection()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_job_run_listener_records_success(isolated_db, real_scheduler):
    """Soak-window finding: most cron jobs write nowhere observable on a
    healthy run (several only log on failure), so a 24h soak with no
    independent firing record can't distinguish 'cron is dead' from 'cron
    fired but only logs failures'. _record_job_run closes that permanently."""
    from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
    from core.loop.autonomous_loop import _record_job_run
    from core.memory.episodic import get_temp_cursor

    real_scheduler.add_listener(_record_job_run, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    real_scheduler.resume()

    def fn():
        return "ok"

    from datetime import datetime, timedelta, timezone
    real_scheduler.add_job(fn, "date", run_date=datetime.now(timezone.utc) + timedelta(milliseconds=200), id="listener-success-test")
    await asyncio.sleep(1.0)

    with get_temp_cursor() as cursor:
        cursor.execute(
            "SELECT source, content FROM episodic_memory WHERE event_type='scheduler_job_run' AND source=?",
            ("listener-success-test",),
        )
        row = cursor.fetchone()
    assert row is not None
    assert "ok" in row[1]


@pytest.mark.asyncio
async def test_job_run_listener_records_failure(isolated_db, real_scheduler):
    from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
    from core.loop.autonomous_loop import _record_job_run
    from core.memory.episodic import get_temp_cursor

    real_scheduler.add_listener(_record_job_run, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    real_scheduler.resume()

    def failing_fn():
        raise RuntimeError("listener-test-boom")

    from datetime import datetime, timedelta, timezone
    real_scheduler.add_job(failing_fn, "date", run_date=datetime.now(timezone.utc) + timedelta(milliseconds=200), id="listener-failure-test")
    await asyncio.sleep(1.0)

    with get_temp_cursor() as cursor:
        cursor.execute(
            "SELECT source, content FROM episodic_memory WHERE event_type='scheduler_job_run' AND source=?",
            ("listener-failure-test",),
        )
        row = cursor.fetchone()
    assert row is not None
    assert "error" in row[1]
    assert "listener-test-boom" in row[1]


if __name__ == "__main__":
    print("✅ test_real_scheduler.py module loads")
