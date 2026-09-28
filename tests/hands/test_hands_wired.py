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


def test_task_type_overrides_match_governor_routes():
    """Phase 2 sub-list unit test (plans/wire-absorbed-repos-autonomy.md):
    HandRunner()._task_type_for(hand) == "<route>" and that route exists in
    governor.py's task-type table — not just a string HandRunner invented."""
    from hands.runner import HandRunner
    from hands.registry import HandRegistry
    from core.city.governor import DISTRICT_TASK_MAP

    runner = HandRunner()
    expected = {
        "researcher": "deep_research",
        "collector": "osint_collect",
        "trader": "trading_analysis",
        "content": "content_generate",
    }
    for hand_name, route in expected.items():
        hand = HandRegistry().get(hand_name)
        assert runner._task_type_for(hand) == route
        assert route in DISTRICT_TASK_MAP, f"route {route!r} missing from governor.py"


def test_trader_hand_reaches_trading_conductor_not_stock_analyst(monkeypatch):
    """Audit finding 2026-06-21: the investment district's manifest only
    registered stock_analyst + sentiment_bot, neither of which branches on
    task_type (stock_analyst.run() always returns a basic quote for a
    hardcoded default symbol regardless of task["type"]). governor.dispatch()
    picked whichever had higher HP, so the trader Hand's scheduled runs
    never reached TradingConductorAgent's real, tonight-verified 11-node
    LLM pipeline at all — "investment/trading is LIVE" was true for direct
    calls but not through the actual scheduler->Hand->Governor path this
    Hand Execution Engine exists to prove. Fixed by registering
    trading_conductor in config/agent_manifest.yaml with a matching
    capability, plus governor.dispatch() now preferring a capability match
    over raw HP. This test proves the real fix, not just the manifest edit:
    it boots real manifest-driven agents into a real registry, then asserts
    a real Governor().dispatch() call for the Hand's exact task lands on
    TradingConductorAgent specifically. The conductor's network/LLM-heavy
    analysis boundary is replaced with a deterministic probe; routing tests
    must not depend on today's market date or a live data vendor."""
    import asyncio
    from core.city.declarative_manifest import ManifestLoader
    from core.city.agent_registry import get_registry
    from core.city.governor import Governor
    from districts.investment.trading_conductor_agent import TradingConductorAgent

    called = {}

    async def routing_probe(self, ticker, date=None, analysts=None):
        called.update(ticker=ticker, date=date, analysts=analysts)
        return {"status": "ok", "ticker": ticker, "rating": "Hold", "routing_probe": True}

    monkeypatch.setattr(TradingConductorAgent, "run_analysis", routing_probe)

    reg = get_registry()
    before = set(reg._agents.keys())
    try:
        loader = ManifestLoader()
        agents = [a for a in loader.load() if a["district"] == "investment"]
        registered = loader.register_all(agents, reg)
        assert registered >= 1

        investment_agents = reg.get_by_district("investment")
        assert any(isinstance(a, TradingConductorAgent) for a in investment_agents), (
            "trading_conductor must be in the manifest-loaded investment agents"
        )
        # Reproduce the exact dispatch shape hands/runner.py sends.
        task = {
            "type": "trading_analysis",
            "district": "investment",
            "params": {"context": "smoke", "hand": "trader"},
        }
        result = asyncio.run(Governor().dispatch(task))
        assert result.get("status") == "ok" and result.get("routing_probe") is True, result
        assert called == {"ticker": "NVDA", "date": None, "analysts": None}
        # The decisive proof: it's not the basic-quote shape stock_analyst returns.
        assert "price" not in result, (
            f"dispatch landed on stock_analyst (returns a 'price' key), not "
            f"trading_conductor: {result}"
        )
    finally:
        for aid in list(reg._agents.keys()):
            if aid not in before:
                reg._agents.pop(aid, None)


def test_autonomous_loop_starts_hand_runner():
    """Task 1.5 — the moment this is wired in, the 9 Hands stop being
    orphaned dataclasses and actually execute on a schedule."""
    import inspect
    from core.loop import autonomous_loop
    src = inspect.getsource(autonomous_loop)
    assert "HandRunner" in src
    assert "register_all" in src


if __name__ == "__main__":
    print("✅ test_hands_wired.py module loads")
