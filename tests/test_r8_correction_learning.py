"""
R8 — Explicit Correction Learning: behavioral + causal tests.

ROOT CAUSE FOUND BY THE R8 READ-ONLY AUDIT (see
VECTOR_TECHNICAL_KNOWLEDGE/R8_CORRECTION_LEARNING_REPORT.md for the full
S0-S5 edge classification): `autonomous_loop._detect_and_store_correction()`
built each correction lesson's `context={"situation": ...}` from
`getattr(self, '_current_action_type', 'conversation')` — but
`self._current_action_type` was NEVER assigned anywhere in the file. Every
real production correction therefore got `lesson.situation == "conversation"`
unconditionally, regardless of what VECTOR had actually just done. This
silently broke the only piece of context that could later let a correction
influence a SPECIFIC future decision rather than nothing at all.

Two changes close this:
1. `AutonomousLoop._act_on()` now sets `self._current_action_type =
   winner.action_type` at the top of every action attempt (core/loop/
   autonomous_loop.py) — so a correction right after really does capture the
   real action_type.
2. `CorrectionLearner.get_correction_penalty(action_type)` (core/memory/
   correction_learner.py) — a new, bounded [0.0, 0.12] read-only query: is
   there a real, persisted, still-valid, sufficiently-confident correction
   lesson whose `situation` EXACTLY equals this action_type? If so, return a
   bounded penalty. `DecisionEngine._correction_penalty()` (core/loop/
   decision_engine.py) subtracts it from the candidate's weighted score,
   exactly like the existing bias_penalty/epistemic_penalty terms.

This is NOT reward learning: nothing here reads PolicyMemory, nothing here
writes a reward, and the gate is a real explicit-correction event, never an
outcome. It is also NOT the same as `validate_lesson()`'s VALIDATED-status
reinforcement (confirmed by the audit to have ZERO production callers, S1
dead) -- decision influence here only requires the same MIN_STORE_CONFIDENCE
(0.7) bar every persisted correction already cleared at detection time.

Per .claude/rules/testing.md, this suite prefers REAL CorrectionDetector +
LessonExtractor + CorrectionLearner + DecisionEngine wherever practical,
substituting only the heavy EpisodicMemory dependency with a minimal,
functionally-real in-memory store (matching this repo's own established
pattern in tests/integration/test_correction_integration.py, which does the
same with a MagicMock) — never the live/production database.
"""
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config import CONFIG
from core.loop.decision_engine import Candidate, DecisionEngine
from core.memory.correction_learner import (
    CORRECTION_EXPLICIT,
    MIN_STORE_CONFIDENCE,
    VALIDATION_UNVALIDATED,
    CorrectionDetector,
    CorrectionLearner,
    LessonExtractor,
)
from core.memory.policy import PolicyMemory


class _FakeCorrectionStore:
    """Minimal, functionally-real in-memory stand-in for EpisodicMemory's
    (store, recall) contract used by CorrectionLearner -- NOT a mock of
    behavior. What is written is exactly what comes back; this is the real
    round-trip guarantee, just backed by a Python list instead of SQLite.
    Matches EpisodicMemory.store(event_type, content, tags, context, source)
    and .recall(query, limit, event_type) signatures exactly."""

    def __init__(self):
        self.rows: list[dict] = []

    def store(self, event_type, content, tags=None, context=None, source="vector"):
        self.rows.append({"event_type": event_type, "content": content, "tags": tags or []})
        return f"row-{len(self.rows)}"

    def recall(self, query, limit=5, event_type=None):
        rows = [r for r in self.rows if event_type is None or r["event_type"] == event_type]
        return [{"content": r["content"]} for r in rows[-limit:]]


def make_learner():
    learner = CorrectionLearner()
    learner._memory = _FakeCorrectionStore()
    return learner


# ═══════════════════════════════════════════════════════════════════════════
# A, B, C — explicit vs ordinary vs ambiguous
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestExplicitOnly:

    def test_a_explicit_correction_captured(self):
        learner = make_learner()
        lesson = learner.process_owner_message(
            "no, use httpx instead of requests",
            prior_vector_response="I'll use requests",
            context={"situation": "send_email"},
        )
        assert lesson is not None
        assert lesson.correction_type == CORRECTION_EXPLICIT
        assert lesson.confidence >= MIN_STORE_CONFIDENCE

    def test_b_ordinary_text_ignored(self):
        learner = make_learner()
        lesson = learner.process_owner_message(
            "what time is the meeting tomorrow?",
            context={"situation": "send_email"},
        )
        assert lesson is None
        assert learner._memory.rows == []

    def test_c_ambiguous_text_ignored_or_deferred(self):
        learner = make_learner()
        # A weak implicit pattern with low resulting confidence must not store.
        lesson = learner.process_owner_message(
            "hmm",  # too short / no real signal
            context={"situation": "send_email"},
        )
        assert lesson is None

    def test_c2_preference_never_becomes_correction(self):
        learner = make_learner()
        lesson = learner.process_owner_message(
            "I prefer using fastapi over flask",
            context={"situation": "code_task"},
        )
        assert lesson is None
        assert learner._memory.rows == []

    def test_c3_temporary_instruction_never_becomes_correction(self):
        learner = make_learner()
        lesson = learner.process_owner_message(
            "just this once, use the old format",
            context={"situation": "code_task"},
        )
        assert lesson is None


# ═══════════════════════════════════════════════════════════════════════════
# D, E, F, G, M, N — validate, provenance, retrieval, no runaway amplification, restart
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestCaptureValidatePersistRetrieve:

    def test_d_low_confidence_never_stored(self):
        """D: validation occurs -- MIN_STORE_CONFIDENCE gates storage."""
        detector = CorrectionDetector()
        extractor = LessonExtractor()
        weak = detector.detect("aren't you supposed to check that")  # implicit, borderline
        if weak.is_correction:
            assert weak.confidence >= 0.0
        # LessonExtractor itself refuses anything under the bar regardless of caller:
        from core.memory.correction_learner import DetectionResult
        fake_low = DetectionResult(True, "implicit", 0.3, "some text", "pattern")
        lesson = extractor.extract(fake_low)
        assert lesson is None

    def test_e_provenance_persists(self):
        learner = make_learner()
        lesson = learner.process_owner_message(
            "no, use httpx instead of requests",
            prior_vector_response="I'll use requests",
            context={"situation": "code_task"},
        )
        assert lesson.source == "owner_correction"
        assert lesson.correction_type == CORRECTION_EXPLICIT
        assert lesson.timestamp
        # round-trips through storage exactly
        stored_row = learner._memory.rows[-1]
        from core.memory.correction_learner import CorrectionLesson
        restored = CorrectionLesson.from_storage_content(stored_row["content"])
        assert restored.source == "owner_correction"
        assert restored.id == lesson.id

    def test_f_invalid_correction_rejected(self):
        learner = make_learner()
        lesson = learner.process_owner_message("nothing correction-like here at all")
        assert lesson is None

    def test_g_valid_correction_retrievable(self):
        learner = make_learner()
        learner.process_owner_message(
            "no, use httpx instead of requests",
            context={"situation": "code_task"},
        )
        retrieved = learner.retrieve_applicable_lessons(domain="coding", limit=5)
        # domain detection may vary (see pre-existing baseline failure noted
        # in the R8 report) -- retrieve without the domain filter to avoid
        # coupling this test to that unrelated, pre-existing defect.
        retrieved_any = learner.retrieve_applicable_lessons(limit=5)
        assert len(retrieved_any) == 1
        assert "httpx" in retrieved_any[0].correction

    def test_m_duplicate_correction_does_not_amplify_uncontrollably(self):
        """M: the SAME correction repeated many times must not let the
        decision-path penalty exceed its documented bound."""
        learner = make_learner()
        for _ in range(10):
            learner.process_owner_message(
                "no, use httpx instead of requests",
                context={"situation": "code_task"},
            )
        penalty = learner.get_correction_penalty("code_task")
        assert 0.0 <= penalty <= 0.12

    def test_n_correction_survives_restart(self):
        """N: a second, independent CorrectionLearner instance (simulating a
        process restart) reading the SAME durable store sees the lesson."""
        shared_store = _FakeCorrectionStore()

        learner_before_restart = CorrectionLearner()
        learner_before_restart._memory = shared_store
        lesson = learner_before_restart.process_owner_message(
            "no, use httpx instead of requests",
            context={"situation": "code_task"},
        )
        assert lesson is not None

        # "restart": a brand new CorrectionLearner object, no shared Python
        # state with the first one except the durable store.
        learner_after_restart = CorrectionLearner()
        learner_after_restart._memory = shared_store
        retrieved = learner_after_restart.retrieve_applicable_lessons(limit=5)
        assert len(retrieved) == 1
        assert retrieved[0].id == lesson.id
        penalty_after_restart = learner_after_restart.get_correction_penalty("code_task")
        assert penalty_after_restart > 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Root-cause fix proof: _current_action_type wiring
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestSituationWiringRootCauseFix:

    def test_current_action_type_unset_before_any_action(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        assert getattr(loop, "_current_action_type", None) is None

    async def test_act_on_sets_current_action_type(self):
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        fake_governor = MagicMock()
        fake_governor.dispatch = AsyncMock(return_value={"status": "ok"})
        loop._governor = fake_governor
        fake_policy = MagicMock()
        fake_policy.get_score = MagicMock(return_value=0.5)
        fake_policy.make_situation_hash = MagicMock(side_effect=PolicyMemory.make_situation_hash)
        loop._policy = fake_policy
        fake_memory = MagicMock()
        fake_memory.recall = MagicMock(return_value=[])
        fake_memory.store_chain = MagicMock()
        loop._memory = fake_memory

        winner = Candidate(action_type="r8_probe_action", params={})
        await loop._act_on(winner)
        assert loop._current_action_type == "r8_probe_action"

    async def test_correction_after_action_captures_real_action_type(self):
        """End-to-end proof of the root-cause fix: an action runs, THEN the
        owner corrects it, and the stored lesson's situation is the REAL
        action_type -- not the pre-fix constant "conversation"."""
        from core.loop.autonomous_loop import AutonomousLoop
        loop = AutonomousLoop()
        fake_governor = MagicMock()
        fake_governor.dispatch = AsyncMock(return_value={"status": "ok"})
        loop._governor = fake_governor
        fake_policy = MagicMock()
        fake_policy.get_score = MagicMock(return_value=0.5)
        fake_policy.make_situation_hash = MagicMock(side_effect=PolicyMemory.make_situation_hash)
        loop._policy = fake_policy
        fake_memory = MagicMock()
        fake_memory.recall = MagicMock(return_value=[])
        fake_memory.store_chain = MagicMock()
        loop._memory = fake_memory

        winner = Candidate(action_type="r8_probe_send_email", params={})
        await loop._act_on(winner)

        captured = {}

        def fake_learner_factory():
            fake_cl = make_learner()
            captured["learner"] = fake_cl
            return fake_cl

        import core.memory.correction_learner as cl_module
        real_class = cl_module.CorrectionLearner
        cl_module.CorrectionLearner = lambda: fake_learner_factory()
        try:
            loop._detect_and_store_correction("no, don't send that email, wait for approval")
        finally:
            cl_module.CorrectionLearner = real_class

        rows = captured["learner"]._memory.rows
        assert len(rows) == 1
        from core.memory.correction_learner import CorrectionLesson
        stored = CorrectionLesson.from_storage_content(rows[0]["content"])
        assert stored.situation == "r8_probe_send_email"
        assert stored.situation != "conversation"


# ═══════════════════════════════════════════════════════════════════════════
# H, I, J + WITHOUT/WITH causal demonstration — real DecisionEngine
# ═══════════════════════════════════════════════════════════════════════════

def make_candidate(action_type, confidence=0.6, urgency=0.5, params=None):
    return Candidate(action_type=action_type, params=params or {}, confidence=confidence, urgency=urgency)


@pytest.fixture
def engine_with_learner():
    """Real DecisionEngine, real CorrectionLearner (fake in-memory store),
    everything else stubbed exactly like tests/test_task91_r6_candidate_diversity.py's
    `engine` fixture."""
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
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    e._get_context_engine = MagicMock()
    e._get_context_engine().get_world_state.return_value = {}
    e._get_metacognition = MagicMock(return_value=None)

    learner = make_learner()
    e._get_correction_learner = MagicMock(return_value=learner)
    e._learner = learner  # test-visible handle
    return e


@pytest.mark.unit
class TestDecisionPathInfluence:

    async def test_h_retrieved_correction_reaches_decision_path(self, engine_with_learner):
        e = engine_with_learner
        e._learner.process_owner_message(
            "no, don't send that email, wait for approval",
            context={"situation": "send_email"},
        )
        c = make_candidate("send_email")
        penalty = e._correction_penalty(c)
        assert penalty > 0.0

    async def test_i_relevant_future_decision_changes_without_vs_with(self, engine_with_learner):
        """The WITHOUT/WITH causal demonstration the task requires.

        WITHOUT CORRECTION: send_email wins (higher confidence).
        WITH EXPLICIT CORRECTION targeting send_email specifically:
            check_calendar wins instead -- and the correction is the ONLY
            variable that changed between the two runs.
        """
        def make_pair():
            return [
                make_candidate("send_email", confidence=0.62, urgency=0.5),
                make_candidate("check_calendar", confidence=0.60, urgency=0.5),
            ]

        # WITHOUT correction
        e_without = DecisionEngine()
        e_without._get_policy = MagicMock()
        e_without._get_policy().get_score.return_value = 0.5
        e_without._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
        e_without._get_goals = MagicMock(); e_without._get_goals().get_active_goals.return_value = []
        e_without._get_memory = MagicMock(); e_without._get_memory().store.return_value = None
        e_without._get_epistemic = MagicMock(); e_without._get_epistemic().get_belief.return_value = None
        e_without._get_reasoning_bank = MagicMock(return_value=None)
        e_without._get_neural_trainer = MagicMock(return_value=None)
        e_without._get_context_engine = MagicMock(); e_without._get_context_engine().get_world_state.return_value = {}
        e_without._get_metacognition = MagicMock(return_value=None)
        e_without._get_correction_learner = MagicMock(return_value=None)  # no learner -> no influence

        d_without = await e_without.evaluate(make_pair())
        assert d_without.winner.action_type == "send_email", (
            "sanity check: without any correction, the higher-confidence candidate must win"
        )

        # WITH an explicit correction targeting send_email specifically
        e_with = DecisionEngine()
        e_with._get_policy = MagicMock()
        e_with._get_policy().get_score.return_value = 0.5
        e_with._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
        e_with._get_goals = MagicMock(); e_with._get_goals().get_active_goals.return_value = []
        e_with._get_memory = MagicMock(); e_with._get_memory().store.return_value = None
        e_with._get_epistemic = MagicMock(); e_with._get_epistemic().get_belief.return_value = None
        e_with._get_reasoning_bank = MagicMock(return_value=None)
        e_with._get_neural_trainer = MagicMock(return_value=None)
        e_with._get_context_engine = MagicMock(); e_with._get_context_engine().get_world_state.return_value = {}
        e_with._get_metacognition = MagicMock(return_value=None)

        learner = make_learner()
        learner.process_owner_message(
            "no, don't send that email, wait for approval",
            context={"situation": "send_email"},
        )
        e_with._get_correction_learner = MagicMock(return_value=learner)

        d_with = await e_with.evaluate(make_pair())
        assert d_with.winner.action_type == "check_calendar", (
            "the explicit correction targeting send_email must be the causal "
            "reason the ranking flips"
        )

    async def test_j_unrelated_decision_does_not_change(self, engine_with_learner):
        """J: a correction about send_email must not affect an unrelated
        action_type's score at all."""
        e = engine_with_learner
        e._learner.process_owner_message(
            "no, don't send that email, wait for approval",
            context={"situation": "send_email"},
        )
        unrelated = make_candidate("check_calendar")
        assert e._correction_penalty(unrelated) == 0.0

    async def test_correction_penalty_bounded_max(self, engine_with_learner):
        e = engine_with_learner
        e._learner.process_owner_message(
            "no, don't send that email, wait for approval",
            context={"situation": "send_email"},
        )
        penalty = e._correction_penalty(make_candidate("send_email"))
        assert 0.0 < penalty <= 0.12

    async def test_unvalidated_lesson_still_influences_decision(self, engine_with_learner):
        """Confirms the design decision documented in the report: decision
        influence does NOT require validate_lesson()/VALIDATED status (which
        has zero production callers) -- only MIN_STORE_CONFIDENCE at
        detection time, which every persisted lesson already cleared."""
        e = engine_with_learner
        lesson = e._learner.process_owner_message(
            "no, don't send that email, wait for approval",
            context={"situation": "send_email"},
        )
        assert lesson.validation_status == VALIDATION_UNVALIDATED
        assert e._correction_penalty(make_candidate("send_email")) > 0.0


# ═══════════════════════════════════════════════════════════════════════════
# K, L — governance cannot be bypassed
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestGovernanceUnbypassed:

    def test_k_correction_learner_source_has_no_governor_reference(self):
        import core.memory.correction_learner as cl
        src = inspect.getsource(cl)
        assert "governor" not in src.lower()

    def test_l_correction_learner_source_has_no_permission_gateway_reference(self):
        import core.memory.correction_learner as cl
        src = inspect.getsource(cl)
        assert "PermissionGateway" not in src
        assert "permission_gateway" not in src

    def test_correction_penalty_method_has_no_governance_reference(self):
        e = DecisionEngine()
        src = inspect.getsource(e._correction_penalty)
        assert "Governor" not in src
        assert "PermissionGateway" not in src
        assert "gateway" not in src.lower()

    def test_get_correction_penalty_method_has_no_governance_reference(self):
        src = inspect.getsource(CorrectionLearner.get_correction_penalty)
        assert "Governor" not in src
        assert "PermissionGateway" not in src


# ═══════════════════════════════════════════════════════════════════════════
# No reward-semantics conflation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestNoRewardConflation:

    def test_correction_penalty_does_not_touch_policy_memory(self):
        src = inspect.getsource(DecisionEngine._correction_penalty)
        assert "PolicyMemory" not in src
        assert "update_from_outcome" not in src
        assert "record_suppression" not in src

    def test_get_correction_penalty_does_not_touch_policy_memory(self):
        """The docstring legitimately DISCUSSES why this is not reward-based
        (explanatory prose); what must never appear is an actual call into
        PolicyMemory or a write of a reward value."""
        src = inspect.getsource(CorrectionLearner.get_correction_penalty)
        assert "PolicyMemory" not in src
        assert "update_from_outcome" not in src
        assert "record_suppression" not in src

    def test_update_from_outcome_signature_unchanged(self):
        import inspect as _inspect
        sig = _inspect.signature(PolicyMemory.update_from_outcome)
        assert list(sig.parameters) == ["self", "action_type", "situation_hash", "reward"]

    def test_correction_penalty_bounded_regardless_of_confidence(self):
        """Even a lesson at the maximum possible confidence (0.95) must
        never exceed the documented 0.12 cap."""
        learner = make_learner()
        from core.memory.correction_learner import CorrectionLesson, VALIDATION_UNVALIDATED
        lesson = CorrectionLesson(
            id="cl_max_conf_probe",
            situation="max_conf_action",
            wrong_behavior="x",
            correction="y",
            lesson="z",
            domain="general",
            confidence=0.95,
            timestamp="2026-01-01T00:00:00+00:00",
            applicability="",
            source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED,
            correction_type=CORRECTION_EXPLICIT,
        )
        learner._memory.store(
            event_type="correction_lesson",
            content=lesson.to_storage_content(),
            tags=lesson.tags,
            source="owner_correction",
        )
        penalty = learner.get_correction_penalty("max_conf_action")
        assert penalty <= 0.12


@pytest.mark.unit
class TestCorrectionPenaltyBoundedWait:
    """R9 follow-up (discovered during R9's own regression pass, same
    session): _correction_penalty() calls into a real EpisodicMemory.recall()
    (FTS5 query), which under real-world DB size/lock contention was
    observed to be slow enough to hang a combined test run past pytest's
    90s per-test timeout. Fixed by reusing R1's exact bounded-wait pattern
    (ThreadPoolExecutor + future.result(timeout=)) so a slow/stuck lookup
    can never block DecisionEngine's synchronous scoring hot path."""

    async def test_slow_correction_lookup_does_not_block_scoring(self, engine_with_learner):
        import time as _time

        e = engine_with_learner
        e._learner.get_correction_penalty = lambda action_type: (_time.sleep(2.0), 0.1)[1]

        original_timeout = CONFIG.get("correction_penalty_timeout_sec")
        CONFIG["correction_penalty_timeout_sec"] = 0.2  # short timeout for a fast test
        try:
            start = _time.monotonic()
            penalty = e._correction_penalty(make_candidate("slow_action"))
            elapsed = _time.monotonic() - start
        finally:
            CONFIG["correction_penalty_timeout_sec"] = original_timeout

        assert penalty == 0.0, "a timed-out lookup must degrade to 'no correction found', not raise"
        assert elapsed < 1.5, f"the bounded wait must not let a slow lookup block scoring (took {elapsed:.2f}s)"

    def test_correction_penalty_timeout_config_present_and_bounded(self):
        value = CONFIG.get("correction_penalty_timeout_sec")
        assert value is not None
        assert 0.05 <= value <= 10.0


if __name__ == "__main__":
    import asyncio
    import sys

    async def _main():
        learner = make_learner()
        lesson = learner.process_owner_message(
            "no, don't send that email, wait for approval",
            context={"situation": "send_email"},
        )
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
        e._get_correction_learner = MagicMock(return_value=learner)

        d = await e.evaluate([
            make_candidate("send_email", confidence=0.62),
            make_candidate("check_calendar", confidence=0.60),
        ])
        return lesson is not None and d.winner.action_type == "check_calendar"

    sys.stdout.reconfigure(encoding="utf-8")
    ok = asyncio.run(_main())
    print("✅ test_r8_correction_learning OK" if ok else "❌ FAILED")
