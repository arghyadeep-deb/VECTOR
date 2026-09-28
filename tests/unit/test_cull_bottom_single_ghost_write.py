"""Regression test — EvolutionEngine.cull_bottom() double ghost-persistence
(core-intelligence audit 2026-08-05, Finding #2, LOW).

Root cause: cull_bottom() called self._record_death(agent), which persists
an agent_history ghost row via _persist_agent_history() -> _persist_ghost()
(dict-shaped, built from the live agent object's attributes), and then
immediately called self._registry.deregister(agent_id), which
independently rebuilds its own ghost data and calls _persist_ghost(agent)
again (object-shaped). Both used INSERT OR REPLACE keyed on agent_id, so
this was idempotent/correct but did the ghost write twice per culled agent.

Fix: cull_bottom() now calls the new _log_death_event() (episodic event
log only) instead of the full _record_death() (event + ghost persist),
since deregister() unconditionally persists the ghost moments later anyway.

This test proves two things with real (isolated) DB writes, not mocks:
1. Ghost data still survives a cull — the whole point of ghost memory.
2. The agent_history row for the culled agent is written exactly once by
   cull_bottom(), not twice.
"""
from __future__ import annotations

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



# ── DB isolation (mirrors tests/unit/test_agent_registry_successor_class.py) ──

@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    """Fresh, isolated SQLite DB per test — never touches the real memory DB."""
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "cull_bottom_ghost_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_isolated_cull_bottom_ghost")
    import core.memory.episodic as ep
    ep.close_db_connection()
    yield ep
    ep.close_db_connection()


class CullAgent(AgentBase):
    def __init__(self, agent_id=None, name="CullAgent", district="cull_ghost_test", generation=1):
        super().__init__(agent_id or str(uuid.uuid4()), name, district, generation=generation)


@pytest.mark.asyncio
async def test_ghost_survives_cull_and_is_written_exactly_once(isolated_episodic):
    """Cull a weak agent out of an over-populated district and verify:
    - the agent_history ghost row exists and carries the right data
      (survives the cull — the point of ghost memory)
    - _persist_ghost was invoked exactly once for that agent_id during the
      cull, proving the redundant second write was actually removed.
    """
    registry = AgentRegistry()
    evo = EvolutionEngine(registry=registry)

    # 6 agents in a district with keep_top=5 -> exactly 1 gets culled (the weakest)
    agents = []
    for i in range(6):
        a = CullAgent(agent_id=str(uuid.uuid4()), name=f"CullAgent{i}", district="cull_ghost_test", generation=1)
        a.health_points = 100 + i * 100  # weakest = agents[0], HP=100
        a.lessons = [f"lesson_{i}"]
        a.best_decisions = [{"action": f"decision_{i}", "reward": 0.9}]
        a.ghost_memory = {"note": f"ghost_{i}"}
        registry.register(a)
        agents.append(a)

    weakest = agents[0]
    weakest_id = weakest.id

    # Spy on _persist_ghost to count real invocations for the culled agent.
    call_count = {"n": 0}
    original_persist_ghost = registry._persist_ghost

    def _counting_persist_ghost(agent_or_dict):
        aid = (
            agent_or_dict.get("agent_id") or agent_or_dict.get("id")
            if isinstance(agent_or_dict, dict)
            else getattr(agent_or_dict, "id", None)
        )
        if aid == weakest_id:
            call_count["n"] += 1
        return original_persist_ghost(agent_or_dict)

    registry._persist_ghost = _counting_persist_ghost

    culled_ids = await evo.cull_bottom("cull_ghost_test", keep_top=5)

    assert culled_ids == [weakest_id], f"expected only the weakest agent culled, got {culled_ids}"

    # 1. Ghost data survives the cull.
    ghosts = registry.get_dead_ghosts(district="cull_ghost_test", limit=10)
    matching = [g for g in ghosts if g["id"] == weakest_id]
    assert matching, "culled agent's ghost row was not found in agent_history — ghost data lost"
    ghost_row = matching[0]
    assert ghost_row["name"] == "CullAgent0"
    assert ghost_row["district"] == "cull_ghost_test"
    assert ghost_row["final_hp"] == 100
    # ghost_memory carried through (the object-shaped write from deregister()
    # uses agent.ghost_memory directly)
    assert ghost_row["ghost_memory"].get("lessons_learned") == ["lesson_0"] or \
        ghost_row["ghost_memory"].get("note") == "ghost_0", (
            f"ghost_memory content unexpected: {ghost_row['ghost_memory']!r}"
        )

    # 2. The write happened exactly once for this culled agent — proving
    #    the redundant double-write was removed.
    assert call_count["n"] == 1, (
        f"_persist_ghost was called {call_count['n']} times for the culled "
        f"agent during cull_bottom() — expected exactly 1 (the redundant "
        f"double-write should be gone)"
    )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
