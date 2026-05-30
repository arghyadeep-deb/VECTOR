"""Integration tests — Session A4: MetaCognition bias penalty in DecisionEngine._score_candidate."""
from __future__ import annotations

import time
import unittest


class TestMetaCognitionAccessor(unittest.TestCase):
    """DecisionEngine._get_metacognition() lazy accessor contract."""

    def setUp(self):
        from core.loop.decision_engine import DecisionEngine
        self.engine = DecisionEngine()

    def test_accessor_returns_object_or_none(self):
        mc = self.engine._get_metacognition()
        # Either a MetaCognition instance or None (if import fails) — never raises
        self.assertTrue(mc is None or hasattr(mc, "detect_bias"))

    def test_accessor_idempotent(self):
        mc1 = self.engine._get_metacognition()
        mc2 = self.engine._get_metacognition()
        self.assertIs(mc1, mc2)

    def test_cache_attrs_initialised(self):
        self.assertIsNone(self.engine._mc_bias_cache)
        self.assertEqual(self.engine._mc_cache_time, 0.0)

    def test_bias_penalty_returns_float(self):
        from core.loop.decision_engine import Candidate
        c = Candidate(action_type="git_status", params={}, confidence=0.5)
        penalty = self.engine._bias_penalty(c)
        self.assertIsInstance(penalty, float)
        self.assertGreaterEqual(penalty, 0.0)
        self.assertLessEqual(penalty, 1.0)

    def test_bias_penalty_never_raises(self):
        """_bias_penalty must be exception-safe regardless of MetaCognition state."""
        from core.loop.decision_engine import Candidate
        c = Candidate(action_type="unknown_action_xyz", params={}, confidence=0.99)
        # Must not raise
        result = self.engine._bias_penalty(c)
        self.assertIsInstance(result, float)


class TestBiasCaching(unittest.TestCase):
    """5-minute bias cache behaviour."""

    def setUp(self):
        from core.loop.decision_engine import DecisionEngine, Candidate
        self.engine = DecisionEngine()
        self.Candidate = Candidate

    def test_cache_populated_after_first_call(self):
        c = self.Candidate(action_type="review_code", params={}, confidence=0.6)
        self.engine._bias_penalty(c)
        # After the first call, cache_time must be non-zero
        self.assertGreater(self.engine._mc_cache_time, 0.0)
        # And _mc_bias_cache must be a list (not None)
        self.assertIsInstance(self.engine._mc_bias_cache, list)

    def test_cache_reused_within_window(self):
        """Second call within 5 min must not re-invoke detect_bias (same list object)."""
        c = self.Candidate(action_type="answer_question", params={}, confidence=0.7)
        self.engine._bias_penalty(c)
        first_cache = self.engine._mc_bias_cache
        first_time = self.engine._mc_cache_time
        # Force a second call immediately — time has not advanced past 300s
        self.engine._bias_penalty(c)
        self.assertIs(self.engine._mc_bias_cache, first_cache)
        self.assertEqual(self.engine._mc_cache_time, first_time)

    def test_cache_expires_after_300s(self):
        """Manually backdating _mc_cache_time causes next call to refresh."""
        c = self.Candidate(action_type="answer_question", params={}, confidence=0.7)
        self.engine._bias_penalty(c)
        first_cache = self.engine._mc_bias_cache
        # Backdate cache time by more than 300s
        self.engine._mc_cache_time -= 301
        self.engine._bias_penalty(c)
        # Cache time must have been refreshed
        self.assertGreater(self.engine._mc_cache_time, time.monotonic() - 5)


class TestBiasPenaltyOverconfidence(unittest.TestCase):
    """Overconfidence bias: high-confidence candidates are penalized when bias is detected."""

    def _make_engine_with_overconfidence_bias(self):
        """Return DecisionEngine with _mc_bias_cache pre-set to overconfidence bias."""
        from core.loop.decision_engine import DecisionEngine
        engine = DecisionEngine()
        # Pre-populate cache to avoid calling episodic memory in tests
        engine._mc_bias_cache = [{"bias_type": "overconfidence", "severity": "high", "evidence": "test", "recommendation": "lower conf"}]
        engine._mc_cache_time = time.monotonic()
        return engine

    def test_overconfident_candidate_penalized(self):
        """confidence > 0.85 must attract positive penalty when overconfidence bias is active."""
        from core.loop.decision_engine import Candidate
        engine = self._make_engine_with_overconfidence_bias()
        c = Candidate(action_type="deploy_production", params={}, confidence=0.95)
        penalty = engine._bias_penalty(c)
        self.assertGreater(penalty, 0.0, "overconfident candidate must have penalty > 0")

    def test_normal_confidence_not_penalized_for_overconfidence(self):
        """confidence <= 0.85 must NOT be penalized by overconfidence bias."""
        from core.loop.decision_engine import Candidate
        engine = self._make_engine_with_overconfidence_bias()
        c = Candidate(action_type="answer_question", params={}, confidence=0.7)
        penalty = engine._bias_penalty(c)
        self.assertEqual(penalty, 0.0, "moderate confidence must not trigger overconfidence penalty")

    def test_score_candidate_lower_for_overconfident(self):
        """_score_candidate total_score must be lower with overconfidence bias than without."""
        from core.loop.decision_engine import DecisionEngine, Candidate
        # Engine WITHOUT injected bias
        engine_clean = DecisionEngine()
        engine_clean._mc_bias_cache = []
        engine_clean._mc_cache_time = time.monotonic()

        # Engine WITH overconfidence bias
        engine_biased = DecisionEngine()
        engine_biased._mc_bias_cache = [{"bias_type": "overconfidence", "severity": "high", "evidence": "x", "recommendation": "y"}]
        engine_biased._mc_cache_time = time.monotonic()

        c_clean = Candidate(action_type="execute_code", params={}, confidence=0.95, goal_ids=[])
        c_biased = Candidate(action_type="execute_code", params={}, confidence=0.95, goal_ids=[])

        score_clean = engine_clean._score_candidate(c_clean)
        score_biased = engine_biased._score_candidate(c_biased)
        self.assertLess(score_biased, score_clean, "biased engine must score overconfident candidate lower")


class TestBiasPenaltyDecisionIntegration(unittest.TestCase):
    """bias_factor appears in reasoning_steps when a penalty is applied."""

    def test_bias_step_in_reasoning_steps(self):
        from core.loop.decision_engine import DecisionEngine, Candidate
        engine = DecisionEngine()
        engine._mc_bias_cache = [{"bias_type": "overconfidence", "severity": "medium", "evidence": "test", "recommendation": "reduce conf"}]
        engine._mc_cache_time = time.monotonic()
        c = Candidate(action_type="push_github", params={}, confidence=0.92, goal_ids=[])
        engine._score_candidate(c)
        bias_steps = [s for s in c.reasoning_steps if "meta_cognition" in s]
        self.assertGreater(len(bias_steps), 0, "reasoning_steps must include meta_cognition bias entry")
        self.assertIn("bias_penalty", bias_steps[0])

    def test_no_bias_step_when_penalty_zero(self):
        from core.loop.decision_engine import DecisionEngine, Candidate
        engine = DecisionEngine()
        engine._mc_bias_cache = []  # no bias detected
        engine._mc_cache_time = time.monotonic()
        c = Candidate(action_type="answer_question", params={}, confidence=0.6, goal_ids=[])
        engine._score_candidate(c)
        bias_steps = [s for s in c.reasoning_steps if "meta_cognition" in s]
        self.assertEqual(len(bias_steps), 0, "no bias step when penalty is zero")

    def test_score_clamped_to_0_1_with_penalty(self):
        """total_score must always stay in [0, 1] even after penalty subtraction."""
        from core.loop.decision_engine import DecisionEngine, Candidate
        engine = DecisionEngine()
        engine._mc_bias_cache = [{"bias_type": "overconfidence", "severity": "high", "evidence": "x", "recommendation": "y"},
                                  {"bias_type": "recency", "severity": "high", "evidence": "x", "recommendation": "y"}]
        engine._mc_cache_time = time.monotonic()
        c = Candidate(action_type="deploy_production", params={}, confidence=0.99, goal_ids=[])
        engine._score_candidate(c)
        self.assertGreaterEqual(c.total_score, 0.0)
        self.assertLessEqual(c.total_score, 1.0)


if __name__ == "__main__":
    unittest.main()
