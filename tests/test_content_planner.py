"""Sub-project D: the script -> schedule_post wedge plan had no production caller, so the real post
queue never received a real job. districts/content/content_planner.py plans one per day, and the
existing owner-approved publish job publishes it (publishing stays gated)."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.runtime.plans import PlanStore
from districts.content import content_planner
from districts.content.content_planner import plan_daily_content, pick_topic


def _store(tmp_path) -> PlanStore:
    return PlanStore(path=tmp_path / "plans.json")


def _publisher(devto="k", hashnode="", medium=""):
    p = MagicMock()
    p._devto_key, p._hashnode_token, p._hashnode_pub_id, p._medium_token = devto, hashnode, "pub", medium
    return p


@pytest.mark.asyncio
async def test_creates_exactly_one_wedge_plan_for_configured_platforms(tmp_path):
    store = _store(tmp_path)
    r = await plan_daily_content(store=store, publisher=_publisher(devto="k", medium="m"))
    assert r["status"] == "planned" and r["platforms"] == ["devto", "medium"]
    plans = store.active_plans()
    assert len(plans) == 1
    steps = {s.action_type: s for s in plans[0].steps}
    assert set(steps) == {"script", "schedule_post"}
    assert steps["schedule_post"].param_bindings == {"content": "step-1.content"}
    assert steps["schedule_post"].params["platforms"] == ["devto", "medium"]
    assert plans[0].goal_id == "g_first_revenue"


@pytest.mark.asyncio
async def test_second_call_is_a_noop_while_a_content_plan_is_active(tmp_path):
    store = _store(tmp_path)
    await plan_daily_content(store=store, publisher=_publisher())
    r = await plan_daily_content(store=store, publisher=_publisher())
    assert r["status"] == "skipped" and "active content plan" in r["reason"]
    assert len(store.active_plans()) == 1


@pytest.mark.asyncio
async def test_no_configured_platform_means_honest_skip_not_a_dead_job(tmp_path):
    store = _store(tmp_path)
    r = await plan_daily_content(store=store, publisher=_publisher(devto="", hashnode="", medium=""))
    assert r["status"] == "skipped" and "no publishing platform configured" in r["reason"]
    assert store.active_plans() == []


@pytest.mark.asyncio
async def test_never_raises_the_loop_must_not_die(tmp_path):
    bad = MagicMock()
    bad.active_plans.side_effect = RuntimeError("store exploded")
    r = await plan_daily_content(store=bad, publisher=_publisher())
    assert r["status"] == "error" and "store exploded" in r["error"]


def test_topics_are_truthful_and_rotate_by_day():
    a = pick_topic(datetime(2026, 9, 24, tzinfo=timezone.utc), has_real_work=False)
    b = pick_topic(datetime(2026, 9, 25, tzinfo=timezone.utc), has_real_work=False)
    assert a != b
    assert pick_topic(datetime(2026, 9, 24, tzinfo=timezone.utc), has_real_work=True) == "what VECTOR did today"


@pytest.mark.asyncio
async def test_plan_step_two_creates_a_pending_job_and_nothing_publishes(tmp_path):
    """End to end on isolated state: execute the plan's steps by hand the way PlanRunner would
    (script content -> schedule_post) and confirm a *pending* job exists, with no publisher call."""
    from districts.content.content_scheduler import ContentScheduler
    from districts.content.post_job import JobStatus, PostJobTracker

    store = _store(tmp_path)
    await plan_daily_content(store=store, publisher=_publisher())
    plan = store.active_plans()[0]
    step2 = next(s for s in plan.steps if s.action_type == "schedule_post")

    sched = ContentScheduler()
    sched._tracker = PostJobTracker(db_path=tmp_path / "jobs.db")
    publisher = MagicMock()
    sched._publisher = publisher
    out = await sched.schedule_post(step2.params["title"], "SCRIPT BODY", step2.params["platforms"])
    jobs = sched._tracker.list_by_status(JobStatus.PENDING)
    assert len(jobs) == 1 and jobs[0].payload["content"] == "SCRIPT BODY"
    assert out["job_ids"]
    publisher.publish_all.assert_not_called()
    publisher.publish_devto.assert_not_called()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_content_plan_job_is_registered_before_the_publish_job(monkeypatch):
    import core.loop.cron_jobs as cj

    seen = []
    monkeypatch.setattr(cj, "_try_register", lambda sched, job_id, cadence, cron, fn: seen.append((job_id, cron)) or True)
    monkeypatch.setattr(cj, "_try_register_interval", lambda *a, **k: True)
    cj.register_default_jobs(object())
    ids = [j for j, _ in seen]
    assert "content-plan" in ids and ids.index("content-plan") < ids.index("content-scheduler")
    assert dict(seen)["content-plan"] == "30 8 * * *"
