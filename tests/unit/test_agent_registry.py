"""Tests for AgentRegistry and get_registry()."""
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from unittest.mock import MagicMock

from core.city.agent_registry import AgentRegistry, get_registry
from core.city.agent_base import AgentBase


def make_agent(name="TestBot", district="coding", hp=500):
    agent_id = str(uuid.uuid4())
    a = AgentBase(agent_id, name, district)
    a.health_points = hp
    return a


class TestAgentRegistry:

    def test_init(self):
        reg = AgentRegistry()
        assert reg.total() == 0

    def test_register_increases_count(self):
        reg = AgentRegistry()
        a = make_agent("Bot1", "coding")
        reg.register(a)
        assert reg.total() == 1

    def test_register_multiple(self):
        reg = AgentRegistry()
        reg.register(make_agent("Bot1", "coding"))
        reg.register(make_agent("Bot2", "research"))
        reg.register(make_agent("Bot3", "security"))
        assert reg.total() == 3

    def test_get_returns_agent(self):
        reg = AgentRegistry()
        a = make_agent("GetBot", "coding")
        reg.register(a)
        result = reg.get(a.id)
        assert result is a

    def test_get_missing_returns_none(self):
        reg = AgentRegistry()
        assert reg.get("nonexistent_id") is None

    def test_get_all_agents(self):
        reg = AgentRegistry()
        a1 = make_agent("A1", "coding")
        a2 = make_agent("A2", "research")
        reg.register(a1)
        reg.register(a2)
        all_agents = reg.get_all_agents()
        assert len(all_agents) == 2

    def test_list_alive_excludes_dead(self):
        reg = AgentRegistry()
        alive = make_agent("Alive", "coding", hp=500)
        dead = make_agent("Dead", "research", hp=0)
        reg.register(alive)
        reg.register(dead)
        living = reg.list_alive()
        assert alive in living
        assert dead not in living

    def test_get_by_district(self):
        reg = AgentRegistry()
        a1 = make_agent("CodingBot1", "coding")
        a2 = make_agent("CodingBot2", "coding")
        a3 = make_agent("ResearchBot", "research")
        reg.register(a1)
        reg.register(a2)
        reg.register(a3)
        coders = reg.get_by_district("coding")
        assert len(coders) == 2
        assert a3 not in coders

    def test_get_council_eligible(self):
        reg = AgentRegistry()
        low = make_agent("LowBot", "coding", hp=500)
        high = make_agent("HighBot", "governance", hp=750)
        reg.register(low)
        reg.register(high)
        council = reg.get_council_eligible()
        assert high in council
        assert low not in council

    def test_get_elite(self):
        reg = AgentRegistry()
        elite = make_agent("EliteBot", "coding", hp=900)
        mid = make_agent("MidBot", "research", hp=700)
        reg.register(elite)
        reg.register(mid)
        elites = reg.get_elite(min_hp=800)
        assert elite in elites
        assert mid not in elites

    def test_count_by_district(self):
        reg = AgentRegistry()
        reg.register(make_agent("C1", "coding"))
        reg.register(make_agent("C2", "coding"))
        reg.register(make_agent("R1", "research"))
        counts = reg.count_by_district()
        assert counts["coding"] == 2
        assert counts["research"] == 1

    def test_list_all_returns_dicts(self):
        reg = AgentRegistry()
        a = make_agent("ListBot", "coding")
        reg.register(a)
        listing = reg.list_all()
        assert isinstance(listing, list)
        assert len(listing) == 1
        entry = listing[0]
        assert "id" in entry or "agent_id" in entry
        assert "name" in entry

    def test_list_all_deduplicates(self):
        reg = AgentRegistry()
        a = make_agent("UniqueBot", "coding")
        reg.register(a)
        # List twice — should not duplicate
        listing1 = reg.list_all()
        listing2 = reg.list_all()
        assert len(listing1) == len(listing2)

    def test_get_dead_ghosts_returns_list(self):
        reg = AgentRegistry()
        ghosts = reg.get_dead_ghosts()
        assert isinstance(ghosts, list)

    def test_get_dead_ghosts_by_district(self):
        reg = AgentRegistry()
        ghosts = reg.get_dead_ghosts(district="coding")
        assert isinstance(ghosts, list)

    def test_deregister_removes_agent(self):
        reg = AgentRegistry()
        a = make_agent("DeregBot", "coding")
        reg.register(a)
        assert reg.get(a.id) is not None
        # deregister spawns a successor, so total stays the same or increases
        reg.deregister(a.id)
        # Original agent is removed
        assert reg.get(a.id) is None

    def test_deregister_unknown_id_no_crash(self):
        reg = AgentRegistry()
        # Should not raise
        reg.deregister("totally_unknown_id")

    def test_get_registry_singleton(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_get_registry_is_agent_registry(self):
        r = get_registry()
        assert isinstance(r, AgentRegistry)
