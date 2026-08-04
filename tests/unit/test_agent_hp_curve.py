"""Regression tests for the 2026-08-05 HP reward-curve fix.

Production measurement (4d17h run, data/logs/vector_api.2026-07-30_09-23-47_308413.log):
1,098 HP award events vs 4 deducts (274:1), 0 agent deaths ever, and
"virtually every line reads +30.0HP | 1000->1000" — agents doing merely
frequent routine work (health_check_done, seo_report_generated, fired every
tick) saturated the 1000 ceiling within minutes because every award was
full-value and the only ceiling was a flat `min(1000, hp+delta)`. That makes
HP measure activity frequency, not quality — the opposite of Critical Rule
#4 ("fake HP = fake evolution"), and it is what made
Governor.dispatch()'s `max(agents, key=lambda a: a.health_points)` fallback
an effectively arbitrary tiebreak once every agent in a district sat tied
at the ceiling (the documented root cause of KNOWN_ISSUES.md issue #10).

The fix (core/city/agent_base.py AgentBase.award_points()) shapes every
award with two multiplicative dampeners:
  1. repeat-reason habituation: the Nth time an agent earns points for the
     exact same `reason` string, the award is divided by (1+N).
  2. headroom scaling: every award is scaled by (1000-hp)/1000, so
     approaching the cap costs exponentially more real accomplishments the
     closer an agent gets.

deduct_points() is intentionally untouched (the Darwinian death mechanic
must stay at full strength). These tests pin down the required end-state:
routine repetition no longer pins an agent at 1000, two agents with
genuinely different outcome profiles land at genuinely different HP, HP
still clamps to [0, 1000], and hitting 0 still triggers death/ghost.
"""

import uuid

import pytest

from core.city.agent_base import AgentBase
from core.security.hp_validator import HPValidator


def make_agent(name="CurveBot", district="qa", hp=500):
    a = AgentBase(str(uuid.uuid4()), name, district)
    a.health_points = hp
    a.model = a._calculate_model()
    return a


@pytest.fixture
def isolated_validator(monkeypatch):
    """Route HP validation through a private in-memory HPValidator.

    core/security/hp_validator.py's module-level singleton writes to a real
    file (core/security/hp_validator.db) that the live VECTOR process
    actively reads/writes while this suite runs. AgentBase._validate_hp_delta
    resolves get_hp_validator() via a local import at call time, so
    monkeypatching the module-level function is sufficient to redirect it
    for the duration of each test without touching agent_base.py.
    """
    validator = HPValidator(db_path=":memory:")
    monkeypatch.setattr(
        "core.security.hp_validator.get_hp_validator", lambda: validator
    )
    return validator


@pytest.fixture
def isolated_registry(monkeypatch):
    """Stub out agent_registry.get_registry() so a death in these tests
    never touches the real vector_memory.db `agent_history` table (one of
    the 5 sacred memory tables) via AgentRegistry.deregister()'s ghost
    persistence + successor spawn. AgentBase.die() resolves get_registry()
    via a local import at call time, so this is enough.
    """

    class _NoopRegistry:
        def deregister(self, agent_id):
            return None

    stub = _NoopRegistry()
    monkeypatch.setattr("core.city.agent_registry.get_registry", lambda: stub)
    return stub


class TestRoutineRepetitionNoLongerSaturates:
    """The core defect: identical-reason spam must not pin HP at 1000."""

    def test_identical_reason_repeated_does_not_pin_at_1000(self, isolated_validator):
        """Replays the exact production pattern: 'health_check_done' at
        +30HP, fired every tick. Old behaviour: agent hits 1000 within a
        couple dozen calls and every further call is a 1000->1000 no-op.
        """
        a = make_agent(hp=500)
        for _ in range(200):
            a.award_points(30, "health_check_done")
        assert a.health_points < 700, (
            f"agent pinned near the ceiling after 200 identical routine "
            f"awards: {a.health_points}"
        )
        # And it must be a genuine plateau, not a fluke — one more identical
        # award should still move it only a hair, never snap to 1000.
        before = a.health_points
        a.award_points(30, "health_check_done")
        assert a.health_points - before < 1.0

    def test_repeat_multiplier_strictly_decreases(self, isolated_validator):
        a = make_agent(hp=500)
        multipliers = []
        for _ in range(6):
            result = a.award_points(30, "same_reason")
            multipliers.append(result["repeat_multiplier"])
        for earlier, later in zip(multipliers, multipliers[1:]):
            assert later < earlier

    def test_validated_delta_never_increases_across_identical_repeats(
        self, isolated_validator
    ):
        a = make_agent(hp=500)
        deltas = []
        for _ in range(10):
            result = a.award_points(30, "seo_report_generated")
            deltas.append(result["validated_delta"])
        for earlier, later in zip(deltas, deltas[1:]):
            assert later <= earlier

    def test_novel_reason_each_time_keeps_full_repeat_multiplier(
        self, isolated_validator
    ):
        """Distinct reasons never share repeat history — an agent doing
        varied genuine work is not penalised just for being productive."""
        a = make_agent(hp=500)
        r1 = a.award_points(30, "reason_a")
        r2 = a.award_points(30, "reason_b")
        assert r1["repeat_multiplier"] == 1.0
        assert r2["repeat_multiplier"] == 1.0
        assert r1["repeat_count"] == 0
        assert r2["repeat_count"] == 0


class TestDifferentQualityDivergesInHP:
    """Two agents with genuinely different outcome profiles must land at
    genuinely different HP — this is what makes max(health_points) a
    meaningful tiebreak again in Governor.dispatch()."""

    def test_busy_routine_agent_vs_varied_genuine_agent(self, isolated_validator):
        busy = make_agent(name="BusyBot", hp=500)
        valuable = make_agent(name="ValuableBot", hp=500)

        # BusyBot: same routine tick, 60 times — exactly the production bug
        # pattern (health_check_done / seo_report_generated).
        for _ in range(60):
            busy.award_points(30, "health_check_done")

        # ValuableBot: 60 distinct genuine accomplishments at the same cadence
        # and the same per-event point value.
        for i in range(60):
            valuable.award_points(30, f"task_completed_distinct_{i}")

        assert valuable.health_points > busy.health_points
        gap = valuable.health_points - busy.health_points
        assert gap > 100, (
            f"expected a material HP gap between routine-only and "
            f"genuinely-varied agents, got {gap:.1f} "
            f"(busy={busy.health_points:.1f}, valuable={valuable.health_points:.1f})"
        )
        # BusyBot must not even be close to council/elite tier despite
        # running the same number of times as ValuableBot.
        assert busy.can_vote_in_council() is False

    def test_owner_approved_first_use_outweighs_routine_tick(
        self, isolated_validator
    ):
        """A +100 owner-approved award (novel, first-ever reason for this
        agent) should be worth noticeably more than a +30 routine tick at
        the same HP level — the documented economy stays recognisable for
        real signal, even though both pass through the same shaping."""
        routine = make_agent(name="RoutineBot", hp=500)
        approved = make_agent(name="ApprovedBot", hp=500)

        routine_result = routine.award_points(30, "health_check_done")
        approved_result = approved.award_points(100, "owner approved output")

        assert approved_result["validated_delta"] > routine_result["validated_delta"]


class TestHPStillClampsToValidRange:
    def test_award_never_pushes_hp_above_1000(self, isolated_validator):
        a = make_agent(hp=950)
        result = a.award_points(1_000_000, "huge one-off")
        assert result["new_hp"] == 1000
        assert a.health_points == 1000
        # Further oversized awards at the ceiling must stay in-range too.
        for _ in range(10):
            a.award_points(1_000_000, "huge one-off")
            assert 0 <= a.health_points <= 1000

    def test_deduct_never_pushes_hp_below_0(self, isolated_validator, isolated_registry):
        a = make_agent(hp=50)
        result = a.deduct_points(1_000_000, "catastrophic failure")
        assert result["new_hp"] == 0
        assert a.health_points == 0
        for _ in range(5):
            a.deduct_points(1_000_000, "catastrophic failure")
            assert 0 <= a.health_points <= 1000


class TestDeathStillTriggersAtZero:
    def test_deduct_to_zero_still_dies_and_preserves_ghost(
        self, isolated_validator, isolated_registry
    ):
        a = make_agent(hp=30)
        result = a.deduct_points(1_000_000, "lethal failure")
        assert a.health_points == 0
        assert result["died"] is True
        assert "ghost" in result
        assert result["ghost"]["final_hp"] == 0
        assert a.ghost_memory.get("final_hp") == 0
        assert "died_at" in a.ghost_memory

    def test_gradual_death_via_repeated_deducts_still_works(
        self, isolated_validator, isolated_registry
    ):
        a = make_agent(hp=100)
        died = False
        for _ in range(30):
            result = a.deduct_points(30, "repeated failure")
            if result["died"]:
                died = True
                break
        assert died is True
        assert a.health_points == 0


if __name__ == "__main__":
    # Real execution, no mocks of VECTOR internals (per testing.md) — run
    # the whole module through pytest's own runner so the isolation
    # fixtures above are honored even outside a `pytest` invocation.
    import sys
    raise SystemExit(pytest.main([__file__, "-v"]))
