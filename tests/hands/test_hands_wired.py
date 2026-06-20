"""Task 1.4 of plans/wire-absorbed-repos-autonomy.md — register_all into the
durable scheduler, on_demand skip, and model-residency serialization.
"""
from __future__ import annotations

import asyncio

import pytest


class FakeScheduler:
    def __init__(self):
        self.jobs: list[tuple] = []

    def add_job(self, fn=None, *args, job_id=None, id=None, cron=None, **kwargs):
        self.jobs.append((job_id or id, cron, fn))
        return True


def test_on_demand_field_exists_and_set_for_manual_hands():
    from hands.registry import HandRegistry
    reg = HandRegistry()
    browser = reg.get("browser")
    clip = reg.get("clip")
    researcher = reg.get("researcher")
    assert browser.on_demand is True
    assert clip.on_demand is True
    assert researcher.on_demand is False


def test_register_all_skips_on_demand_registers_seven():
    from hands.runner import HandRunner
    scheduler = FakeScheduler()
    runner = HandRunner()
    registered = runner.register_all(scheduler)
    assert registered == 7
    assert len(scheduler.jobs) == 7
    job_ids = [j[0] for j in scheduler.jobs]
    assert "hand-browser" not in job_ids
    assert "hand-clip" not in job_ids
    assert "hand-researcher" in job_ids


def test_model_heavy_hands_serialize_not_concurrent():
    """Two model-heavy hands triggered together must not run concurrently —
    the second waits for the first to release the model-residency lock."""
    from hands.runner import HandRunner
    from hands.registry import HandRegistry

    runner = HandRunner()
    order: list[str] = []

    async def _slow_dispatch(hand, context):
        order.append(f"{hand.name}-start")
        await asyncio.sleep(0.2)
        order.append(f"{hand.name}-end")
        return "ok"

    runner._dispatch = _slow_dispatch

    researcher = HandRegistry().get("researcher")
    trader = HandRegistry().get("trader")
    assert researcher.name in runner.MODEL_HEAVY_HANDS
    assert trader.name in runner.MODEL_HEAVY_HANDS

    async def _run_both():
        await asyncio.gather(
            runner.run_hand(researcher, {}),
            runner.run_hand(trader, {}),
        )

    asyncio.run(_run_both())

    # Serialized: first hand's start+end must both precede the second
    # hand's start. If they ran concurrently, we'd see start,start,end,end.
    assert order[1].endswith("-end") or order[0].split("-")[0] == order[1].split("-")[0], order
    first_hand = order[0].rsplit("-", 1)[0]
    first_end_idx = order.index(f"{first_hand}-end")
    second_start_idx = next(i for i, v in enumerate(order) if v.endswith("-start") and not v.startswith(first_hand))
    assert second_start_idx > first_end_idx, f"hands ran concurrently: {order}"


if __name__ == "__main__":
    print("✅ test_hands_wired.py module loads")
