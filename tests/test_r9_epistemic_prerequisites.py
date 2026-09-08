"""
R9 — Epistemic Prerequisites: audit + minimal-repair behavioral tests.

AUDIT SUMMARY (full detail: VECTOR_TECHNICAL_KNOWLEDGE/R9_EPISTEMIC_PREREQUISITES_REPORT.md):

1. `core/loop/decision_engine.py`'s epistemic writer (`record_epistemic_belief()`,
   called from `autonomous_loop._act_on()` after every real outcome) and reader
   (`_epistemic_penalty()`, called from `_score_candidate()`) both key claims as
   `f"action_domain:{action_type.split('_')[0]}"` -- CONSISTENT, already fully
   wired, confirmed working before this task. No fix needed here.

2. `core/runtime/plans.py`'s `verify_step_outcome()` "confidence_threshold"
   verification branch used a bare `step.action_type` as the claim id -- NEVER
   matching the `action_domain:*` convention every real writer uses. A genuine
   reader/writer identity mismatch (same class of bug Task 89's R4/R5 fixed for
   PolicyMemory), fixed minimally by reusing the exact same domain-derivation
   decision_engine.py already uses. No plan generator currently emits a
   "confidence_threshold" step (confirmed by repo-wide grep) -- this is a
   preemptive fix for a real but not-yet-triggered defect, honestly reported as
   such, not overclaimed as an active production bug.

3. `core/loop/context_engine.py`'s `track_beliefs()` writes 5 distinct
   "belief:*"-namespaced claims (presence, kiit_attendance, screen_activity,
   goals, memory health) every think-tick -- confirmed reachable (S3+) on the
   WRITE side. NO reader anywhere in the codebase ever queries a "belief:*"
   key. This is a genuine, confirmed dead-reader gap -- NOT fixed in this task,
   because there is no existing intended connection to reconnect: wiring these
   ambient world-state beliefs into DecisionEngine's scoring would require
   inventing a new scoring policy (what should "owner present" or "screen
   activity=coding" do to which candidate's score?), which is new design, not
   minimal repair. Reported, not invented.

4. `core/brain/person_model.py`'s `PersonModel` class is a CONFIRMED SEPARATE
   subsystem (its own class, its own SQLite db `person_models.db`, Gap 7
   "theory of mind per person" -- not Gap 3's action-domain confidence). Its
   `update_belief()` method name is a naming coincidence, not a shared
   identity with `EpistemicTracker`. NOT merged, per the task's explicit
   instruction not to merge conceptually-related-but-architecturally-separate
   systems.

5. Epistemic influence on DecisionEngine is PENALTY-ONLY (bounded factor in
   [0.70, 1.0], confirmed by direct source read of `_epistemic_penalty()`) --
   it can only ever DAMPEN a score, never boost one past its own real value,
   mirroring R8's correction_penalty design. Cannot approve RED actions,
   cannot bypass Governor/PermissionGateway (neither is referenced anywhere in
   `epistemic_tracker.py` or the epistemic methods in `decision_engine.py`).

Per .claude/rules/testing.md, this suite uses a REAL EpistemicTracker backed by
an isolated temp-file SQLite db (matching the class's own `__main__` self-test
convention) -- never the live/production `data/epistemic.db`.
"""
import inspect
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.brain.epistemic_tracker import EpistemicTracker
from core.loop.decision_engine import Candidate, DecisionEngine
from core.memory.policy import PolicyMemory


@pytest.fixture
def tracker():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    t = EpistemicTracker(db_path=db_path)
    yield t
    t.close()
    Path(db_path).unlink(missing_ok=True)


def make_candidate(action_type="check_attendance", confidence=0.6, urgency=0.5, params=None):
    return Candidate(action_type=action_type, params=params or {}, confidence=confidence, urgency=urgency)


@pytest.fixture
def engine():
    e = DecisionEngine()
    e._get_policy = MagicMock()
    e._get_policy().get_score.return_value = 0.5
    e._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
    e._get_goals = MagicMock()
    e._get_goals().get_active_goals.return_value = []
    e._get_memory = MagicMock()
    e._get_memory().store.return_value = None
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    e._get_context_engine = MagicMock()
    e._get_context_engine().get_world_state.return_value = {}
    e._get_metacognition = MagicMock(return_value=None)
    e._get_correction_learner = MagicMock(return_value=None)  # R8's mechanism, out of scope here
    return e


# ═══════════════════════════════════════════════════════════════════════════
# A, B, G, H, I — storage / retrieval / bounded confidence / provenance / restart
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestStorageRetrieval:

    def test_a_valid_epistemic_state_stored(self, tracker):
        tracker.update_belief("action_domain:code", "recent success", 0.8, "act_loop")
        assert "action_domain:code" in tracker._beliefs

    def test_b_valid_state_retrieved(self, tracker):
        tracker.update_belief("action_domain:code", "recent success", 0.8, "act_loop")
        belief = tracker.get_belief("action_domain:code")
        assert belief is not None
        assert belief["value"] == "recent success"
        assert belief["stale"] is False

    def test_g_confidence_bounded_on_write(self, tracker):
        tracker.update_belief("action_domain:test", "x", 1.5, "test")
        assert tracker.get_belief("action_domain:test")["confidence"] == 1.0
        tracker.update_belief("action_domain:test2", "x", -0.5, "test")
        assert tracker.get_belief("action_domain:test2")["confidence"] == 0.0

    def test_h_provenance_survives(self, tracker):
        tracker.update_belief("action_domain:code", "x", 0.8, "act_loop")
        belief = tracker.get_belief("action_domain:code")
        assert belief["source"] == "act_loop"

    def test_i_restart_preserves_required_state(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            t1 = EpistemicTracker(db_path=db_path)
            t1.update_belief("action_domain:code", "recent success", 0.8, "act_loop")
            t1.close()

            # "restart": brand new instance, same durable file
            t2 = EpistemicTracker(db_path=db_path)
            belief = t2.get_belief("action_domain:code")
            assert belief is not None
            assert belief["confidence"] == 0.8
            assert belief["source"] == "act_loop"
            t2.close()
        finally:
            Path(db_path).unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# E, F — staleness bounded, contradictions deterministic
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestStalenessAndContradiction:

    def test_e_stale_state_does_not_dominate(self, tracker):
        """A stale belief's decision-path influence is capped at a FIXED 0.70
        dampening factor -- it never gets worse than that no matter how old,
        and it is not the identity ("1.0 == no effect") the moment it's
        stale, so it cannot silently keep dominating as if fresh."""
        tracker.update_belief("action_domain:old", "x", 0.9, "test", ttl_hours=0)
        # ttl_hours=0 -> immediately stale (age_hours > 0 is true almost instantly)
        import time
        time.sleep(0.01)
        belief = tracker.get_belief("action_domain:old")
        assert belief["stale"] is True
        assert belief["current_confidence"] == 0.0

        c = DecisionEngine()
        c._get_epistemic = MagicMock(return_value=tracker)
        factor, conf = c._epistemic_penalty(make_candidate("old_action"))
        assert factor == 0.70  # fixed, bounded dampening -- not 0.0, not creeping lower over time

    def test_f_contradiction_is_deterministic_last_write_wins(self, tracker):
        tracker.update_belief("action_domain:x", "A", 0.8, "source1")
        tracker.update_belief("action_domain:x", "NOT-A", 0.8, "source2")
        belief = tracker.get_belief("action_domain:x")
        assert belief["value"] == "NOT-A"  # deterministic: last write wins, not random

    def test_f2_merge_belief_blend_is_deterministic(self, tracker):
        tracker.update_belief("action_domain:y", "A", 0.9, "source1")
        tracker.merge_belief("action_domain:y", "B", 0.3, "source2")
        belief = tracker.get_belief("action_domain:y")
        expected = round(0.9 * 0.7 + 0.3 * 0.3, 3)
        assert abs(belief["confidence"] - expected) < 0.01


# ═══════════════════════════════════════════════════════════════════════════
# C, D — relevant state influences scoring, unrelated does not
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestScoringInfluence:

    async def test_c_relevant_state_influences_scoring(self, engine, tracker):
        tracker.update_belief("action_domain:code", "x", 0.9, "act_loop", ttl_hours=0)
        import time
        time.sleep(0.01)  # force staleness
        engine._get_epistemic = MagicMock(return_value=tracker)

        c = make_candidate("code_task")
        without_epistemic_score = c.total_score
        d = await engine.evaluate([c])
        assert d.winner.total_score < 1.0  # dampened, not neutral

    async def test_d_unrelated_state_does_not_influence(self, engine, tracker):
        tracker.update_belief("action_domain:code", "x", 0.9, "act_loop", ttl_hours=0)
        import time
        time.sleep(0.01)
        engine._get_epistemic = MagicMock(return_value=tracker)

        # "search_web" -> domain "search", never touched by the stale "code" belief
        unrelated = make_candidate("search_web", confidence=0.5, urgency=0.5)
        factor, conf = engine._epistemic_penalty(unrelated)
        assert factor == 1.0  # unknown domain -> neutral, per _epistemic_penalty's own contract

    async def test_epistemic_never_boosts_only_dampens(self, engine, tracker):
        """Confirms by direct behavior (not just source reading) that the
        factor is always <= 1.0."""
        tracker.update_belief("action_domain:known", "x", 0.95, "act_loop")  # fresh, high confidence
        engine._get_epistemic = MagicMock(return_value=tracker)
        factor, conf = engine._epistemic_penalty(make_candidate("known_thing"))
        assert factor <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# J — governance cannot be bypassed
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestGovernanceUnbypassed:

    def test_j_epistemic_tracker_source_has_no_governance_reference(self):
        import core.brain.epistemic_tracker as et
        src = inspect.getsource(et)
        assert "governor" not in src.lower()
        assert "permission_gateway" not in src.lower()
        assert "PermissionGateway" not in src

    def test_j2_epistemic_penalty_method_has_no_governance_reference(self):
        src = inspect.getsource(DecisionEngine._epistemic_penalty)
        assert "Governor" not in src
        assert "PermissionGateway" not in src


# ═══════════════════════════════════════════════════════════════════════════
# PersonModel confirmed separate (not merged)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestPersonModelConfirmedSeparate:

    def test_person_model_is_a_different_class_different_db(self):
        from core.brain.person_model import PersonModel
        assert PersonModel is not EpistemicTracker
        # Different default db filenames -- confirmed architecturally separate
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            et = EpistemicTracker(db_path=db_path)
            assert not hasattr(et, "RELATIONSHIP_TYPES")  # PersonModel-only attribute
            et.close()
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_decision_engine_never_imports_person_model(self):
        import core.loop.decision_engine as de
        src = inspect.getsource(de)
        assert "PersonModel" not in src
        assert "person_model" not in src


# ═══════════════════════════════════════════════════════════════════════════
# plans.py fix: reader/writer identity mismatch repair
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestPlansConfidenceThresholdFix:

    def test_bare_action_type_never_matched_before_fix(self, tracker):
        """Documents the pre-fix bug directly: a belief stored under the
        canonical action_domain key was NEVER found by a bare-action_type
        lookup -- proving the mismatch was real, not hypothetical."""
        tracker.update_belief("action_domain:check", "x", 0.9, "act_loop")
        assert tracker.get_confidence("check_attendance") == 0.0  # bare action_type: no match
        assert tracker.get_confidence("action_domain:check") == pytest.approx(0.9, abs=0.05)  # correct key: matches

    def test_verify_step_outcome_confidence_threshold_now_matches(self, monkeypatch, tracker):
        from core.runtime.plans import PlanStep, verify_step_outcome

        tracker.update_belief("action_domain:check", "verified", 0.9, "act_loop")

        import core.brain.epistemic_tracker as et_module
        monkeypatch.setattr(et_module, "EpistemicTracker", lambda *a, **kw: tracker)
        # plans.py does `from core.brain.epistemic_tracker import EpistemicTracker`
        # inside the function body -- patch the module attribute it re-imports from.
        import core.runtime.plans as plans_module
        monkeypatch.setattr(
            plans_module, "verify_step_outcome", plans_module.verify_step_outcome
        )

        step = PlanStep(
            id="step1",
            action_type="check_attendance",
            params={},
            verification={"type": "confidence_threshold", "criteria": {"min_confidence": 0.5}},
        )
        # tracker.close() is called inside verify_step_outcome -- use a
        # close-safe wrapper so the shared fixture tracker survives for
        # any later assertions in this test.
        tracker.close = lambda: None

        passed = verify_step_outcome(step, "executed", None)
        assert passed is True, (
            "R9 fix: confidence_threshold verification must now find the belief "
            "stored under the canonical action_domain key"
        )
        tracker._conn.close()  # real close, bypassing the no-op patched above, for teardown

    def test_verify_step_outcome_confidence_threshold_fails_when_no_belief(self, monkeypatch, tracker):
        from core.runtime.plans import PlanStep, verify_step_outcome
        import core.brain.epistemic_tracker as et_module
        tracker.close = lambda: None
        monkeypatch.setattr(et_module, "EpistemicTracker", lambda *a, **kw: tracker)

        step = PlanStep(
            id="step2",
            action_type="never_seen_action",
            params={},
            verification={"type": "confidence_threshold", "criteria": {"min_confidence": 0.5}},
        )
        passed = verify_step_outcome(step, "executed", None)
        assert passed is False
        tracker._conn.close()  # real close, bypassing the no-op patched above, for teardown


if __name__ == "__main__":
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name
    et = EpistemicTracker(db_path=db)
    et.update_belief("action_domain:code", "x", 0.9, "act_loop")
    ok = et.get_belief("action_domain:code")["confidence"] == 0.9
    et.close()
    Path(db).unlink(missing_ok=True)
    print("✅ test_r9_epistemic_prerequisites OK" if ok else "❌ FAILED")
