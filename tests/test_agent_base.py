import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

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
    a = make_agent()
    result = a.award_points(100, "test")
    assert a.health_points == 600
    assert result["new_hp"] == 600
    assert result["old_hp"] == 500


def test_hp_capped_at_1000():
    a = make_agent()
    a.award_points(600, "big award")
    assert a.health_points == 1000


def test_deduct_points_decreases_hp():
    a = make_agent()
    result = a.deduct_points(100, "test")
    assert a.health_points == 400
    assert result["new_hp"] == 400


def test_hp_floor_at_zero():
    a = make_agent()
    a.deduct_points(9999, "death")
    assert a.health_points == 0


def test_death_preserves_ghost():
    a = make_agent()
    a.add_lesson("lesson one")
    a.deduct_points(9999, "killed")
    assert "died_at" in a.ghost_memory
    assert a.ghost_memory["name"] == "TestAgent"


def test_model_upgrades_with_hp():
    a = make_agent()
    a.award_points(350, "upgrade")
    assert a.health_points == 850
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
    a.award_points(201, "council eligible")
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
    a.deduct_points(9999, "killed")
    assert not a.is_alive


def test_to_dict_has_all_keys():
    a = make_agent()
    d = a.to_dict()
    for key in ("id", "name", "district", "health_points", "model", "generation"):
        assert key in d
