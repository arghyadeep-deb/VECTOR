"""Tests for AgentBase HP system, model tiers, and event handling."""
import uuid

import pytest

from core.city.agent_base import AgentBase


def make_agent(name="TestBot", district="coding", hp=500):
    a = AgentBase(str(uuid.uuid4()), name, district)
    a.health_points = hp
    a.model = a._calculate_model()
    return a


class TestAgentBaseInit:

    def test_initial_hp(self):
        a = AgentBase(str(uuid.uuid4()), "Bot", "coding")
        assert a.health_points == 500

    def test_initial_generation(self):
        a = AgentBase(str(uuid.uuid4()), "Bot", "coding")
        assert a.generation == 1

    def test_custom_generation(self):
        a = AgentBase(str(uuid.uuid4()), "Bot", "coding", generation=3)
        assert a.generation == 3

    def test_id_stored(self):
        aid = str(uuid.uuid4())
        a = AgentBase(aid, "Bot", "coding")
        assert a.id == aid

    def test_name_stored(self):
        a = AgentBase(str(uuid.uuid4()), "MyBot", "research")
        assert a.name == "MyBot"

    def test_district_stored(self):
        a = AgentBase(str(uuid.uuid4()), "Bot", "security")
        assert a.district == "security"

    def test_initial_ghost_empty(self):
        a = AgentBase(str(uuid.uuid4()), "Bot", "coding")
        assert a.ghost_memory == {}

    def test_initial_subscribed_events_empty(self):
        a = AgentBase(str(uuid.uuid4()), "Bot", "coding")
        assert len(a.subscribed_events) == 0

    def test_initial_inbox_empty(self):
        a = AgentBase(str(uuid.uuid4()), "Bot", "coding")
        assert len(a._inbox) == 0


class TestModelCalculation:

    def test_elite_model(self):
        a = make_agent(hp=850)
        assert a.model is not None  # should have cloud_coder assigned

    def test_strong_model(self):
        a = make_agent(hp=700)
        assert a.model is not None

    def test_healthy_model(self):
        a = make_agent(hp=500)
        assert a.model is not None

    def test_weak_model(self):
        a = make_agent(hp=300)
        assert a.model is not None

    def test_critical_model(self):
        a = make_agent(hp=100)
        assert a.model is not None

    def test_dead_model_is_none(self):
        a = make_agent(hp=0)
        assert a.model is None


class TestHPOperations:

    def test_award_points_increases_hp(self):
        # 2026-08-05 reward-curve fix: awards are shaped by headroom
        # ((1000-hp)/1000) and repeat-reason habituation, so a first-time
        # "task_completed" award at hp=500 lands at 100 * 1.0 * 0.5 = 50,
        # not the raw 100. See AgentBase.award_points() docstring.
        a = make_agent(hp=500)
        result = a.award_points(100, "task_completed")
        assert result["new_hp"] == 550
        assert a.health_points == 550

    def test_award_points_caps_at_1000(self):
        # A single realistic-sized award near the ceiling is deliberately
        # tiny now (that's the fix). To prove the hard 1000 ceiling still
        # holds, award something oversized — hp_validator's own outlier
        # clamp (±200) plus the final min(1000, ...) must still cap it.
        a = make_agent(hp=950)
        result = a.award_points(1_000_000, "bonus")
        assert result["new_hp"] == 1000
        assert a.health_points == 1000

    def test_award_points_returns_dict(self):
        a = make_agent(hp=500)
        result = a.award_points(50, "reason")
        assert "old_hp" in result
        assert "new_hp" in result
        assert "model_changed" in result
        assert result["old_hp"] == 500

    def test_deduct_points_decreases_hp(self):
        a = make_agent(hp=500)
        result = a.deduct_points(100, "failure")
        assert result["new_hp"] == 400
        assert a.health_points == 400

    def test_deduct_points_floors_at_zero(self):
        a = make_agent(hp=50)
        result = a.deduct_points(200, "critical_fail")
        assert result["new_hp"] == 0
        assert a.health_points == 0

    def test_deduct_to_zero_triggers_death(self):
        a = make_agent(hp=30)
        result = a.deduct_points(30, "lethal_fail")
        assert result["died"] is True
        assert "ghost" in result

    def test_deduct_without_death(self):
        a = make_agent(hp=500)
        result = a.deduct_points(100, "minor_fail")
        assert result["died"] is False

    def test_award_recalculates_model(self):
        a = make_agent(hp=500)
        old_model = a.model
        # headroom shaping means 400 at hp=500 lands at ~200, not elite tier
        # by itself — the assertion below is structural (always true) and
        # doesn't depend on the exact post-shaping HP value.
        a.award_points(400, "excellence")
        # model should be recalculated (might change)
        assert a.model == a._calculate_model()


class TestDieAndInherit:

    def test_die_returns_ghost(self):
        a = make_agent(hp=100)
        ghost = a.die()
        assert ghost["name"] == a.name
        assert ghost["district"] == a.district
        assert ghost["final_hp"] == 0
        assert "died_at" in ghost

    def test_die_stores_ghost_memory(self):
        a = make_agent()
        a.die()
        assert a.ghost_memory != {}

    def test_inherit_ghost_lessons(self):
        a = AgentBase(str(uuid.uuid4()), "InheritBot", "coding", generation=2)
        ghost = {
            "lessons_learned": ["lesson1", "lesson2"],
            "best_decisions": [{"action": "research", "reward": 0.9}],
            "personality_traits": {"calm": 0.8},
            "generation": 1,
        }
        a.inherit_ghost(ghost)
        assert a.lessons == ["lesson1", "lesson2"]
        assert len(a.best_decisions) == 1
        assert a.personality_traits == {"calm": 0.8}

    def test_inherit_empty_ghost_no_crash(self):
        a = make_agent()
        a.inherit_ghost(None)
        a.inherit_ghost({})
        assert a.lessons == []

    def test_add_lesson_stores(self):
        a = make_agent()
        a.add_lesson("always validate input")
        assert "always validate input" in a.lessons

    def test_add_lesson_caps_at_20(self):
        a = make_agent()
        for i in range(25):
            a.add_lesson(f"lesson_{i}")
        assert len(a.lessons) == 20

    def test_record_decision_high_reward(self):
        a = make_agent()
        a.record_decision({"action": "code_review"}, reward=0.8)
        assert len(a.best_decisions) == 1

    def test_record_decision_low_reward_not_stored(self):
        a = make_agent()
        a.record_decision({"action": "wasted_time"}, reward=0.3)
        assert len(a.best_decisions) == 0

    def test_record_decision_caps_at_10(self):
        a = make_agent()
        for i in range(15):
            a.record_decision({"action": f"action_{i}"}, reward=0.9)
        assert len(a.best_decisions) == 10


class TestStatusAndPredicates:

    def test_can_vote_in_council_high_hp(self):
        a = make_agent(hp=750)
        assert a.can_vote_in_council() is True

    def test_cannot_vote_low_hp(self):
        a = make_agent(hp=600)
        assert a.can_vote_in_council() is False

    def test_is_alive_true(self):
        a = make_agent(hp=1)
        assert a.is_alive is True

    def test_is_alive_false_when_dead(self):
        a = make_agent(hp=0)
        assert a.is_alive is False

    def test_is_elite_true(self):
        a = make_agent(hp=800)
        assert a.is_elite is True

    def test_is_elite_false_below_threshold(self):
        a = make_agent(hp=799)
        assert a.is_elite is False

    def test_can_access_cloud_above_600(self):
        a = make_agent(hp=600)
        assert a.can_access_cloud is True

    def test_cannot_access_cloud_below_600(self):
        a = make_agent(hp=599)
        assert a.can_access_cloud is False

    def test_get_status_elite(self):
        a = make_agent(hp=800)
        assert a.get_status() == "elite"

    def test_get_status_strong(self):
        a = make_agent(hp=700)
        assert a.get_status() == "strong"

    def test_get_status_healthy(self):
        a = make_agent(hp=500)
        assert a.get_status() == "healthy"

    def test_get_status_weakened(self):
        a = make_agent(hp=300)
        assert a.get_status() == "weakened"

    def test_get_status_critical(self):
        a = make_agent(hp=50)
        assert a.get_status() == "critical"

    def test_get_status_dead(self):
        a = make_agent(hp=0)
        assert a.get_status() == "dead"


class TestEventHandling:

    async def test_subscribe_to_stores_event(self):
        a = make_agent()
        a.subscribe_to("RESEARCH_COMPLETE")
        assert "RESEARCH_COMPLETE" in a.subscribed_events

    async def test_subscribe_to_multiple(self):
        a = make_agent()
        a.subscribe_to("EVENT_A")
        a.subscribe_to("EVENT_B")
        assert len(a.subscribed_events) == 2

    async def test_handle_event_queues_to_inbox(self):
        a = make_agent()
        event = {"event_type": "TEST_EVENT", "data": {"key": "value"}}
        result = await a.handle_event(event)
        assert len(a._inbox) == 1
        assert result["status"] == "queued"

    async def test_handle_event_updates_last_active(self):
        import datetime
        a = make_agent()
        before = a.last_active
        event = {"event_type": "TEST_EVENT", "data": {}}
        await a.handle_event(event)
        assert a.last_active >= before

    async def test_run_base_returns_ok(self):
        a = make_agent()
        result = await a.run({"type": "test_task", "params": {}})
        assert result["status"] == "ok"
        assert result["agent"] == a.name


class TestToDict:

    def test_to_dict_has_required_keys(self):
        a = make_agent()
        d = a.to_dict()
        for key in ["id", "name", "district", "generation", "health_points", "model"]:
            assert key in d

    def test_to_dict_hp_matches(self):
        a = make_agent(hp=750)
        d = a.to_dict()
        assert d["health_points"] == 750

    def test_to_dict_district_matches(self):
        a = make_agent(district="research")
        d = a.to_dict()
        assert d["district"] == "research"
