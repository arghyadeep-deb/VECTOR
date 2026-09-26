"""Soak test: multiple rounds of death/rebirth under realistic conditions."""

import uuid
import pytest

from core.city.agent_base import AgentBase
from core.city.agent_registry import AgentRegistry
from core.city.evolution_engine import EvolutionEngine


@pytest.fixture(autouse=True)
def _legacy_rank_cull(monkeypatch):
    # These tests exercise the MECHANICS of culling (ghost writes, deregistration, the reflect tick). Since 2026-09-26 the default
    # cull only removes agents that are actually failing (idle/healthy agents are safe -- see core/city/experience.py); the
    # mechanics are unchanged, so run them under the legacy rank rule. The new policy is covered in tests/test_hp_fair_rules.py.
    monkeypatch.setenv("VECTOR_FAIR_CULL", "0")



@pytest.fixture(autouse=True)
def _reset_evolution_counters():
    EvolutionEngine._total_deaths = 0
    EvolutionEngine._total_spawns = 0


class SoakAgent(AgentBase):
    def __init__(self, agent_id=None, name="SoakAgent", district="soak", generation=1):
        super().__init__(agent_id or str(uuid.uuid4()), name, district, generation=generation)


class FakeMemory:
    def __init__(self):
        self.events = []
    def store(self, **kwargs):
        self.events.append(kwargs)


async def _make_dead(engine, registry, name, district, lessons, gen=1):
    agent = SoakAgent(agent_id=str(uuid.uuid4()), name=name, district=district, generation=gen)
    agent.health_points = 0
    agent.lessons = lessons
    agent.best_decisions = [{"action": "survive", "reward": 0.5}]
    agent.ghost_memory = {
        "name": agent.name, "district": agent.district,
        "generation": agent.generation,
        "lessons_learned": agent.lessons,
        "best_decisions": agent.best_decisions,
        "personality_traits": {"adaptive": 0.8},
    }
    registry.register(agent)
    engine.register_constructor(name, SoakAgent)
    return agent


@pytest.mark.asyncio
async def test_soak_multiple_rounds_death_rebirth(monkeypatch):
    registry = AgentRegistry()
    memory = FakeMemory()
    engine = EvolutionEngine(registry=registry, memory=memory)
    monkeypatch.setattr(engine, "_persist_agent_history", lambda agent: None)

    lessons_pool = [
        ["check edge cases"], ["test boundaries"], ["handle timeouts"],
        ["validate inputs"], ["log failures"],
    ]

    for round_num in range(5):
        agent = await _make_dead(
            engine, registry, "SoakAgent", "soak",
            lessons_pool[round_num % len(lessons_pool)],
            gen=round_num + 1,
        )
        result = await engine.check_and_evolve([agent])
        assert result["died"] == 1, f"Round {round_num}: expected 1 death"
        assert result["spawned"] == 1, f"Round {round_num}: expected 1 spawn"

        stats = engine.get_evolution_stats()
        assert stats["total_deaths"] == round_num + 1
        assert stats["total_spawns"] == round_num + 1
        assert stats["highest_generation"] == round_num + 2

    highest_gen = max(a.generation for a in registry.get_by_district("soak"))
    assert highest_gen == 6
    latest = [a for a in registry.get_by_district("soak") if a.generation == highest_gen][0]
    assert "log failures" in latest.lessons

    deaths = [e for e in memory.events if e.get("event_type") == "agent_death"]
    births = [e for e in memory.events if e.get("event_type") == "agent_birth"]
    assert len(deaths) == 5
    assert len(births) == 5


@pytest.mark.asyncio
async def test_soak_cull_bottom_keeps_top_performers(monkeypatch):
    registry = AgentRegistry()
    memory = FakeMemory()
    engine = EvolutionEngine(registry=registry, memory=memory)
    monkeypatch.setattr(engine, "_persist_agent_history", lambda agent: None)
    # deregister auto-spawns; prevent that for cull test
    def _deregister_no_spawn(agent_id):
        agent = registry._agents.pop(agent_id, None)
        if agent:
            engine._record_death(agent)
            EvolutionEngine._total_deaths += 1
    monkeypatch.setattr(registry, "deregister", _deregister_no_spawn)
    engine.register_constructor("SoakAgent", SoakAgent)

    agents = []
    for i in range(10):
        agent = SoakAgent(
            agent_id=str(uuid.uuid4()), name="SoakAgent",
            district="cull_test", generation=1,
        )
        agent.health_points = 100 + i * 20
        agent.lessons = [f"lesson_{i}"]
        agent.ghost_memory = {}
        registry.register(agent)
        agents.append(agent)

    culled_ids = await engine.cull_bottom("cull_test", keep_top=3)

    assert len(culled_ids) == 7
    remaining = registry.get_by_district("cull_test")
    assert len(remaining) == 3

    remaining_hps = sorted([getattr(a, "health_points", 0) for a in remaining])
    assert remaining_hps == [240, 260, 280]

    stats = engine.get_evolution_stats()
    assert stats["total_deaths"] == 7


@pytest.mark.asyncio
async def test_soak_critical_hp_across_rounds(monkeypatch):
    registry = AgentRegistry()
    engine = EvolutionEngine(registry=registry, memory=FakeMemory())
    monkeypatch.setattr(engine, "_persist_agent_history", lambda agent: None)
    engine.register_constructor("SoakAgent", SoakAgent)

    agents = []
    for hp in [10, 25, 45, 55, 70]:
        agent = SoakAgent(agent_id=str(uuid.uuid4()), district="crit_test")
        agent.health_points = hp
        agents.append(agent)

    result = await engine.check_and_evolve(agents)
    assert result["died"] == 0
    assert result["spawned"] == 0
    assert len(result["critical"]) == 3
    assert result["critical"] == ["SoakAgent", "SoakAgent", "SoakAgent"]


@pytest.mark.asyncio
async def test_soak_generation_chain_preserved(monkeypatch):
    registry = AgentRegistry()
    memory = FakeMemory()
    engine = EvolutionEngine(registry=registry, memory=memory)
    monkeypatch.setattr(engine, "_persist_agent_history", lambda agent: None)
    engine.register_constructor("ChainAgent", SoakAgent)

    gen1 = await _make_dead(engine, registry, "ChainAgent", "chain", ["gen1_lesson"], gen=1)
    r1 = await engine.check_and_evolve([gen1])
    assert r1["spawned"] == 1

    alive = [a for a in registry.get_by_district("chain") if a.health_points > 0]
    assert len(alive) == 1
    gen2 = alive[0]
    gen2.health_points = 0
    gen2.lessons = gen2.lessons + ["gen2_lesson"]
    gen2.ghost_memory = {
        "name": gen2.name, "district": gen2.district,
        "generation": gen2.generation,
        "lessons_learned": gen2.lessons,
        "best_decisions": [],
        "personality_traits": {},
    }
    r2 = await engine.check_and_evolve([gen2])
    assert r2["spawned"] == 1

    alive = [a for a in registry.get_by_district("chain") if a.health_points > 0]
    assert len(alive) == 1
    gen3 = alive[0]
    assert gen3.generation == 3
    assert "gen1_lesson" in gen3.lessons
    assert "gen2_lesson" in gen3.lessons

    stats = engine.get_evolution_stats()
    assert stats["highest_generation"] == 3
    assert stats["total_deaths"] == 2
    assert stats["total_spawns"] == 2


@pytest.mark.asyncio
async def test_cull_bottom_with_real_deregister(monkeypatch):
    registry = AgentRegistry()
    memory = FakeMemory()
    engine = EvolutionEngine(registry=registry, memory=memory)
    monkeypatch.setattr(engine, "_persist_agent_history", lambda agent: None)
    engine.register_constructor("SoakAgent", SoakAgent)

    agents = []
    for i in range(5):
        agent = SoakAgent(
            agent_id=str(uuid.uuid4()), name="SoakAgent",
            district="real_cull", generation=1,
        )
        agent.health_points = 100 + i * 40
        agent.lessons = [f"real_lesson_{i}"]
        agent.ghost_memory = {}
        registry.register(agent)
        agents.append(agent)

    culled = await engine.cull_bottom("real_cull", keep_top=3)

    assert len(culled) == 2
    remaining = registry.get_by_district("real_cull")

    kept = [a for a in remaining if a.generation == 1]
    spawned = [a for a in remaining if a.generation > 1]
    assert len(kept) == 3
    assert len(spawned) == 2

    kept_hps = sorted(getattr(a, "health_points", 0) for a in kept)
    assert kept_hps == [180, 220, 260]

    for s in spawned:
        assert s.health_points > 0
        assert len(s.lessons) > 0
