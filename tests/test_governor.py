import uuid
import asyncio

import pytest
from core.city.governor import Governor
from core.city.agent_base import AgentBase
from core.city.agent_registry import get_registry


@pytest.fixture(autouse=True)
def clean_registry():
    reg = get_registry()
    before = list(reg._agents.keys())
    yield
    # Remove test agents added during test
    for aid in list(reg._agents.keys()):
        if aid not in before:
            reg._agents.pop(aid, None)


def make_agent(district="coding"):
    a = AgentBase(str(uuid.uuid4()), f"TestAgent_{district}", district)
    get_registry().register(a)
    return a


def test_route_coding_task():
    gov = Governor()
    assert gov.route_task("review my git code") == "coding"
    assert gov.route_task("fix a bug") == "coding"


def test_route_calendar_task():
    gov = Governor()
    assert gov.route_task("check my KIIT schedule") == "time_calendar"
    assert gov.route_task("set a deadline") == "time_calendar"


def test_route_security_task():
    gov = Governor()
    assert gov.route_task("scan for malware") == "security"


def test_route_unknown_defaults_to_research():
    gov = Governor()
    assert gov.route_task("xyzzy_totally_unknown") == "research"


@pytest.mark.asyncio
async def test_dispatch_returns_task_id():
    make_agent("coding")
    gov = Governor()
    result = await gov.dispatch({"type": "code_review", "file": "test.py"})
    assert "task_id" in result
    assert "district" in result


@pytest.mark.asyncio
async def test_dispatch_no_agents_returns_no_agents_status():
    gov = Governor()
    result = await gov.dispatch({"type": "unknown_type_xyz_no_district"})
    assert result.get("status") in ("no_agents", "stub", "error", "ok")


def test_get_district_summary_after_register():
    make_agent("coding")
    gov = Governor()
    summary = gov.get_district_summary()
    assert "coding" in summary
    assert summary["coding"]["agents"] >= 1


@pytest.mark.asyncio
async def test_dispatch_prefers_capability_match_over_raw_hp():
    """Audit finding 2026-06-21: governor.dispatch() picked the single
    highest-HP agent in a district regardless of task type, so a Hand's
    task_type was silently ignored whenever a district had >1 registered
    agent (confirmed for investment: trader Hand sends type="trading_analysis"
    but stock_analyst/sentiment_bot — the only manifest-registered investment
    agents — always won the HP race and ignored task type entirely, never
    reaching TradingConductorAgent's real 11-node LLM pipeline). Capability
    matching must win over raw HP."""
    generic = make_agent("coding")
    generic.health_points = 900  # much higher HP, but no capability match
    generic.capabilities = ["general"]

    specialist = make_agent("coding")
    specialist.health_points = 500
    specialist.capabilities = ["coding", "code_review"]

    called = {}

    async def _generic_run(task):
        called["agent"] = "generic"
        return {"status": "ok"}

    async def _specialist_run(task):
        called["agent"] = "specialist"
        return {"status": "ok"}

    generic.run = _generic_run
    specialist.run = _specialist_run

    gov = Governor()
    await gov.dispatch({"type": "code_review", "district": "coding", "params": {}})

    assert called.get("agent") == "specialist", (
        f"expected the capability-matched agent to be picked over raw HP, "
        f"got: {called}"
    )
