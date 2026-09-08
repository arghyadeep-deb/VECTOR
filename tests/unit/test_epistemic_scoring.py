"""Unit tests — EpistemicTracker integration with DecisionEngine scoring.

Tests the three wiring points:
1. _epistemic_penalty() dampening factors
2. record_epistemic_belief() belief creation/update
3. decay_epistemic() decay delegation

Also tests that epistemic dampening is correctly applied in _score_candidate()
and surfaced in reasoning_chain / reasoning_steps.
"""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.loop.decision_engine import Candidate, DecisionEngine


# ── Fixtures ──────────────────────────────────────────────────────────────


def _make_candidate(action_type="search_web", confidence=0.5, urgency=0.5,
                    timing_score=1.0, estimated_cost_inr=0.0, goal_ids=None,
                    params=None):
    return Candidate(
        action_type=action_type,
        params=params or {},
        goal_ids=goal_ids or [],
        confidence=confidence,
        urgency=urgency,
        timing_score=timing_score,
        estimated_cost_inr=estimated_cost_inr,
    )


@pytest.fixture
def engine():
    """DecisionEngine with mocked dependencies (same pattern as existing tests)."""
    e = DecisionEngine()
    e._get_policy = MagicMock()
    e._get_policy().get_score.return_value = 0.5
    e._get_goals = MagicMock()
    e._get_goals().get_active_goals.return_value = []
    e._get_memory = MagicMock()
    e._get_memory().store.return_value = None
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    e._get_context_engine = MagicMock()
    e._get_context_engine().get_world_state.return_value = {}
    return e


@pytest.fixture
def epistemic_engine(engine):
    """Engine with a real-ish epistemic mock that returns configurable beliefs."""
    mock_epistemic = MagicMock()
    mock_epistemic.get_belief.return_value = None
    mock_epistemic.get_confidence.return_value = 0.0
    mock_epistemic.merge_belief.return_value = None
    mock_epistemic.decay_all.return_value = 0
    mock_epistemic.check_staleness.return_value = []
    engine._get_epistemic = MagicMock(return_value=mock_epistemic)
    return engine, mock_epistemic


# ── _epistemic_penalty() tests ────────────────────────────────────────────


@pytest.mark.unit
class TestEpistemicPenalty:
    """Test the dampening factor logic."""

    def test_unknown_domain_returns_neutral(self, epistemic_engine):
        """No belief for domain → factor 1.0 (no penalty for ignorance)."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = None
        c = _make_candidate("search_web")
        factor, conf = engine._epistemic_penalty(c)
        assert factor == 1.0
        assert conf == 0.0

    def test_stale_belief_returns_heavy_penalty(self, epistemic_engine):
        """Stale belief → factor 0.70 (30% reduction)."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = {
            "stale": True,
            "confidence": 0.8,
            "current_confidence": 0.0,
            "last_verified": "2026-01-01T00:00:00",
            "ttl_hours": 72,
        }
        c = _make_candidate("search_web")
        factor, conf = engine._epistemic_penalty(c)
        assert factor == 0.70
        assert conf == 0.0

    def test_low_confidence_penalty(self, epistemic_engine):
        """Confidence < 0.3 → factor 0.80."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = {
            "stale": False,
            "confidence": 0.2,
            "current_confidence": 0.2,
        }
        c = _make_candidate("search_web")
        factor, conf = engine._epistemic_penalty(c)
        assert factor == 0.80
        assert abs(conf - 0.2) < 0.01

    def test_medium_confidence_penalty(self, epistemic_engine):
        """Confidence 0.3–0.5 → factor 0.90."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = {
            "stale": False,
            "confidence": 0.4,
            "current_confidence": 0.4,
        }
        c = _make_candidate("search_web")
        factor, conf = engine._epistemic_penalty(c)
        assert factor == 0.90
        assert abs(conf - 0.4) < 0.01

    def test_high_confidence_no_penalty(self, epistemic_engine):
        """Confidence ≥ 0.5 → factor 1.0 (no penalty)."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = {
            "stale": False,
            "confidence": 0.85,
            "current_confidence": 0.85,
        }
        c = _make_candidate("search_web")
        factor, conf = engine._epistemic_penalty(c)
        assert factor == 1.0
        assert abs(conf - 0.85) < 0.01

    def test_epistemic_unavailable_returns_neutral(self, engine):
        """No epistemic tracker → factor 1.0."""
        engine._get_epistemic = MagicMock(return_value=None)
        c = _make_candidate("search_web")
        factor, conf = engine._epistemic_penalty(c)
        assert factor == 1.0

    def test_exception_returns_neutral(self, epistemic_engine):
        """Epistemic throws → factor 1.0 (fail-open)."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.side_effect = RuntimeError("db corrupted")
        c = _make_candidate("search_web")
        factor, conf = engine._epistemic_penalty(c)
        assert factor == 1.0

    def test_config_gate_disables_penalty(self, epistemic_engine):
        """CONFIG epistemic_scoring=False → factor 1.0."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = {
            "stale": True, "confidence": 0.0, "current_confidence": 0.0,
        }
        c = _make_candidate("search_web")
        with patch.dict("core.loop.decision_engine.CONFIG",
                        {"epistemic_scoring": False}):
            factor, conf = engine._epistemic_penalty(c)
        assert factor == 1.0

    def test_domain_extracted_from_action_type(self, epistemic_engine):
        """Domain is first segment of action_type (before underscore)."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = None
        c = _make_candidate("code_review_vc")
        engine._epistemic_penalty(c)
        mock_ep.get_belief.assert_called_with("action_domain:code")


# ── _score_candidate() integration with epistemic ─────────────────────────


@pytest.mark.unit
class TestScoringWithEpistemic:
    """Test that _score_candidate applies epistemic dampening."""

    def test_stale_domain_reduces_score(self, epistemic_engine):
        """Two identical candidates; one in stale domain scores lower."""
        engine, mock_ep = epistemic_engine

        # First call: no belief (neutral). Second call: stale belief.
        call_count = [0]
        def side_effect(claim_id):
            call_count[0] += 1
            if "stale_domain" in claim_id:
                return {"stale": True, "confidence": 0.0,
                        "current_confidence": 0.0, "last_verified": "old",
                        "ttl_hours": 72}
            return None
        mock_ep.get_belief.side_effect = side_effect

        c_fresh = _make_candidate("fresh_action")
        c_stale = _make_candidate("stale_domain_action")

        engine._score_candidate(c_fresh)
        engine._score_candidate(c_stale)

        assert c_stale.total_score < c_fresh.total_score, (
            f"Stale domain should score lower: "
            f"{c_stale.total_score} vs {c_fresh.total_score}"
        )

    def test_epistemic_factor_appears_in_reasoning_chain(self, epistemic_engine):
        """When epistemic penalty > 0, reasoning_chain includes epistemic entry."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = {
            "stale": False,
            "confidence": 0.2,
            "current_confidence": 0.2,
        }
        c = _make_candidate("lowconf_action")
        engine._score_candidate(c)

        epistemic_entries = [
            e for e in c.reasoning_chain
            if e.get("factor") == "epistemic_confidence"
        ]
        assert len(epistemic_entries) == 1
        assert epistemic_entries[0]["weight"] == 0.80

    def test_epistemic_factor_appears_in_reasoning_steps(self, epistemic_engine):
        """When epistemic penalty > 0, reasoning_steps includes epistemic line."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = {
            "stale": True,
            "confidence": 0.0,
            "current_confidence": 0.0,
        }
        c = _make_candidate("stale_action")
        engine._score_candidate(c)

        epistemic_steps = [
            s for s in c.reasoning_steps
            if "epistemic_factor" in s
        ]
        assert len(epistemic_steps) == 1
        assert "0.70" in epistemic_steps[0]

    def test_no_epistemic_entry_when_neutral(self, epistemic_engine):
        """When factor is 1.0, reasoning_chain has no epistemic entry."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = None  # unknown domain
        c = _make_candidate("unknown_action")
        engine._score_candidate(c)

        epistemic_entries = [
            e for e in c.reasoning_chain
            if e.get("factor") == "epistemic_confidence"
        ]
        assert len(epistemic_entries) == 0


# ── record_epistemic_belief() tests ───────────────────────────────────────


@pytest.mark.unit
class TestRecordEpistemicBelief:
    """Test belief recording after action outcomes."""

    def test_high_reward_creates_belief(self, epistemic_engine):
        """High reward → high confidence belief."""
        engine, mock_ep = epistemic_engine
        engine.record_epistemic_belief("search_web", "ok", 0.9)
        mock_ep.merge_belief.assert_called_once()
        args = mock_ep.merge_belief.call_args
        assert args[0][0] == "action_domain:search"  # claim_id
        assert abs(args[0][2] - 0.9) < 0.01          # confidence
        assert args[0][3] == "act_loop"               # source

    def test_low_reward_creates_low_confidence(self, epistemic_engine):
        """Low reward → low confidence belief."""
        engine, mock_ep = epistemic_engine
        engine.record_epistemic_belief("commit_code", "failed", 0.2)
        mock_ep.merge_belief.assert_called_once()
        args = mock_ep.merge_belief.call_args
        assert abs(args[0][2] - 0.2) < 0.01

    def test_reward_clamped_to_01(self, epistemic_engine):
        """Reward outside [0, 1] is clamped."""
        engine, mock_ep = epistemic_engine
        engine.record_epistemic_belief("action_x", "ok", 1.5)
        args = mock_ep.merge_belief.call_args
        assert args[0][2] <= 1.0

        mock_ep.reset_mock()
        engine.record_epistemic_belief("action_y", "ok", -0.3)
        args = mock_ep.merge_belief.call_args
        assert args[0][2] >= 0.0

    def test_no_call_when_epistemic_unavailable(self, engine):
        """No epistemic tracker → no crash, no call."""
        engine._get_epistemic = MagicMock(return_value=None)
        engine.record_epistemic_belief("action_x", "ok", 0.8)
        # No assertion needed — just verifying no exception

    def test_config_gate_disables_recording(self, epistemic_engine):
        """CONFIG epistemic_scoring=False → merge_belief not called."""
        engine, mock_ep = epistemic_engine
        with patch.dict("core.loop.decision_engine.CONFIG",
                        {"epistemic_scoring": False}):
            engine.record_epistemic_belief("action_x", "ok", 0.8)
        mock_ep.merge_belief.assert_not_called()

    def test_exception_does_not_propagate(self, epistemic_engine):
        """If merge_belief throws, no crash."""
        engine, mock_ep = epistemic_engine
        mock_ep.merge_belief.side_effect = RuntimeError("db locked")
        engine.record_epistemic_belief("action_x", "ok", 0.8)
        # No exception propagated


# ── decay_epistemic() tests ───────────────────────────────────────────────


@pytest.mark.unit
class TestDecayEpistemic:
    """Test decay delegation to EpistemicTracker."""

    def test_returns_count_from_decay_all(self, epistemic_engine):
        """decay_epistemic returns the count from decay_all()."""
        engine, mock_ep = epistemic_engine
        mock_ep.decay_all.return_value = 5
        mock_ep.check_staleness.return_value = []
        result = engine.decay_epistemic()
        assert result == 5

    def test_returns_zero_when_no_epistemic(self, engine):
        """No tracker → returns 0."""
        engine._get_epistemic = MagicMock(return_value=None)
        result = engine.decay_epistemic()
        assert result == 0

    def test_returns_zero_when_config_disabled(self, epistemic_engine):
        """CONFIG epistemic_scoring=False → returns 0."""
        engine, mock_ep = epistemic_engine
        with patch.dict("core.loop.decision_engine.CONFIG",
                        {"epistemic_scoring": False}):
            result = engine.decay_epistemic()
        assert result == 0
        mock_ep.decay_all.assert_not_called()

    def test_exception_returns_zero(self, epistemic_engine):
        """If decay_all throws → returns 0."""
        engine, mock_ep = epistemic_engine
        mock_ep.decay_all.side_effect = RuntimeError("db error")
        result = engine.decay_epistemic()
        assert result == 0


# ── evaluate() end-to-end with epistemic ──────────────────────────────────


@pytest.mark.unit
class TestEvaluateWithEpistemic:
    """Test that evaluate() correctly applies epistemic dampening to winner selection."""

    async def test_epistemic_changes_winner(self, epistemic_engine):
        """Candidate in well-known domain wins over identical candidate in stale domain."""
        engine, mock_ep = epistemic_engine

        def belief_side_effect(claim_id):
            if "alpha" in claim_id:
                return {"stale": False, "confidence": 0.9,
                        "current_confidence": 0.9}
            if "beta" in claim_id:
                return {"stale": True, "confidence": 0.0,
                        "current_confidence": 0.0, "last_verified": "old",
                        "ttl_hours": 72}
            return None
        mock_ep.get_belief.side_effect = belief_side_effect

        c_alpha = _make_candidate("alpha_action", confidence=0.7, urgency=0.5)
        c_beta = _make_candidate("beta_action", confidence=0.7, urgency=0.5)

        decision = await engine.evaluate([c_alpha, c_beta])
        assert decision.winner.action_type == "alpha_action", (
            f"Well-known domain should win: "
            f"alpha={c_alpha.total_score} vs beta={c_beta.total_score}"
        )

    async def test_unknown_domains_compete_equally(self, epistemic_engine):
        """Two candidates in unknown domains → same epistemic factor (1.0)."""
        engine, mock_ep = epistemic_engine
        mock_ep.get_belief.return_value = None

        c1 = _make_candidate("new1_action", confidence=0.6, urgency=0.5)
        c2 = _make_candidate("new2_action", confidence=0.6, urgency=0.5)

        engine._score_candidate(c1)
        engine._score_candidate(c2)

        # Scores should be identical (same inputs, same epistemic factor)
        assert abs(c1.total_score - c2.total_score) < 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
