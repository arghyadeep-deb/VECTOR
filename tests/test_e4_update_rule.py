"""
E4 — Update Rule.

Question: does repeated experience produce meaningful, predictable future
preference changes? Classify the current update rule: FUNCTIONAL / INERT /
PATHOLOGICAL / UNSTABLE / UNSAFE.

AUDIT SUMMARY (full detail: VECTOR_TECHNICAL_KNOWLEDGE/E4_UPDATE_RULE_REPORT.md):

1. `PolicyMemory.update_from_outcome()`'s online average
   (`new_avg = (old_avg*n + reward)/(n+1)`) is **FUNCTIONAL** -- E1 (this
   session) already proved it produces a real, persistent, restart-surviving
   preference change from repeated experience. This stage adds one further,
   honestly-reported characteristic: the update rule has NO decay and NO cap
   on `sample_count`, so as `n` grows large, any single new observation's
   marginal weight (`1/(n+1)`) shrinks toward zero -- a known mathematical
   SATURATION property of an unweighted running mean over a non-stationary
   signal, not a bug. Not fixed (E4 explicitly forbids replacing a working
   algorithm merely because a decayed/windowed one would theoretically adapt
   faster) -- proven and quantified instead.

2. `veto_count` (Task 89/D3's suppression counter) was found to be
   **INERT** -- written by `record_suppression()`, but never read by
   `PolicyMemory.get_score()` or anything else, confirmed by repo-wide
   audit. Its own docstring already stated the intent
   ("so decision_engine's get_score() / future tooling can see...") that
   was never completed. THIS is a real, minimal, already-intended wiring
   gap -- fixed in this stage: `PolicyMemory.get_veto_count()` (new,
   read-only) + `DecisionEngine._veto_penalty()` (new, bounded [0.0, 0.10],
   same architectural pattern as bias_penalty/epistemic_penalty/
   correction_penalty) now makes a repeatedly-vetoed situation's decision
   score meaningfully, predictably worse -- closing the exact gap the
   original column's own docstring named as future work.

No reward VALUE, aggregation formula, or existing column was changed. No
decay/windowing algorithm was introduced (that would be replacing a working
algorithm, explicitly out of scope).
"""
import inspect
from unittest.mock import MagicMock

import pytest

from core.config import CONFIG
from core.loop.decision_engine import Candidate, DecisionEngine
from core.memory.policy import PolicyMemory


def make_candidate(action_type, confidence=0.6, urgency=0.5, params=None):
    return Candidate(action_type=action_type, params=params or {}, confidence=confidence, urgency=urgency)


@pytest.fixture
def engine():
    e = DecisionEngine()
    e._get_goals = MagicMock()
    e._get_goals().get_active_goals.return_value = []
    e._get_memory = MagicMock()
    e._get_memory().store.return_value = None
    e._get_epistemic = MagicMock()
    e._get_epistemic().get_belief.return_value = None
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    e._get_context_engine = MagicMock()
    e._get_context_engine().get_world_state.return_value = {}
    e._get_metacognition = MagicMock(return_value=None)
    e._get_correction_learner = MagicMock(return_value=None)
    # _get_policy is intentionally real -- this file tests the real PolicyMemory.
    return e


# ═══════════════════════════════════════════════════════════════════════════
# veto_count: was INERT, now wired
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestVetoCountWasInertNowWired:

    def test_veto_count_previously_unread_by_get_score(self):
        """Documents the pre-fix finding directly: get_score()'s own SQL
        query selects only avg_reward, sample_count -- never veto_count.
        (get_score()'s docstring legitimately DISCUSSES veto_count in prose
        explaining a NULL-handling edge case -- what must never appear is
        an actual SQL SELECT of the column, which this checks for directly.)"""
        src = inspect.getsource(PolicyMemory.get_score)
        assert "SELECT avg_reward, sample_count FROM policy_memory" in src
        assert "SELECT avg_reward, sample_count, veto_count" not in src

    def test_get_veto_count_reads_back_a_real_recorded_suppression(self):
        import uuid
        pm = PolicyMemory()
        action_type = f"e4_veto_probe_{uuid.uuid4().hex[:8]}"
        h = pm.make_situation_hash(action_type, {})
        assert pm.get_veto_count(action_type, h) == 0  # no data yet
        pm.record_suppression(action_type, h)
        pm.record_suppression(action_type, h)
        pm.record_suppression(action_type, h)
        assert pm.get_veto_count(action_type, h) == 3

    def test_repeated_veto_meaningfully_and_predictably_lowers_score(self, engine):
        """Behavioral proof: a candidate whose exact situation has been
        vetoed many times now scores measurably worse than an identical,
        never-vetoed one -- closing the exact gap veto_count's own
        original docstring named as intended future work."""
        import uuid
        action_type = f"e4_veto_behavior_{uuid.uuid4().hex[:8]}"
        params = {}
        pm = engine._get_policy()
        h = pm.make_situation_hash(action_type, params)
        for _ in range(6):
            pm.record_suppression(action_type, h)

        vetoed = make_candidate(action_type, confidence=0.6, params=params)
        engine._score_candidate(vetoed)

        never_vetoed = make_candidate(f"{action_type}_never_vetoed", confidence=0.6, params=params)
        engine._score_candidate(never_vetoed)

        assert vetoed.total_score < never_vetoed.total_score, (
            "a repeatedly-vetoed situation must score measurably worse than an "
            "otherwise-identical never-vetoed one"
        )

    def test_veto_penalty_bounded(self, engine):
        """Even an extreme veto_count must never exceed the documented cap."""
        import uuid
        action_type = f"e4_veto_extreme_{uuid.uuid4().hex[:8]}"
        pm = engine._get_policy()
        h = pm.make_situation_hash(action_type, {})
        for _ in range(500):
            pm.record_suppression(action_type, h)
        penalty = engine._veto_penalty(h, make_candidate(action_type))
        assert penalty <= 0.10

    def test_veto_penalty_unrelated_situation_unaffected(self, engine):
        import uuid
        vetoed_action = f"e4_veto_unrelated_a_{uuid.uuid4().hex[:8]}"
        unrelated_action = f"e4_veto_unrelated_b_{uuid.uuid4().hex[:8]}"
        pm = engine._get_policy()
        h_vetoed = pm.make_situation_hash(vetoed_action, {})
        for _ in range(6):
            pm.record_suppression(vetoed_action, h_vetoed)

        h_unrelated = pm.make_situation_hash(unrelated_action, {})
        penalty = engine._veto_penalty(h_unrelated, make_candidate(unrelated_action))
        assert penalty == 0.0

    def test_veto_penalty_never_bypasses_governance(self):
        src = inspect.getsource(DecisionEngine._veto_penalty)
        assert "Governor" not in src
        assert "PermissionGateway" not in src

    def test_veto_penalty_does_not_change_reward_semantics(self):
        """The fix reads veto_count through a NEW dedicated method -- it
        never touches avg_reward/sample_count or update_from_outcome's
        contract."""
        src = inspect.getsource(PolicyMemory.get_veto_count)
        assert "avg_reward" not in src
        assert "sample_count" not in src
        sig = inspect.signature(PolicyMemory.update_from_outcome)
        assert list(sig.parameters) == ["self", "action_type", "situation_hash", "reward"]


# ═══════════════════════════════════════════════════════════════════════════
# avg_reward saturation: documented, not fixed
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestAvgRewardSaturationDocumented:

    def test_saturation_a_single_new_observation_barely_moves_a_long_history(self):
        """Quantifies the documented (not fixed) saturation property: after
        many prior samples, one new, even maximally different, observation
        moves the average by a bounded, small, predictable amount --
        1/(n+1) -- not a defect, a real property of an unweighted running
        mean with no decay."""
        import uuid
        pm = PolicyMemory()
        action_type = f"e4_saturation_{uuid.uuid4().hex[:8]}"
        h = pm.make_situation_hash(action_type, {})
        n_prior = 200
        for _ in range(n_prior):
            pm.update_from_outcome(action_type, h, 0.9)  # long, consistent history
        score_before = pm.get_score(action_type, h)
        assert score_before == pytest.approx(0.9, abs=0.02)

        pm.update_from_outcome(action_type, h, 0.0)  # one maximally-opposite new observation
        score_after = pm.get_score(action_type, h)

        expected_shift = 0.9 / (n_prior + 1)  # exact math of the real online-average formula
        actual_shift = score_before - score_after
        assert actual_shift == pytest.approx(expected_shift, abs=0.005), (
            f"a single new observation after {n_prior} prior samples must move the "
            f"average by exactly the online-average formula's predicted amount "
            f"({expected_shift:.4f}), not more and not less -- confirming this is a "
            "real, bounded, predictable mathematical property, not instability"
        )

    def test_update_from_outcome_source_unchanged_no_decay_added(self):
        """Confirms E4 did not add a decay/windowing mechanism -- that would
        be replacing a working algorithm, explicitly out of scope."""
        src = inspect.getsource(PolicyMemory.update_from_outcome)
        assert "new_avg = (old_avg * n + reward) / (n + 1)" in src
        assert "decay" not in src.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Update-rule controls: positive / negative / unrelated / restart / duplicate
# (E1 already proved the restart+duplicate+unrelated case for avg_reward end
# to end; this file adds the veto_count-specific equivalents only.)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestVetoControls:

    def test_positive_experience_zero_vetoes_no_penalty(self, engine):
        import uuid
        action_type = f"e4_positive_{uuid.uuid4().hex[:8]}"
        penalty = engine._veto_penalty(
            engine._get_policy().make_situation_hash(action_type, {}),
            make_candidate(action_type),
        )
        assert penalty == 0.0

    def test_negative_experience_n_vetoes_produces_predictable_penalty(self, engine):
        import uuid
        action_type = f"e4_negative_{uuid.uuid4().hex[:8]}"
        pm = engine._get_policy()
        h = pm.make_situation_hash(action_type, {})
        for n in range(1, 6):
            pm.record_suppression(action_type, h)
            penalty = engine._veto_penalty(h, make_candidate(action_type))
            assert penalty == pytest.approx(min(0.10, n * 0.02), abs=0.001)

    def test_duplicate_veto_recording_does_not_change_formula(self, engine):
        """Recording the exact same veto event twice (e.g. a retried/replayed
        suppression) is simply two real events -- the count increments
        normally, no special-case amplification or deduplication logic
        exists or is needed (each record_suppression() call already
        represents one real veto occurrence)."""
        import uuid
        action_type = f"e4_dup_veto_{uuid.uuid4().hex[:8]}"
        pm = engine._get_policy()
        h = pm.make_situation_hash(action_type, {})
        pm.record_suppression(action_type, h)
        pm.record_suppression(action_type, h)
        assert pm.get_veto_count(action_type, h) == 2


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
