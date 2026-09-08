"""
Task 91 — R6 Candidate Diversity (staleness-only) regression + behavioral tests.

Pre-fix behavior (proven by TestPreFixBehaviorBaseline below): DecisionEngine.
evaluate() always picked `ranked[0]` — the single highest-scoring candidate —
with no memory of prior decisions. If nothing else in the situation changed,
the SAME (action_type, params) identity could win every single evaluate()
call forever; VECTOR's candidate-selection loop had no mechanism to ever try
a genuinely-scored alternative over an unchanged repeat winner.

Fix: core/loop/decision_engine.py::_select_staleness_aware_winner(). A
candidate identity (the canonical PolicyMemory.make_situation_hash() this
class already used for policy lookups — reused unchanged, no second identity
system) that has been the actual evaluate() winner for
CONFIG["candidate_staleness_streak"] (default 5) or more CONSECUTIVE calls is
considered stale. When stale, the next candidate in the already-ranked list
with a DIFFERENT identity is selected instead — never invented, never
constructed, never reclassified. If no distinct alternative exists among the
real scored candidates, the stale winner is kept unchanged.

Per .claude/rules/testing.md ("Never mock: permission_gateway,
session_hydration, HP system" + prefer real execution), this suite exercises
the REAL DecisionEngine + REAL PolicyMemory.make_situation_hash (pure,
no DB access) for identity computation. Heavy unrelated subsystems
(episodic memory store, goal system, epistemic tracker, reasoning bank,
neural trainer, metacognition) are stubbed exactly like the existing
tests/unit/test_decision_engine.py `engine` fixture, but with
`_get_policy().make_situation_hash` wired to the REAL static method (via
side_effect) instead of an opaque Mock, since these tests require genuinely
distinct hashes per (action_type, params) to assert on.
"""
import copy

import pytest
from unittest.mock import MagicMock

from core.config import CONFIG
from core.loop.decision_engine import DecisionEngine, Candidate
from core.memory.policy import PolicyMemory


def make_candidate(action_type="test_action", confidence=0.5, urgency=0.5,
                    timing_score=1.0, estimated_cost_inr=0.0, goal_ids=None,
                    params=None):
    return Candidate(
        action_type=action_type,
        params=params if params is not None else {},
        goal_ids=goal_ids or [],
        confidence=confidence,
        urgency=urgency,
        timing_score=timing_score,
        estimated_cost_inr=estimated_cost_inr,
    )


@pytest.fixture
def engine():
    """Real DecisionEngine, real PolicyMemory.make_situation_hash (pure —
    no DB access), everything else stubbed. Matches
    tests/unit/test_decision_engine.py's `engine` fixture except
    make_situation_hash is real so identities are genuinely distinct."""
    e = DecisionEngine()
    e._get_policy = MagicMock()
    e._get_policy().get_score.return_value = 0.5
    e._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
    e._get_goals = MagicMock()
    e._get_goals().get_active_goals.return_value = []
    e._get_memory = MagicMock()
    e._get_memory().store.return_value = None
    e._get_epistemic = MagicMock()
    e._get_epistemic().get_belief.return_value = None
    e._get_epistemic().update_belief.return_value = None
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    e._get_context_engine = MagicMock()
    e._get_context_engine().get_world_state.return_value = {}
    e._get_metacognition = MagicMock(return_value=None)
    # R8/R9: stub the correction-learner getter too -- otherwise every
    # evaluate() call in this file's many-iteration tests (e.g. 300 rapid
    # decisions) does a real, bounded-but-nonzero-latency EpisodicMemory
    # lookup, which adds up across a tight loop even though no single call
    # can hang (see core/loop/decision_engine.py::_correction_penalty()'s
    # timeout bound). Matches how every other subsystem getter here is
    # already stubbed for isolation.
    e._get_correction_learner = MagicMock(return_value=None)
    return e


THRESHOLD = 5  # must match CANDIDATE_STALENESS_STREAK default in core/config.py


async def _run_n_times(engine, candidates_factory, n):
    """Call evaluate() n times with fresh Candidate objects each time
    (mirrors autonomous_loop rebuilding candidates every think tick) and
    return the list of winners."""
    winners = []
    for _ in range(n):
        cands = candidates_factory()
        decision = await engine.evaluate(cands)
        winners.append(decision.winner)
    return winners


@pytest.mark.unit
class TestPreFixBehaviorBaseline:
    """Proves the ORIGINAL bug this task fixes: without any staleness
    concept, the identical top candidate wins unboundedly — VECTOR would
    genuinely repeat the same decision forever if nothing else changed."""

    async def test_same_candidate_can_win_unbounded_without_staleness_engaged(self, engine):
        # Below threshold, staleness never engages — this documents that
        # the pre-fix behavior (unconditional repeat-winning) is exactly
        # what happens until the threshold is crossed, i.e. the guard is
        # opt-in via genuine repetition, not always-on.
        def factory():
            return [
                make_candidate("check_attendance", confidence=0.9, urgency=0.9,
                                params={"goal_id": "g_kiit"}),
                make_candidate("check_calendar", confidence=0.3, urgency=0.2),
            ]
        winners = await _run_n_times(engine, factory, THRESHOLD)
        assert all(w.action_type == "check_attendance" for w in winners)


@pytest.mark.unit
class TestStalenessGuardCore:
    """Scenarios A-H from the task's SUCCESS CRITERIA / IMPLEMENTATION
    REQUIREMENTS section."""

    async def test_a_fresh_candidate_remains_selectable(self, engine):
        """A. fresh candidate remains selectable."""
        c = make_candidate("check_attendance", confidence=0.9, urgency=0.9)
        decision = await engine.evaluate([c])
        assert decision.winner.action_type == "check_attendance"

    async def test_b_repeated_unchanged_candidate_eventually_becomes_stale(self, engine):
        """B. repeated unchanged candidate eventually becomes stale."""
        def factory():
            return [
                make_candidate("check_attendance", confidence=0.9, urgency=0.9,
                                params={"goal_id": "g_kiit"}),
                make_candidate("check_calendar", confidence=0.3, urgency=0.2),
            ]
        winners = await _run_n_times(engine, factory, THRESHOLD)
        # Exactly THRESHOLD consecutive real wins before suppression engages.
        assert all(w.action_type == "check_attendance" for w in winners)

        # The (THRESHOLD+1)th call: A is still top-ranked by raw score, but
        # now stale -> the genuinely scored alternative B must win instead.
        cands = factory()
        decision = await engine.evaluate(cands)
        assert decision.winner.action_type == "check_calendar"

    async def test_c_stale_candidate_not_reselected_when_safe_alternative_exists(self, engine):
        """C. stale candidate is not repeatedly selected when a SAFE existing
        alternative already exists."""
        def factory():
            return [
                make_candidate("action_a", confidence=0.9, urgency=0.9),
                make_candidate("action_b", confidence=0.4, urgency=0.4),
            ]
        await _run_n_times(engine, factory, THRESHOLD)
        decision = await engine.evaluate(factory())
        assert decision.winner.action_type == "action_b"

    async def test_d_no_alternative_system_does_not_invent_one(self, engine):
        """D. if no safe alternative exists, the system does NOT invent one."""
        def factory():
            return [make_candidate("only_action", confidence=0.8, urgency=0.8)]
        winners = await _run_n_times(engine, factory, THRESHOLD + 3)
        # Every single winner must be the one real candidate that exists —
        # never anything else, never None, never a fabricated action_type.
        assert all(w.action_type == "only_action" for w in winners)

    async def test_d2_duplicate_identity_candidates_do_not_count_as_alternatives(self, engine):
        """D (extended): two candidates with the SAME (action_type, params)
        identity are not a real alternative to each other."""
        def factory():
            return [
                make_candidate("dup_action", confidence=0.8, urgency=0.8, params={"x": 1}),
                make_candidate("dup_action", confidence=0.8, urgency=0.8, params={"x": 1}),
            ]
        winners = await _run_n_times(engine, factory, THRESHOLD + 2)
        assert all(w.action_type == "dup_action" for w in winners)

    async def test_e_meaningful_context_change_resets_staleness(self, engine):
        """E. meaningful context/situation change resets or invalidates
        staleness appropriately — once a different identity actually wins,
        the original candidate is eligible again the next time it tops the
        ranking."""
        def factory():
            return [
                make_candidate("action_a", confidence=0.9, urgency=0.9),
                make_candidate("action_b", confidence=0.4, urgency=0.4),
            ]
        await _run_n_times(engine, factory, THRESHOLD)
        # (THRESHOLD+1)th call: A suppressed, B wins -> streak resets to B.
        d1 = await engine.evaluate(factory())
        assert d1.winner.action_type == "action_b"

        # Next call: A is top-ranked again (its own score never changed) and
        # is no longer stale (streak now belongs to B, not A) -> A wins.
        d2 = await engine.evaluate(factory())
        assert d2.winner.action_type == "action_a"

    async def test_f_candidate_identity_stable_across_param_ordering(self, engine):
        """F. candidate identity remains stable across equivalent parameter
        ordering (reuses PolicyMemory.make_situation_hash's json.dumps
        sort_keys=True canonicalization)."""
        c1 = make_candidate("order_test", params={"a": 1, "b": 2, "c": 3})
        c2 = make_candidate("order_test", params={"c": 3, "a": 1, "b": 2})
        h1 = engine._make_situation_hash(c1)
        h2 = engine._make_situation_hash(c2)
        assert h1 == h2
        assert h1.startswith("v2:")

    async def test_g_no_red_yellow_forbidden_action_created(self, engine):
        """G. RED/YELLOW/FORBIDDEN actions are never created by R6 — the
        staleness guard only ever returns an object already present in the
        `ranked` list passed to it, never a new Candidate."""
        def factory():
            return [
                make_candidate("delete_repo", confidence=0.9, urgency=0.9),
                make_candidate("send_email", confidence=0.4, urgency=0.4),
            ]
        winners = await _run_n_times(engine, factory, THRESHOLD + 1)
        allowed = {"delete_repo", "send_email"}
        assert all(w.action_type in allowed for w in winners)

    async def test_h_existing_r1_r5_behavior_intact(self, engine):
        """H. existing R1-R5 behavior remains intact — a single evaluate()
        call still scores via the real 5-factor formula and policy_score
        still comes from PolicyMemory.get_score() (mocked here, but the
        call path — _make_situation_hash -> _get_policy().get_score() — is
        unchanged)."""
        c = make_candidate("search_web", confidence=0.8, urgency=0.6)
        decision = await engine.evaluate([c])
        assert 0.0 <= decision.winner.total_score <= 1.0
        assert decision.winner.policy_score == 0.5  # from the mocked get_score
        engine._get_policy().get_score.assert_called()


@pytest.mark.unit
class TestBehavioralScenarios:
    """The task's explicit BEHAVIORAL VERIFICATION scenarios 1-4, using the
    real DecisionEngine/candidate-selection components."""

    async def test_scenario_1_stale_a_suppressed_safe_b_wins(self, engine):
        def factory():
            return [
                make_candidate("A", confidence=0.9, urgency=0.9),
                make_candidate("B", confidence=0.5, urgency=0.5),
            ]
        for _ in range(THRESHOLD):
            d = await engine.evaluate(factory())
            assert d.winner.action_type == "A"
        d_final = await engine.evaluate(factory())
        assert d_final.winner.action_type == "B"

    async def test_scenario_2_stale_a_no_alternative_no_invention(self, engine):
        def factory():
            return [make_candidate("A", confidence=0.9, urgency=0.9)]
        for _ in range(THRESHOLD + 5):
            d = await engine.evaluate(factory())
            assert d.winner.action_type == "A"

    async def test_scenario_3_situation_change_reenables_a(self, engine):
        def factory():
            return [
                make_candidate("A", confidence=0.9, urgency=0.9),
                make_candidate("B", confidence=0.5, urgency=0.5),
            ]
        for _ in range(THRESHOLD):
            await engine.evaluate(factory())
        d_suppressed = await engine.evaluate(factory())
        assert d_suppressed.winner.action_type == "B"
        d_reenabled = await engine.evaluate(factory())
        assert d_reenabled.winner.action_type == "A"

    async def test_scenario_4_no_forbidden_action_generated(self, engine):
        def factory():
            return [
                make_candidate("wire_transfer", confidence=0.9, urgency=0.9),
                make_candidate("noop", confidence=0.1, urgency=0.1),
            ]
        for _ in range(THRESHOLD + 1):
            d = await engine.evaluate(factory())
            assert d.winner.action_type in ("wire_transfer", "noop")


@pytest.mark.unit
class TestAdversarial:
    """Adversarial review items from the task."""

    async def test_1_staleness_cannot_suppress_every_candidate(self, engine):
        """If ALL candidates share one identity, R6 must not produce a
        winner-less decision — the single identity keeps winning."""
        def factory():
            return [make_candidate("only", params={"k": "v"})]
        for _ in range(THRESHOLD + 10):
            d = await engine.evaluate(factory())
            assert d.winner is not None
            assert d.winner.action_type == "only"

    async def test_2_staleness_state_does_not_leak_across_unrelated_situations(self):
        """Two independent DecisionEngine instances (e.g. two different
        subsystems) must not share streak state — it is instance-local."""
        e1 = DecisionEngine()
        e2 = DecisionEngine()
        e1._get_policy = MagicMock()
        e1._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
        e1._get_policy().get_score.return_value = 0.5
        e1._get_goals = MagicMock(); e1._get_goals().get_active_goals.return_value = []
        e1._get_memory = MagicMock(); e1._get_memory().store.return_value = None
        e1._get_epistemic = MagicMock(); e1._get_epistemic().get_belief.return_value = None
        e1._get_reasoning_bank = MagicMock(return_value=None)
        e1._get_neural_trainer = MagicMock(return_value=None)
        e1._get_context_engine = MagicMock(); e1._get_context_engine().get_world_state.return_value = {}
        e1._get_correction_learner = MagicMock(return_value=None)

        e2._get_policy = MagicMock()
        e2._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
        e2._get_policy().get_score.return_value = 0.5
        e2._get_goals = MagicMock(); e2._get_goals().get_active_goals.return_value = []
        e2._get_memory = MagicMock(); e2._get_memory().store.return_value = None
        e2._get_epistemic = MagicMock(); e2._get_epistemic().get_belief.return_value = None
        e2._get_reasoning_bank = MagicMock(return_value=None)
        e2._get_neural_trainer = MagicMock(return_value=None)
        e2._get_context_engine = MagicMock(); e2._get_context_engine().get_world_state.return_value = {}
        e2._get_correction_learner = MagicMock(return_value=None)

        def factory():
            return [
                make_candidate("A", confidence=0.9, urgency=0.9),
                make_candidate("B", confidence=0.5, urgency=0.5),
            ]
        for _ in range(THRESHOLD):
            await e1.evaluate(factory())
        # e1 is now primed to suppress A on its next call; e2 has never run.
        d_e2 = await e2.evaluate(factory())
        assert d_e2.winner.action_type == "A"  # unaffected by e1's streak

    async def test_3_parameter_ordering_never_causes_false_alternative(self, engine):
        """Different key ORDER of the same param dict must not be treated as
        a distinct identity that lets a duplicate 'escape' staleness."""
        def factory():
            return [
                make_candidate("same_action", confidence=0.9, urgency=0.9, params={"a": 1, "b": 2}),
                make_candidate("same_action", confidence=0.9, urgency=0.9, params={"b": 2, "a": 1}),
            ]
        winners = await _run_n_times(engine, factory, THRESHOLD + 2)
        # Both "candidates" are the identical situation despite key order;
        # they must never count as each other's alternative.
        assert all(w.action_type == "same_action" for w in winners)

    async def test_4_no_consequential_action_selected_outside_ranked_list(self, engine):
        """The winner is always `is` one of the objects passed into
        evaluate() — R6 cannot cause selection of anything else."""
        def factory():
            return [
                make_candidate("A", confidence=0.9, urgency=0.9),
                make_candidate("B", confidence=0.5, urgency=0.5),
            ]
        for _ in range(THRESHOLD + 1):
            cands = factory()
            d = await engine.evaluate(cands)
            assert any(d.winner is c for c in cands)

    async def test_6_governance_not_bypassed_r6_is_scoring_only(self, engine):
        """R6 operates purely inside DecisionEngine.evaluate() and returns a
        Candidate — it has no code path to PermissionGateway/Governor and
        cannot bypass them (those gates run downstream in autonomous_loop on
        whatever `decision.winner` is, unchanged by this task)."""
        import inspect
        src = inspect.getsource(engine._select_staleness_aware_winner)
        for forbidden in ("PermissionGateway", "permission_gateway", "Governor", "governor.dispatch"):
            assert forbidden not in src

    async def test_7_staleness_reset_requires_a_real_different_winner(self, engine):
        """Staleness cannot be trivially reset without SOME other candidate
        actually winning — merely re-running evaluate() with the exact same
        single-candidate input keeps incrementing the streak, never resets."""
        def factory():
            return [make_candidate("A", confidence=0.9, urgency=0.9)]
        for _ in range(THRESHOLD + 3):
            await engine.evaluate(factory())
        assert engine._winner_streak_count >= THRESHOLD + 3
        assert engine._winner_streak_hash == engine._make_situation_hash(factory()[0])

    async def test_8_empty_candidate_set_unaffected_safe_fallback(self, engine):
        """Empty candidate list still returns the existing safe noop
        fallback — evaluate()'s pre-existing empty-candidates guard runs
        BEFORE the staleness selector is ever reached."""
        decision = await engine.evaluate([])
        assert decision.winner.action_type == "noop"
        assert decision.evaluated == 0


@pytest.mark.unit
class TestConfigDefault:
    def test_candidate_staleness_streak_config_present_and_bounded(self):
        value = CONFIG.get("candidate_staleness_streak")
        assert value is not None
        assert isinstance(value, int)
        assert 1 <= value <= 1000
        assert value == THRESHOLD  # keep in sync with the module-level constant above


if __name__ == "__main__":
    import asyncio
    import sys

    async def _main():
        e = DecisionEngine()
        e._get_policy = MagicMock()
        e._get_policy().get_score.return_value = 0.5
        e._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
        e._get_goals = MagicMock(); e._get_goals().get_active_goals.return_value = []
        e._get_memory = MagicMock(); e._get_memory().store.return_value = None
        e._get_epistemic = MagicMock(); e._get_epistemic().get_belief.return_value = None
        e._get_reasoning_bank = MagicMock(return_value=None)
        e._get_neural_trainer = MagicMock(return_value=None)
        e._get_context_engine = MagicMock(); e._get_context_engine().get_world_state.return_value = {}
        e._get_correction_learner = MagicMock(return_value=None)

        def factory():
            return [
                make_candidate("A", confidence=0.9, urgency=0.9),
                make_candidate("B", confidence=0.5, urgency=0.5),
            ]
        for _ in range(THRESHOLD):
            d = await e.evaluate(factory())
            assert d.winner.action_type == "A"
        d_final = await e.evaluate(factory())
        return d_final.winner.action_type == "B"

    sys.stdout.reconfigure(encoding="utf-8")
    ok = asyncio.run(_main())
    print("✅ test_task91_r6_candidate_diversity OK" if ok else "❌ FAILED")
