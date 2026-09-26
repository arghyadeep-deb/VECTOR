"""core/city/experience.py: the lineage ledger, XP/level, failure attribution and playbook."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.city import experience as xp


def agent(name="Scout", district="research", gen=1, aid=None):
    return SimpleNamespace(id=aid or f"id-{name}-{gen}", name=name, district=district, generation=gen)


@pytest.fixture(autouse=True)
def _fresh(isolated_vector_db):
    xp._reset_for_tests()
    yield
    xp._reset_for_tests()


def test_a_verified_success_is_worth_more_than_an_unverified_one():
    a = agent()
    verified = xp.record(a, "t1", "success", verified=True)
    unverified = xp.record(agent("Other"), "t1", "success", verified=False)
    assert verified == pytest.approx(5.0) and unverified == pytest.approx(1.5)   # 10 * 0.5 difficulty, x0.3 unverified


def test_repeating_the_same_success_earns_less_each_time():
    a = agent()
    gains = [xp.record(a, "same_task", "success", verified=True) for _ in range(5)]
    assert gains == sorted(gains, reverse=True) and gains[0] > 2 * gains[4] * 0.9
    assert xp.record(a, "a_new_task", "success", verified=True) == pytest.approx(gains[0]), "novel work earns full credit"


def test_harder_tasks_earn_more():
    assert xp.record(agent("A"), "t", "success", verified=True, difficulty=1.0) > xp.record(agent("B"), "t", "success", verified=True, difficulty=0.2)


@pytest.mark.parametrize("failure,expected", [
    ({"error": "OPENAI_API_KEY not configured"}, "env"), ({"error": "connection refused"}, "env"), ("Request timed out after 30s", "env"),
    ({"reason": "provider returned 503"}, "env"), ({"error": "No module named 'kokoro'"}, "env"),
    ({"error": "KeyError: 'customer'"}, "own"), ({"error": "the plan produced no edits"}, "own"), ("division by zero", "own"), (None, "own"),
])
def test_failures_are_attributed_to_the_environment_or_the_agent(failure, expected):
    assert xp.classify_failure(failure) == expected


def test_only_the_first_failure_of_a_kind_teaches():
    a = agent()
    first = xp.record(a, "parse", "fail_own", note="KeyError: 'customer' at line 41")
    again = xp.record(a, "parse", "fail_own", note="KeyError: 'customer' at line 87")     # same mistake, different line number
    other = xp.record(a, "parse", "fail_own", note="ValueError: bad date")
    assert first == xp.LEARNING_XP and again == 0.0 and other == xp.LEARNING_XP
    assert xp.record(a, "parse", "fail_env", note="provider down") == 0.0
    assert xp.is_first_of_kind(xp.lineage_key(a), "parse", xp.failure_signature("ValueError: bad date")) is False


def test_successors_share_the_lineage_and_deaths_temper_standing_but_never_erase_experience():
    parent = agent("Scout", "research", gen=1)
    for i in range(12):
        xp.record(parent, f"task{i}", "success", verified=True, difficulty=1.0)
    before = xp.lineage_stats(parent)
    xp.record_death(parent, "lost 30HP")
    child = agent("Scout", "research", gen=2, aid="id-new")
    after = xp.lineage_stats(child)
    assert after["xp"] == before["xp"], "every bit of XP is still on the ledger"
    assert after["deaths"] == 1 and after["standing_xp"] == pytest.approx(before["xp"] * xp.DEATH_STANDING_FACTOR, abs=0.01)
    assert after["level"] <= before["level"]
    assert xp.lineage_stats(agent("Scout", "coding"))["xp"] == 0, "a different district is a different lineage"


def test_levels_rise_with_standing_xp_and_are_capped():
    assert [xp.level_for_xp(v) for v in (0, 24, 25, 100, 900, 100000)] == [0, 0, 1, 2, 6, xp.MAX_LEVEL]


def test_skill_table_does_not_count_environment_failures_against_the_agent():
    a = agent()
    for _ in range(3):
        xp.record(a, "search", "success", verified=True)
    xp.record(a, "search", "fail_own", note="bad query")
    for _ in range(5):
        xp.record(a, "search", "fail_env", note="provider down")
    s = xp.skill_table(a)["search"]
    assert s["n"] == 9 and s["fail_env"] == 5 and s["success_rate"] == 0.75 and s["verified_rate"] == 1.0


def test_playbook_has_do_dont_and_environment_notes_task_first():
    a = agent()
    for _ in range(4):
        xp.record(a, "strong_task", "success", verified=True)
    for i in range(3):
        xp.record(a, "weak_task", "fail_own", note=f"ValueError: bad input {i}")
    xp.record(a, "weak_task", "success")
    xp.record(a, "weak_task", "fail_env", note="no api key")
    lines = xp.playbook(a, task_type="weak_task", k=6)
    joined = "\n".join(lines)
    assert any(l.startswith("DON'T") and "weak_task" in l for l in lines)
    assert "DO: 'strong_task' is a strength" in joined and "came from the environment" in joined
    assert lines[0].startswith("DON'T") or "weak_task" in lines[0], "lines about the requested task come first"
    assert len(xp.playbook(a, k=2)) == 2


def test_recording_never_raises_on_bad_input():
    assert xp.record(agent(), "t", "not_an_outcome") == 0.0
    assert xp.record(object(), "t", "success") >= 0.0
    assert xp.playbook("nobody:nowhere") == []
