"""Test _reflect_tick calls cull_bottom death-rebirth in the autonomous loop."""

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



class CullAgent(AgentBase):
    def __init__(self, agent_id=None, name="CullAgent", district="reflect_test", generation=1):
        super().__init__(agent_id or str(uuid.uuid4()), name, district, generation=generation)


class FakeMemory:
    def __init__(self):
        self.events = []
    def store(self, **kwargs):
        self.events.append(kwargs)


class FakeDailyReviewer:
    async def review(self):
        return True


@pytest.fixture(autouse=True)
def _reset_counters():
    EvolutionEngine._total_deaths = 0
    EvolutionEngine._total_spawns = 0


@pytest.mark.asyncio
async def test_reflect_tick_culls_weak_agents(monkeypatch):
    from core.loop.autonomous_loop import AutonomousLoop

    registry = AgentRegistry()
    memory = FakeMemory()

    evo = EvolutionEngine(registry=registry, memory=memory)
    evo.register_constructor("CullAgent", CullAgent)
    monkeypatch.setattr(evo, "_persist_agent_history", lambda agent: None)

    for i in range(8):
        a = CullAgent(agent_id=str(uuid.uuid4()), name="CullAgent", district="reflect_test", generation=1)
        a.health_points = 100 + i * 50
        a.lessons = [f"lesson_{i}"]
        a.ghost_memory = {}
        registry.register(a)

    loop = AutonomousLoop()
    loop._memory = memory
    loop._tick_count = 100

    original_get_registry = None
    import core.city.agent_registry as reg_mod
    original_get_registry = reg_mod.get_registry
    monkeypatch.setattr(reg_mod, "get_registry", lambda: registry)

    monkeypatch.setattr(loop, "_get_memory", lambda: memory)
    monkeypatch.setattr(loop, "_check_session_compact", _async_noop)

    from districts.reflection import daily_reviewer
    monkeypatch.setattr(daily_reviewer, "DailyReviewer", FakeDailyReviewer)

    import scripts.db_backup as db_backup
    monkeypatch.setattr(db_backup, "run_backup", lambda: {"backed": [], "failed": []})

    import subprocess
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    await loop._reflect_tick()

    alive = [a for a in registry.get_by_district("reflect_test") if a.health_points > 0]
    assert len(alive) >= 5

    assert EvolutionEngine._total_deaths >= 3
    assert EvolutionEngine._total_spawns >= 3

    gen2_count = len([a for a in registry.get_by_district("reflect_test") if a.generation > 1])
    assert gen2_count >= 3


async def _async_noop(*args, **kwargs):
    return None
