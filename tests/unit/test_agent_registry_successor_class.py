"""Regression tests for the "successor comes back as a bare AgentBase stub"
bug (2026-08-05 fix).

Root cause: AgentRegistry.deregister() hardcoded `AgentBase(...)` for the
successor in both its main path and its fallback path, instead of
reconstructing the SAME class as the agent that died. A district staffed by
a real subclass (e.g. CodingSwarm — 14 wrapped Python specialists + 10 .md
prompt agents, a real async run()) would, on death, be silently replaced by
a bare AgentBase whose run() just returns {"status": "ok", ...} without
doing any work, and whose capabilities list is always [] (capabilities are
injected by ManifestLoader AFTER construction, never inside a class's own
__init__ — so inherit_ghost(), which only restores lessons/best_decisions/
personality_traits, could never have fixed this either).

These tests drive agents to death through the REAL production path
(deduct_points -> die() -> agent_registry.deregister()), not a shortcut, so
they prove the actual fix rather than a mocked approximation.

DB isolation: deregister() persists a ghost row via _persist_ghost(), which
goes through core.memory.episodic.get_db_connection(). All tests here use
the isolated_episodic fixture (same pattern as
tests/unit/test_memory_decay.py) so nothing touches the real
vector_memory.db.
"""
from __future__ import annotations

import uuid

import pytest

from core.city.agent_base import AgentBase
from core.city.agent_registry import get_registry


# ── DB isolation (mirrors tests/unit/test_memory_decay.py::isolated_episodic) ──

@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    """Fresh, isolated SQLite DB per test — never touches the real memory DB."""
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "agent_registry_successor_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_isolated_agent_registry_successor")
    import core.memory.episodic as ep
    ep.close_db_connection()
    yield ep
    ep.close_db_connection()


@pytest.fixture()
def clean_registry_slot():
    """The production death path (AgentBase.die()) always uses the process
    singleton registry (get_registry()), so these tests register real
    agents into it. Snapshot the keys before the test and remove anything
    added during it, so this test file never leaks agents into other tests
    that share the same singleton within one pytest process."""
    reg = get_registry()
    before = set(reg._agents.keys())
    yield reg
    for aid in list(reg._agents.keys()):
        if aid not in before:
            reg._agents.pop(aid, None)


def _kill(agent) -> None:
    """Drive an agent to HP 0 through the real deduct_points() path, same
    pattern as agent_base.py's own __main__ smoke test — deduct_points()
    triggers die() -> agent_registry.deregister() exactly once, the moment
    HP first reaches 0."""
    for _ in range(200):
        if not agent.is_alive:
            break
        agent.deduct_points(agent.health_points or 1, "regression test kill")
    assert not agent.is_alive, "test setup failure: agent never reached 0 HP"


# ── 1. Real district subclass dies -> successor is the SAME class ──────────

def test_dying_coding_swarm_respawns_as_coding_swarm_with_capabilities(
    isolated_episodic, clean_registry_slot
):
    """Kill a real CodingSwarm (districts/coding/agent.py) through the actual
    production path and assert the successor is a genuine CodingSwarm — not
    a bare AgentBase — with its capabilities intact and a run() that is its
    own, not AgentBase.run."""
    from districts.coding.agent import CodingSwarm

    reg = clean_registry_slot
    swarm = CodingSwarm()
    reg.register(swarm)

    # Capabilities are normally injected by ManifestLoader AFTER
    # construction (declarative_manifest.instantiate_all) — simulate that
    # here so we can assert they survive death -> respawn.
    swarm.capabilities = ["code_review", "architecture", "refactor"]
    original_generation = swarm.generation
    dying_id = swarm.id

    _kill(swarm)

    # CodingSwarm hardcodes its own id ("coding-swarm-001") in __init__ —
    # every CodingSwarm instance, including the successor, reoccupies that
    # same registry slot by design (a singleton-per-district agent). So the
    # correctness signal here is object identity, not registry-key absence:
    # the OBJECT at that id must no longer be the one that died.
    successors = [
        a for a in reg.get_by_district("coding")
        if isinstance(a, CodingSwarm) and a is not swarm
    ]
    assert successors, "no CodingSwarm successor was registered after death"
    successor = successors[0]
    assert successor is not swarm

    assert type(successor) is CodingSwarm, (
        f"successor came back as {type(successor).__name__}, not CodingSwarm "
        f"— this is the exact bug: a district silently downgraded to a "
        f"bare stub that reports fake success"
    )
    assert successor.generation == original_generation + 1
    assert successor.capabilities == ["code_review", "architecture", "refactor"], (
        "successor's capabilities were not carried across the generation "
        "boundary — governor.dispatch()'s capability match would silently "
        "stop routing real work to it"
    )
    # The successor's run() must be CodingSwarm's own real async dispatcher,
    # not the fake-success AgentBase.run() ({"status": "ok", ...} with no
    # work performed).
    assert type(successor).run is not AgentBase.run
    assert type(successor).run is CodingSwarm.run


# ── 2. Reconstruction-failure path stays staffed AND logs loudly ───────────

class _UnsatisfiableAgent(AgentBase):
    """A district agent whose constructor cannot be satisfied by any of the
    shapes AgentRegistry._instantiate_successor tries (zero-arg, AgentBase
    kwargs, AgentBase positional) — simulates a genuinely incompatible
    subclass constructor."""

    def __init__(self, required_thing: str, district: str = "unsatisfiable_district"):
        super().__init__(str(uuid.uuid4()), "UnsatisfiableAgent", district)
        self.required_thing = required_thing


def test_unreconstructable_class_falls_back_to_staffed_agentbase_and_logs_error(
    isolated_episodic, clean_registry_slot
):
    """When the dying agent's class cannot be reconstructed, the district
    must NOT be left unstaffed (RULE 9) — but the downgrade must be LOUD
    (logger.error naming the class), never a silent stub swap."""
    from loguru import logger

    reg = clean_registry_slot
    agent = _UnsatisfiableAgent(required_thing="widget")
    reg.register(agent)
    agent.capabilities = ["some_capability"]
    dying_id = agent.id

    captured: list[str] = []
    sink_id = logger.add(captured.append, level="ERROR")
    try:
        _kill(agent)
    finally:
        logger.remove(sink_id)

    # District stays staffed — RULE 9. Original entry is gone, but a
    # successor exists in its place.
    assert reg.get(dying_id) is None
    remaining = [
        a for a in reg.get_by_district("unsatisfiable_district")
        if a.id != dying_id
    ]
    assert remaining, "district was left unstaffed after an unreconstructable death — RULE 9 violated"
    successor = remaining[0]

    # Degrades to the CURRENT (pre-fix) behaviour: a staffed bare AgentBase —
    # never a crash, never an empty district.
    assert type(successor) is AgentBase
    assert successor.generation == agent.generation + 1
    # Capabilities are still carried through even on the degraded path.
    assert successor.capabilities == ["some_capability"]

    # The downgrade must be loud: an ERROR log naming the actual class that
    # failed to reconstruct.
    joined = "\n".join(captured)
    assert "_UnsatisfiableAgent" in joined, (
        f"reconstruction failure was not logged loudly with the class name; "
        f"captured ERROR logs: {captured!r}"
    )
    assert "FAILED" in joined or "failed" in joined.lower()


# ── 3. Ghost inheritance still works across the generation boundary ────────

class _LessonAgent(AgentBase):
    def __init__(self, agent_id: str | None = None, name: str = "LessonAgent",
                 district: str = "lesson_district", generation: int = 1):
        super().__init__(agent_id or str(uuid.uuid4()), name, district, generation=generation)


def test_ghost_lessons_inherited_across_generation_boundary(
    isolated_episodic, clean_registry_slot
):
    """A successor (whatever class it comes back as) must inherit the dying
    agent's lessons, best_decisions, and personality_traits — this was
    already working before the fix and must not regress."""
    reg = clean_registry_slot
    agent = _LessonAgent()
    reg.register(agent)
    agent.lessons = ["always validate input", "check edge cases"]
    agent.best_decisions = [{"action": "retry with backoff", "reward": 0.9}]
    agent.personality_traits = {"cautious": 0.85}
    dying_id = agent.id

    _kill(agent)

    successors = [
        a for a in reg.get_by_district("lesson_district")
        if a.id != dying_id
    ]
    assert successors, "no successor registered after death"
    successor = successors[0]

    # The two lessons the agent had must be inherited first. Since 2026-09-25 (ghost memory records failures) the HP the
    # agent lost while dying is also remembered, so a failure lesson follows them.
    assert successor.lessons[:2] == ["always validate input", "check edge cases"]
    assert any("regression test kill" in str(lesson) for lesson in successor.lessons[2:])
    assert successor.best_decisions == [{"action": "retry with backoff", "reward": 0.9}]
    assert successor.personality_traits == {"cautious": 0.85}
    assert successor.generation == agent.generation + 1


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
