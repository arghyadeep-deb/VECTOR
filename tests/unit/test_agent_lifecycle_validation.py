import datetime
import uuid

import pytest

from core.city.agent_base import AgentBase
from core.city.agent_registry import AgentRegistry
from core.city.evolution_engine import EvolutionEngine


class LifecycleAgent(AgentBase):
    def __init__(
        self,
        agent_id: str | None = None,
        name: str = "LifecycleAgent",
        district: str = "validation",
        generation: int = 1,
    ) -> None:
        super().__init__(agent_id or str(uuid.uuid4()), name, district, generation=generation)


class FakeMemory:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def store(self, **kwargs) -> None:
        self.events.append(kwargs)


@pytest.mark.asyncio
async def test_agent_death_ghost_successor_birth_end_to_end(monkeypatch):
    registry = AgentRegistry()
    memory = FakeMemory()
    engine = EvolutionEngine(registry=registry, memory=memory)
    engine.register_constructor("LifecycleAgent", LifecycleAgent)
    monkeypatch.setattr(engine, "_persist_agent_history", lambda agent: None)

    dead = LifecycleAgent(agent_id="dead-agent", generation=1)
    dead.health_points = 0
    dead.lessons = ["validate edge cases"]
    dead.best_decisions = [{"action": "repair", "reward": 0.95}]
    dead.ghost_memory = {
        "name": dead.name,
        "district": dead.district,
        "generation": dead.generation,
        "lessons_learned": dead.lessons,
        "best_decisions": dead.best_decisions,
        "personality_traits": {"careful": 0.9},
        "died_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    result = await engine.check_and_evolve([dead])

    assert result == {"died": 1, "spawned": 1, "critical": []}
    successors = registry.get_by_district("validation")
    assert len(successors) == 1
    successor = successors[0]
    assert successor.name == dead.name
    assert successor.generation == 2
    assert successor.lessons == ["validate edge cases"]
    assert successor.best_decisions == dead.best_decisions
    assert [event["event_type"] for event in memory.events] == ["agent_death", "agent_birth"]


@pytest.mark.asyncio
async def test_agent_lifecycle_flags_critical_without_respawning(monkeypatch):
    registry = AgentRegistry()
    engine = EvolutionEngine(registry=registry, memory=FakeMemory())
    monkeypatch.setattr(engine, "_persist_agent_history", lambda agent: None)

    weak = LifecycleAgent(agent_id="weak-agent")
    weak.health_points = 25

    result = await engine.check_and_evolve([weak])

    assert result == {"died": 0, "spawned": 0, "critical": ["LifecycleAgent"]}
    assert registry.get_by_district("validation") == []


@pytest.mark.asyncio
async def test_check_and_evolve_concurrent_deaths(monkeypatch):
    registry = AgentRegistry()
    memory = FakeMemory()
    engine = EvolutionEngine(registry=registry, memory=memory)
    engine.register_constructor("LifecycleAgent", LifecycleAgent)
    monkeypatch.setattr(engine, "_persist_agent_history", lambda agent: None)

    agents = []
    for i in range(3):
        a = LifecycleAgent(agent_id=str(uuid.uuid4()), generation=1)
        a.health_points = 0
        a.lessons = [f"lesson_{i}"]
        a.best_decisions = []
        a.ghost_memory = {
            "name": a.name, "district": a.district,
            "generation": a.generation,
            "lessons_learned": a.lessons,
            "best_decisions": [],
            "personality_traits": {},
        }
        agents.append(a)

    result = await engine.check_and_evolve(agents)
    assert result["died"] == 3
    assert result["spawned"] == 3
    assert len(result["critical"]) == 0
    successors = registry.get_by_district("validation")
    assert len(successors) >= 3


@pytest.mark.asyncio
async def test_spawn_successor_legacy_api(monkeypatch):
    registry = AgentRegistry()
    memory = FakeMemory()
    engine = EvolutionEngine(registry=registry, memory=memory)
    monkeypatch.setattr(engine, "_persist_agent_history", lambda agent: None)

    ghost = {
        "name": "LegacyBot", "district": "validation",
        "generation": 3, "final_hp": 0,
        "lessons_learned": ["legacy lesson"],
        "best_decisions": [{"action": "refactor", "reward": 0.8}],
        "personality_traits": {"meticulous": 0.7},
    }
    blueprint = engine.spawn_successor(ghost)
    assert blueprint["name"] == "LegacyBot"
    assert blueprint["generation"] == 4
    assert blueprint["starting_hp"] == 700
    assert blueprint["lessons_inherited"] == 1
    assert EvolutionEngine._total_deaths >= 1
    assert EvolutionEngine._total_spawns >= 1
