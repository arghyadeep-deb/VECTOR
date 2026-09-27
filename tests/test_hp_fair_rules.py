"""HP/experience rules behind VECTOR_HP_FAIR and VECTOR_PLAYBOOK (owner decisions 2026-09-26). Everything is OFF by default; the
legacy behaviour is asserted too so switching a flag on is a known, measured change."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import core.city.agent_registry as registry_mod
from core.city import experience as xp
from core.city.agent_base import AgentBase
from core.city.agent_registry import AgentRegistry
from core.city.evolution_engine import EvolutionEngine
from core.city.governor import Governor


class Person(AgentBase):
    async def run(self, task):
        return {"status": "ok"}


@pytest.fixture(autouse=True)
def world(isolated_vector_db, monkeypatch):
    monkeypatch.delenv("VECTOR_HP_FAIR", raising=False)
    monkeypatch.delenv("VECTOR_PLAYBOOK", raising=False)
    monkeypatch.delenv("VECTOR_LEVEL_COUNCIL", raising=False)
    monkeypatch.delenv("VECTOR_FAIR_CULL", raising=False)
    xp._reset_for_tests()
    original = registry_mod._registry_singleton
    registry_mod._registry_singleton = AgentRegistry()
    yield registry_mod._registry_singleton
    registry_mod._registry_singleton = original
    xp._reset_for_tests()


def person(name="Ada", district="lab", hp=500):
    a = Person(agent_id=f"id-{name}", name=name, district=district)
    a.health_points = hp
    return a


def fail(agent, error, task_type="do_thing"):
    Governor()._account_failure(agent, task_type, {"status": "error", "error": error})


# ── fault attribution ───────────────────────────────────────────────────────────────────────────────────────────────

def test_default_behaviour_is_unchanged_every_failure_costs_30_but_the_ledger_learns_whose_fault_it_was():
    a = person()
    fail(a, "OPENAI_API_KEY not configured")
    fail(a, "KeyError: 'x'")
    assert a.health_points == 440
    stats = xp.lineage_stats(a)["outcomes"]
    assert stats == {"fail_env": 1, "fail_own": 1}


def test_flag_on_environment_failures_are_free(monkeypatch):
    monkeypatch.setenv("VECTOR_HP_FAIR", "1")
    a = person()
    for _ in range(5):
        fail(a, "provider returned 503 service unavailable")
    assert a.health_points == 500 and a.lessons == []


def test_flag_on_first_failure_of_a_kind_is_cheap_and_leaves_a_lesson_repeats_cost_full(monkeypatch):
    monkeypatch.setenv("VECTOR_HP_FAIR", "1")
    a = person()
    fail(a, "KeyError: 'customer' at line 41")
    assert a.health_points == 495 and any("first" in str(l) for l in a.lessons)
    fail(a, "KeyError: 'customer' at line 90")            # same mistake again
    assert a.health_points == 465
    fail(a, "ValueError: bad date")                        # a different mistake: cheap again
    assert a.health_points == 460


# ── probation instead of instant death ──────────────────────────────────────────────────────────────────────────────

def test_default_zero_hp_is_death(world):
    a = person(hp=20)
    world.register(a)
    out = a.deduct_points(30, "collapse")
    assert out["died"] is True and world.get(a.id) is None


def test_flag_on_zero_hp_starts_probation_and_death_comes_after_the_chances_are_spent(monkeypatch, world):
    monkeypatch.setenv("VECTOR_HP_FAIR", "1")
    a = person(hp=20)
    world.register(a)
    first = a.deduct_points(30, "collapse 1")
    assert first["died"] is False and first["probation"] is True and a.health_points == 1 and first["probation_left"] == 3
    deaths = []
    for i in range(2, 8):
        r = a.deduct_points(30, f"collapse {i}")
        if r["died"]:
            deaths.append(i)
            break
    assert deaths == [5], "first collapse + three more chances, then the fourth further collapse is death"
    assert world.get(a.id) is None


def test_recovery_above_50_resets_probation(monkeypatch, world):
    monkeypatch.setenv("VECTOR_HP_FAIR", "1")
    a = person(hp=20)
    world.register(a)
    assert a.deduct_points(30, "first collapse")["probation_left"] == 3
    a.award_points(100, "verified recovery")
    assert a.health_points > 50 and a._probation_used is False and a._probation_left == 0
    a.health_points = 1
    again = a.deduct_points(30, "later collapse")
    assert again["probation"] is True and again["probation_left"] == 3


def test_death_is_recorded_in_the_ledger_and_the_successor_shares_the_lineage(world):
    a = person("Scout", hp=10)
    world.register(a)
    xp.record(a, "t", "success", verified=True, difficulty=1.0)
    a.deduct_points(50, "fatal")
    stats = xp.lineage_stats(person("Scout"))
    assert stats["deaths"] == 1 and stats["xp"] > 0 and stats["standing_xp"] < stats["xp"]


# ── standing follows level ──────────────────────────────────────────────────────────────────────────────────────────

def _give_level(agent, level):
    while xp.lineage_stats(agent)["level"] < level:
        xp.record(agent, f"t{xp.lineage_stats(agent)['xp']}", "success", verified=True, difficulty=1.0)


def test_level_raises_the_model_tier_only_when_the_flag_is_on(monkeypatch):
    a = person(hp=150)                                     # HP tier: ambient
    _give_level(a, 4)
    xp._CACHE.clear()
    assert a._calculate_model() == "vector-ambient"
    monkeypatch.setenv("VECTOR_HP_FAIR", "1")
    assert a._calculate_model() == "vector-focus", "a level-4 agent keeps the focus tier through a bad HP week"
    b = person("Fresh", hp=150)
    assert b._calculate_model() == "vector-ambient", "level 0 adds nothing"
    c = person("Strong", hp=900)
    assert c._calculate_model() == "vector-dev", "the level floor never lowers a tier"


def test_council_eligibility_follows_level_when_the_flag_is_on(monkeypatch):
    a = person(hp=900)
    assert a.can_vote_in_council() is True
    monkeypatch.setenv("VECTOR_LEVEL_COUNCIL", "1")
    assert a.can_vote_in_council() is False, "high HP alone no longer buys a vote"
    _give_level(a, 5)
    xp._CACHE.clear()
    assert a.can_vote_in_council() is True
    a.health_points = 100
    assert a.can_vote_in_council() is False, "not while on the ropes"


# ── playbook in the prompt ──────────────────────────────────────────────────────────────────────────────────────────

def test_playbook_appears_in_the_system_prompt_only_when_enabled(monkeypatch):
    a = person()
    xp.record(a, "parse", "fail_own", note="KeyError: 'customer'")
    assert "lineage has learned" not in a.get_system_prompt()
    monkeypatch.setenv("VECTOR_PLAYBOOK", "1")
    prompt = a.get_system_prompt()
    assert "What your lineage has learned" in prompt and "DON'T" in prompt and "keyerror" in prompt.lower()


# ── idle agents are safe: culling needs a record of failing ─────────────────────────────────────────────────────────

def _cull(world, district="lab"):
    return asyncio.run(EvolutionEngine(registry=world).cull_bottom(district, keep_top=2))


def test_legacy_rank_cull_when_fair_cull_is_switched_off(monkeypatch, world):
    monkeypatch.setenv("VECTOR_FAIR_CULL", "0")
    for i, hp in enumerate((900, 800, 700, 300)):
        world.register(person(f"P{i}", hp=hp))
    assert len(_cull(world)) == 2


def test_by_default_idle_low_hp_agents_are_never_culled_only_genuinely_failing_ones(monkeypatch, world):
    idle_low = person("IdleLow", hp=150)                   # bottom of the district, never given work
    failing = person("Failing", hp=100)
    for hp, n in ((900, "Top1"), (800, "Top2"), (700, "Top3")):
        world.register(person(n, hp=hp))
    world.register(idle_low)
    world.register(failing)
    for i in range(3):
        xp.record(failing, "t", "fail_own", note=f"mistake {chr(97 + i)}")
    culled = _cull(world)
    assert culled == [failing.id], "the idle agent must be safe; the one with a record of failing may go"
    assert world.get(idle_low.id) is not None


def test_flag_on_penalties_are_not_smoothed_against_earlier_rewards_or_penalties(monkeypatch):
    """The validator's EMA was one state per agent for both signs: a -5 after a +50 award was deducted as 33.5 HP."""
    monkeypatch.setenv("VECTOR_HP_FAIR", "1")
    from core.security.hp_validator import get_hp_validator
    get_hp_validator()._ema_state.clear()
    a = person("Blend", hp=500)
    a.award_points(50, "big win")
    before = a.health_points
    a.deduct_points(5, "tiny slip")
    assert before - a.health_points == pytest.approx(5.0, abs=0.01)
    b = person("Blend2", hp=500)
    b.deduct_points(30, "big loss")
    hp = b.health_points
    b.deduct_points(5, "tiny slip")
    assert hp - b.health_points == pytest.approx(5.0, abs=0.01), "after a -30 the next -5 must still be -5, not -22.5"
    b.deduct_points(30, "another big loss after a small one")
    assert hp - 5.0 - b.health_points == pytest.approx(30.0, abs=0.01), "and a -30 after a -5 must still be -30, not -12.5"


def test_by_default_a_district_of_healthy_agents_loses_nobody_to_the_rank_cull(world):
    """The recorded history: 98% of real deaths were healthy agents culled by rank at 02:00."""
    for i, hp in enumerate((900, 800, 700, 600, 500, 500, 400)):
        world.register(person(f"P{i}", hp=hp))
    assert _cull(world) == [] and world.total() == 7


def test_fair_cull_skips_the_pass_when_the_experience_ledger_fails(monkeypatch, world):
    for i, hp in enumerate((900, 800, 100, 50)):
        world.register(person(f"Ledger{i}", hp=hp))
    monkeypatch.setattr(xp, "own_fault_failures", lambda key: (_ for _ in ()).throw(RuntimeError("db offline")))
    assert _cull(world) == [] and world.total() == 4
