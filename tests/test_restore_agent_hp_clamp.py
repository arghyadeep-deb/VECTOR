"""restore_agent_hp must never bring an agent back above the 1000 HP ceiling (live HUD 2026-09-25: CodingSwarm 1500,
OpsSwarm 1200, restored from a snapshot saved before the cap was enforced)."""
from __future__ import annotations

from types import SimpleNamespace

from core.loop import loop_state


class _Registry:
    def __init__(self, agents):
        self._agents = agents

    def get_all_agents(self):
        return self._agents


def test_restored_hp_is_clamped_to_the_ceiling_and_floor(monkeypatch):
    a = SimpleNamespace(id="a1", name="CodingSwarm", district="coding", health_points=500)
    b = SimpleNamespace(id="b1", name="OpsSwarm", district="ops", health_points=500)
    c = SimpleNamespace(id="c1", name="Normal", district="x", health_points=500)
    d = SimpleNamespace(id="d1", name="Neg", district="x", health_points=500)
    monkeypatch.setattr(loop_state, "load_agent_hp", lambda: {
        "a1": {"name": "CodingSwarm", "district": "coding", "hp": 1500},
        "b1": {"name": "OpsSwarm", "district": "ops", "hp": 1200},
        "c1": {"name": "Normal", "district": "x", "hp": 640},
        "d1": {"name": "Neg", "district": "x", "hp": -30},
    })
    assert loop_state.restore_agent_hp(_Registry([a, b, c, d])) == 4
    assert (a.health_points, b.health_points, c.health_points, d.health_points) == (1000, 1000, 640, 0)


def test_a_garbage_hp_value_is_skipped_not_fatal(monkeypatch):
    a = SimpleNamespace(id="a1", name="A", district="x", health_points=500)
    monkeypatch.setattr(loop_state, "load_agent_hp", lambda: {"a1": {"name": "A", "district": "x", "hp": "lots"}})
    assert loop_state.restore_agent_hp(_Registry([a])) == 0
    assert a.health_points == 500
