import uuid

import pytest
from core.city.agent_base import AgentBase
from core.config import CONFIG


def make_agent(name="TestAgent", district="coding"):
    return AgentBase(str(uuid.uuid4()), name, district)


def test_initial_hp():
    a = make_agent()
    assert a.health_points == 500


def test_initial_model_is_focus():
    a = make_agent()
    assert a.model == CONFIG["models"]["focus"]


def test_award_points_increases_hp():
    # 2026-08-05 reward-curve fix: awards are shaped by headroom
    # ((1000-hp)/1000) and repeat-reason habituation, so exact 1:1 arithmetic
    # no longer holds — but the new value is still exactly knowable and is
    # asserted as such. A first-time award of 100 at hp=500 lands at
    # 100 * 1.0 (first use of this reason) * 0.5 (headroom) = 50 -> 550.
    # Reviewer note: this originally got relaxed to `> 500` /
    # `new_hp > old_hp`; the latter is true of ANY positive award and would
    # pass even if the shaping were removed entirely. Pinned to the exact
    # value to match tests/unit/test_agent_base.py, which asserts the same
    # 550 for the same call.
    a = make_agent()
    result = a.award_points(100, "test")
    assert a.health_points == 550
    assert result["new_hp"] == 550
    assert result["old_hp"] == 500


def test_hp_capped_at_1000():
    a = make_agent()
    a.health_points = 950
    # A single realistic award is now deliberately tiny near the ceiling
    # (that's the fix) — use an oversized one to prove the hard cap still
    # holds via hp_validator's outlier clamp + the final min(1000, ...).
    a.award_points(1_000_000, "big award")
    assert a.health_points == 1000


def test_deduct_points_decreases_hp():
    a = make_agent()
    result = a.deduct_points(100, "test")
    assert a.health_points == 400
    assert result["new_hp"] == 400


def test_hp_floor_at_zero():
    a = make_agent()
    # HP validator clamps each delta to ±200, so reach the floor across txns
    for _ in range(3):
        a.deduct_points(200, "death")
    assert a.health_points == 0


def test_death_preserves_ghost():
    a = make_agent()
    a.add_lesson("lesson one")
    # HP validator clamps each delta to ±200, so drive to death across txns
    for _ in range(3):
        a.deduct_points(200, "killed")
    assert "died_at" in a.ghost_memory
    assert a.ghost_memory["name"] == "TestAgent"


def test_model_upgrades_with_hp():
    a = make_agent()
    a.health_points = 950
    # Oversized award relies on the same hard-cap safety net as
    # test_hp_capped_at_1000 to deterministically clear the elite tier.
    a.award_points(1_000_000, "upgrade")
    assert a.health_points == 1000
    assert a.is_elite is True
    assert a.model == CONFIG["models"]["cloud_coder"]


def test_model_downgrades_with_hp():
    a = make_agent()
    a.deduct_points(150, "downgrade")
    assert a.health_points == 350
    assert a.model == CONFIG["models"]["reasoning"]


def test_can_vote_in_council_threshold():
    a = make_agent()
    assert not a.can_vote_in_council()
    # Oversized award relies on hp_validator's outlier clamp (±200) to
    # deterministically cross the 700 HP council threshold from birth (500).
    a.award_points(1_000_000, "council eligible")
    assert a.health_points == 700
    assert a.can_vote_in_council()


def test_inherit_ghost_carries_lessons():
    ghost = {
        "lessons_learned": ["lesson A", "lesson B"],
        "best_decisions": [{"action": "search_web", "reward": 0.9}],
        "personality_traits": {"curious": True},
        "generation": 1,
    }
    a = make_agent()
    a.inherit_ghost(ghost)
    assert "lesson A" in a.lessons
    assert len(a.best_decisions) == 1


def test_is_alive_property():
    a = make_agent()
    assert a.is_alive
    # HP validator clamps each delta to ±200, so drive to death across txns
    for _ in range(3):
        a.deduct_points(200, "killed")
    assert not a.is_alive


def test_to_dict_has_all_keys():
    a = make_agent()
    d = a.to_dict()
    for key in ("id", "name", "district", "health_points", "model", "generation"):
        assert key in d
