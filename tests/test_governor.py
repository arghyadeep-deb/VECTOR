import uuid
import asyncio

import pytest
from core.city.governor import Governor
from core.city.agent_base import AgentBase
from core.city.agent_registry import AgentRegistry, get_registry


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


def governor_with_only(*agents) -> Governor:
    """2026-09-30 (full-suite regression run, Phase 3 codebase audit;
    same root cause class Codex independently confirmed for
    core/loop/decision_engine.py's tests): Governor.dispatch()'s
    capability-vs-HP race reads the process-wide AgentRegistry singleton.
    `clean_registry` above only removes agents THIS test itself added --
    an earlier test elsewhere in a full 6000+ suite run that registers
    real district agents into the SAME shared singleton and doesn't fully
    clean up can leave a real, higher-HP or differently-capable agent in
    the "coding" district that wins these tests' own deliberately-close
    capability/HP races instead of the synthetic agents the test built.
    Bypasses the shared singleton entirely: a genuinely fresh, isolated
    AgentRegistry containing ONLY the given agents, independent of
    whatever any other test in the suite has left in the global one."""
    gov = Governor()
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    gov._registry = reg
    return gov


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


def test_route_unknown_defaults_to_research(monkeypatch):
    # With the LLM classifier unavailable (empty reply), unknown task types
    # must fall back to the research district.
    import core.inference.ollama_safe as ollama_safe
    monkeypatch.setattr(ollama_safe, "chat", lambda *a, **kw: "")
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
    # 2026-09-25: an unclassified, undeclared task type is refused outright ("blocked") rather than routed anywhere.
    assert result.get("status") in ("no_agents", "stub", "error", "ok", "blocked")


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

    gov = governor_with_only(generic, specialist)
    await gov.dispatch({"type": "code_review", "district": "coding", "params": {}})

    assert called.get("agent") == "specialist", (
        f"expected the capability-matched agent to be picked over raw HP, "
        f"got: {called}"
    )


@pytest.mark.asyncio
async def test_dispatch_withholds_hp_when_no_agent_declares_capability():
    """Task A.3 (governor-wiring-and-ambient-perception.md): when a district
    has agents but NONE declare the requested task_type as a capability,
    governor.dispatch() should still run the best-HP agent (an "honest miss"
    that refuses to run was tried and reverted — verified against real
    core/api/routers/*.py call sites, it broke most of them, since the
    manifest's `capabilities` tags are descriptive themes, not literal
    task_type strings) but must NOT award the Darwinian +50 HP for a run
    that wasn't actually capability-matched — that fake-succeeds and
    poisons the HP signal exactly like the original audit finding."""
    agent = make_agent("coding")
    agent.health_points = 900
    agent.capabilities = ["unrelated_capability"]

    called = {}

    async def _run(task):
        called["ran"] = True
        return {"status": "ok"}

    agent.run = _run
    hp_before = agent.health_points

    gov = governor_with_only(agent)
    # 2026-09-25: the type must be a REAL one that this agent simply does not declare. "totally_uncovered_task_type" was
    # an invented name, and running an invented name on whichever agent the caller's district happened to hold is the
    # Governor gap that is now closed (see tests/test_governor_unknown_task_gate.py). git_status is a routing key /
    # GREEN action no coding agent here declares, so the availability-over-purity fallback is still what is exercised.
    result = await gov.dispatch({"type": "git_status", "district": "coding", "params": {}})

    assert result.get("status") == "ok"
    assert called.get("ran") is True, "fallback agent must still run (availability over purity)"
    assert agent.health_points == hp_before, "no HP should be awarded for a non-capability-matched run"
