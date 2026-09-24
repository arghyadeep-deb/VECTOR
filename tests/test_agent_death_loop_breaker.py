"""Regression test for the 2026-09-24 external review's Phase 3 finding
(KNOWN_ISSUES #81): APITester died ~858x/day (once per ~63s) and was
resurrected instantly into the same failure every time. AgentRegistry now
quarantines the successor of an agent that dies `max_deaths` times inside
`window_seconds`, with exponentially growing backoff.

Drives the REAL AgentRegistry.deregister() -> successor-spawn path (not a
mock of it); only time.time() is controlled to move past the backoff.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.city.agent_base import AgentBase
from core.city.agent_registry import AgentRegistry

_CFG = {"agent_death_loop": {"max_deaths": 3, "window_seconds": 600.0,
                              "base_backoff_seconds": 100.0, "max_backoff_seconds": 400.0}}


def _kill_and_respawn(reg: AgentRegistry, name: str) -> None:
    """Kill the currently registered agent of this name via the real
    registry path (which spawns/quarantines the successor)."""
    live = [a for a in reg._agents.values() if a.name == name]
    assert live, f"no live {name} to kill"
    reg.deregister(live[0].id)


@pytest.fixture
def reg():
    r = AgentRegistry()
    r._persist_ghost = lambda agent: None  # DB persistence is out of scope here
    return r


def _fresh(reg, name="LoopingAgent"):
    a = AgentBase("id-" + name, name, "qa")
    reg.register(a)
    return a


def test_below_threshold_respawns_normally(reg):
    with patch("core.city.agent_registry.CONFIG", _CFG):
        _fresh(reg)
        for _ in range(2):  # max_deaths is 3, so 2 deaths never quarantine
            _kill_and_respawn(reg, "LoopingAgent")
        assert len([a for a in reg.get_all_agents() if a.name == "LoopingAgent"]) == 1
        assert reg.quarantined() == []


def test_nth_death_quarantines_successor_instead_of_respawning(reg):
    with patch("core.city.agent_registry.CONFIG", _CFG):
        _fresh(reg)
        _kill_and_respawn(reg, "LoopingAgent")
        _kill_and_respawn(reg, "LoopingAgent")
        _kill_and_respawn(reg, "LoopingAgent")  # 3rd death inside the window
        assert [a for a in reg.get_all_agents() if a.name == "LoopingAgent"] == [], (
            "the successor of a death-looping agent must NOT be routable"
        )
        q = reg.quarantined()
        assert len(q) == 1 and q[0]["name"] == "LoopingAgent"
        assert 0 < q[0]["seconds_remaining"] <= 100.0


def test_quarantined_agent_is_released_after_backoff(reg):
    import time as _time
    real_now = _time.time()
    with patch("core.city.agent_registry.CONFIG", _CFG):
        _fresh(reg)
        for _ in range(3):
            _kill_and_respawn(reg, "LoopingAgent")
        assert reg.quarantined()
        with patch("time.time", return_value=real_now + 101.0):
            released = [a for a in reg.get_all_agents() if a.name == "LoopingAgent"]
        assert len(released) == 1
        assert reg.quarantined() == []


def test_backoff_doubles_on_repeat_quarantine_and_caps(reg):
    import time as _time
    t = [_time.time()]
    with patch("core.city.agent_registry.CONFIG", _CFG), patch("time.time", side_effect=lambda: t[0]):
        _fresh(reg)
        remaining = []
        for _round in range(4):
            for _ in range(3):
                _kill_and_respawn(reg, "LoopingAgent")
            remaining.append(round(reg.quarantined()[0]["seconds_remaining"]))
            t[0] += remaining[-1] + 1  # wait out the backoff, agent is released
            reg.get_all_agents()
        assert remaining == [100, 200, 400, 400], f"expected doubling capped at 400, got {remaining}"


def test_other_agents_unaffected_by_one_agents_death_loop(reg):
    with patch("core.city.agent_registry.CONFIG", _CFG):
        _fresh(reg, "LoopingAgent")
        healthy = _fresh(reg, "HealthyAgent")
        for _ in range(3):
            _kill_and_respawn(reg, "LoopingAgent")
        assert any(a.id == healthy.id for a in reg.get_all_agents())
        assert [q["name"] for q in reg.quarantined()] == ["LoopingAgent"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
