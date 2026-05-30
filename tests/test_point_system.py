import uuid

import pytest
from core.memory.policy import PolicyMemory


@pytest.fixture
def pm():
    return PolicyMemory()


def unique_hash(pm):
    return pm.make_situation_hash({"run": uuid.uuid4().hex})


def test_default_score_before_any_data(pm):
    h = unique_hash(pm)
    score = pm.get_score("brand_new_action_xyz", h)
    assert score == PolicyMemory.DEFAULT_SCORE


def test_score_updates_after_outcome(pm):
    h = unique_hash(pm)
    pm.update_from_outcome("test_action", h, 1.0)
    score = pm.get_score("test_action", h)
    assert score > PolicyMemory.DEFAULT_SCORE


def test_online_average_converges(pm):
    h = unique_hash(pm)
    for _ in range(5):
        pm.update_from_outcome("avg_action", h, 0.8)
    score = pm.get_score("avg_action", h)
    assert abs(score - 0.8) < 0.01


def test_reward_clamped_to_0_1(pm):
    h = unique_hash(pm)
    pm.update_from_outcome("clamp_action", h, 9999.0)
    score = pm.get_score("clamp_action", h)
    assert 0.0 <= score <= 1.0

    pm.update_from_outcome("clamp_action", h, -9999.0)
    score2 = pm.get_score("clamp_action", h)
    assert 0.0 <= score2 <= 1.0


def test_get_stats_returns_dict(pm):
    pm.update_from_outcome("stats_action", unique_hash(pm), 0.5)
    stats = pm.get_stats()
    assert "total_entries" in stats
    assert "overall_avg_reward" in stats
    assert stats["total_entries"] >= 1


def test_different_situations_tracked_separately(pm):
    h1 = unique_hash(pm)
    h2 = unique_hash(pm)
    pm.update_from_outcome("same_action", h1, 1.0)
    pm.update_from_outcome("same_action", h2, 0.0)
    s1 = pm.get_score("same_action", h1)
    s2 = pm.get_score("same_action", h2)
    assert s1 > s2


def test_make_situation_hash_deterministic(pm):
    ctx = {"task": "test", "env": "dev"}
    h1 = pm.make_situation_hash(ctx)
    h2 = pm.make_situation_hash(ctx)
    assert h1 == h2


def test_get_top_actions_returns_list(pm):
    h = unique_hash(pm)
    for _ in range(3):
        pm.update_from_outcome("top_action", h, 0.9)
    top = pm.get_top_actions(limit=10)
    assert isinstance(top, list)
    if top:
        assert "action" in top[0]
        assert "avg_reward" in top[0]
