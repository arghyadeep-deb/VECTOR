"""Phase 5 (external review 2026-09-24): post_jobs.db held 69 jobs, 0 published.
Root causes found in a copy of the live DB:
  * all 69 were "Test Post"/"Body text" written by the test suite itself,
  * one job sat in 'publishing' forever (no recovery, cancellation not handled).
Publishing itself stays owner-approved (RED) -- nothing here bypasses that.
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from districts.content import post_job, video_pipeline
from districts.content.content_scheduler import ContentScheduler
from districts.content.post_job import JobStatus, PostJobTracker


def _age(tracker: PostJobTracker, job_id: str, minutes: float) -> None:
    ts = (datetime.now(tz=timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with sqlite3.connect(str(tracker._db_path)) as conn:
        conn.execute("UPDATE post_jobs SET updated_at=? WHERE job_id=?", (ts, job_id))


def test_default_job_dbs_are_isolated_from_live_files_under_pytest():
    live_root = Path(post_job.__file__).resolve().parents[2]
    assert post_job._DB_PATH.parent != live_root
    assert video_pipeline._DB_PATH.parent != live_root
    assert "vector_pytest_data" in str(post_job._DB_PATH)


def test_stale_publishing_job_is_recovered_to_retrying(tmp_path):
    t = PostJobTracker(db_path=tmp_path / "j.db")
    jid = t.create(platform="devto", title="real", payload={"content": "x"})
    t.mark_publishing(jid)
    _age(t, jid, 90)
    assert t.recover_stale_publishing(max_age_minutes=30) == [jid]
    assert t.get(jid).status == JobStatus.RETRYING
    assert [j.job_id for j in t.list_pending()] == [jid]


def test_recent_publishing_job_is_left_alone(tmp_path):
    t = PostJobTracker(db_path=tmp_path / "j.db")
    jid = t.create(platform="devto", title="real", payload={"content": "x"})
    t.mark_publishing(jid)
    assert t.recover_stale_publishing(max_age_minutes=30) == []
    assert t.get(jid).status == JobStatus.PUBLISHING


def test_stale_publishing_with_exhausted_retries_fails_instead_of_looping(tmp_path):
    t = PostJobTracker(db_path=tmp_path / "j.db")
    jid = t.create(platform="devto", title="real", payload={"content": "x"}, max_retries=3)
    # mark_publishing() only claims a pending/retrying job (atomic claim guard,
    # 2026-09-30 race-condition fix) -- drive the real cycle instead of calling
    # it back-to-back, so the job reaches attempt_count == max_retries while
    # genuinely stuck in PUBLISHING.
    for _ in range(2):
        t.mark_publishing(jid)
        t.mark_retrying(jid, error="transient")
    t.mark_publishing(jid)
    _age(t, jid, 90)
    t.recover_stale_publishing(max_age_minutes=30)
    assert t.get(jid).status == JobStatus.FAILED


@pytest.mark.asyncio
async def test_cancelled_approval_wait_does_not_strand_job_in_publishing(tmp_path):
    sched = ContentScheduler()
    sched._tracker = PostJobTracker(db_path=tmp_path / "j.db")
    sched._publisher = MagicMock()
    jid = sched._tracker.create(platform="devto", title="real", payload={"content": "x"})

    async def _hang(*a, **kw):
        await asyncio.sleep(30)

    with patch("core.loop.permission_gateway.PermissionGateway.execute", new=_hang):
        task = asyncio.create_task(sched.run_pending())
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert sched._tracker.get(jid).status == JobStatus.RETRYING
    sched._publisher.publish_all.assert_not_called()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
