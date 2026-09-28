
import copy
import math
from unittest.mock import MagicMock, patch

import pytest

from core.loop.decision_engine import DecisionEngine, Candidate, Decision


def make_candidate(action_type="test_action", confidence=0.5, urgency=0.5,
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
    e = DecisionEngine()
    e._get_policy = MagicMock()
    e._get_policy().get_score.return_value = 0.5
    e._get_goals = MagicMock()
    e._get_goals().get_active_goals.return_value = []
    e._get_memory = MagicMock()
    e._get_memory().store.return_value = None
    e._get_epistemic = MagicMock()
    e._get_epistemic().get_belief.return_value = None
    e._get_epistemic().update_belief.return_value = None
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    return e


@pytest.mark.unit
class TestScoringFactors:

    async def test_goal_alignment_increases_score(self, engine):
        low = make_candidate("action_a", goal_ids=[], confidence=0.5, urgency=0.5)
        high = make_candidate("action_b", goal_ids=["g_important"], confidence=0.5, urgency=0.5)
        engine._get_goals().get_active_goals.return_value = [
            {"id": "g_important", "priority": 10, "progress": 0.0}
        ]
        decision = await engine.evaluate([low, high])
        assert decision.winner.action_type == "action_b"

    async def test_confidence_factor(self, engine):
        low = make_candidate("action_a", confidence=0.1, urgency=0.5)
        high = make_candidate("action_b", confidence=0.9, urgency=0.5)
        decision = await engine.evaluate([low, high])
        assert decision.winner.action_type == "action_b"

    async def test_urgency_factor(self, engine):
        low = make_candidate("action_a", confidence=0.5, urgency=0.1)
        high = make_candidate("action_b", confidence=0.5, urgency=0.9)
        decision = await engine.evaluate([low, high])
        assert decision.winner.action_type == "action_b"

    async def test_timing_factor(self, engine):
        low = make_candidate("action_a", confidence=0.5, timing_score=0.2)
        high = make_candidate("action_b", confidence=0.5, timing_score=1.0)
        decision = await engine.evaluate([low, high])
        assert decision.winner.action_type == "action_b"

    async def test_cost_penalty_reduces_score(self, engine):
        cheap = make_candidate("action_a", confidence=0.5, estimated_cost_inr=0.0)
        expensive = make_candidate("action_b", confidence=0.5, estimated_cost_inr=50.0)
        decision = await engine.evaluate([cheap, expensive])
        assert decision.winner.action_type == "action_a"

    async def test_each_factor_contributes_to_reasoning_chain(self, engine):
        c = make_candidate("action_a", confidence=0.7, urgency=0.6, timing_score=0.8)
        await engine.evaluate([c])
        assert len(c.reasoning_chain) >= 6  # later rounds added extra post-score factors
        factor_names = {s["factor"] for s in c.reasoning_chain}
        assert "goal_alignment" in factor_names
        assert "confidence" in factor_names
        assert "policy_score" in factor_names
        assert "urgency" in factor_names
        assert "timing_score" in factor_names
        assert "cost_penalty" in factor_names


@pytest.mark.unit
class TestTieScores:

    async def test_tie_scores_first_wins(self, engine):
        c1 = make_candidate("alpha", confidence=0.5, urgency=0.5, timing_score=0.5, estimated_cost_inr=0.0)
        c2 = make_candidate("beta", confidence=0.5, urgency=0.5, timing_score=0.5, estimated_cost_inr=0.0)
        decision = await engine.evaluate([c1, c2])
        assert decision.winner.action_type == "alpha"
        assert c1.total_score == c2.total_score

    async def test_tie_three_candidates(self, engine):
        cands = [
            make_candidate("x", confidence=0.5, urgency=0.5),
            make_candidate("y", confidence=0.5, urgency=0.5),
            make_candidate("z", confidence=0.5, urgency=0.5),
        ]
        decision = await engine.evaluate(cands)
        assert decision.winner.action_type == "x"
        scores = [c.total_score for c in decision.all_candidates]
        assert scores[0] == scores[1] == scores[2]


@pytest.mark.unit
class TestNegativeCostHandling:

    async def test_negative_cost_increases_score(self, engine):
        positive = make_candidate("action_a", confidence=0.5, estimated_cost_inr=10.0)
        negative = make_candidate("action_b", confidence=0.5, estimated_cost_inr=-10.0)
        decision = await engine.evaluate([positive, negative])
        assert decision.winner is not None


@pytest.mark.unit
class TestZeroUtilityActions:

    async def test_zero_confidence_action(self, engine):
        c = make_candidate("action_a", confidence=0.0, urgency=0.0, timing_score=0.0)
        decision = await engine.evaluate([c])
        assert 0.0 <= c.total_score <= 1.0
        assert decision.winner.action_type == "action_a"

    async def test_evaluated_count_correct(self, engine):
        decision = await engine.evaluate([])
        assert decision.winner.action_type == "noop"
        assert decision.evaluated == 0

    async def test_single_candidate_wins(self, engine):
        c = make_candidate("only_action", confidence=0.1, urgency=0.1)
        decision = await engine.evaluate([c])
        assert decision.winner.action_type == "only_action"


@pytest.mark.unit
class TestNaNInfHandling:

    async def test_nan_confidence_does_not_crash(self, engine):
        c = make_candidate("action_nan", confidence=float("nan"), urgency=0.5)
        try:
            await engine.evaluate([c])
        except Exception:
            pytest.fail("NaN confidence crashed the engine")

    async def test_inf_confidence_does_not_crash(self, engine):
        c = make_candidate("action_inf", confidence=float("inf"), urgency=0.5)
        try:
            await engine.evaluate([c])
        except Exception:
            pytest.fail("Inf confidence crashed the engine")

    async def test_nan_urgency_does_not_crash(self, engine):
        c = make_candidate("action_nan", confidence=0.5, urgency=float("nan"))
        try:
            await engine.evaluate([c])
        except Exception:
            pytest.fail("NaN urgency crashed the engine")

    async def test_neg_inf_cost_does_not_crash(self, engine):
        c = make_candidate("action_neg_inf", confidence=0.5, estimated_cost_inr=float("-inf"))
        try:
            await engine.evaluate([c])
        except Exception:
            pytest.fail("-inf cost crashed the engine")


@pytest.mark.unit
class TestDegeneratePolicy:

    async def test_degenerate_policy_rejected_when_no_policy(self, engine):
        engine._get_policy = MagicMock()
        engine._get_policy().get_score.return_value = 0.0
        c1 = make_candidate("policy_bad", confidence=1.0, urgency=1.0)
        c2 = make_candidate("policy_good", confidence=0.0, urgency=0.0)
        decision = await engine.evaluate([c1, c2])
        assert decision.winner is not None

    async def test_policy_score_applied(self, engine):
        c = make_candidate("action_a", confidence=0.5, urgency=0.5)
        await engine.evaluate([c])
        assert 0.0 <= c.policy_score <= 1.0


@pytest.mark.unit
class TestA2CTrainer:

    async def test_neural_score_defaults_when_no_trainer(self, engine):
        c = make_candidate("action_a", confidence=0.5)
        await engine.evaluate([c])
        assert 0.0 <= c.total_score <= 1.0

    async def test_evaluate_records_neural_state_and_learn_on_outcome(self):
        # New contract (audit 2026-06-08): evaluate() records _last_neural
        # (state + chosen action); record_outcome(reward) trains the network.
        engine = DecisionEngine()
        mock_trainer = MagicMock()
        mock_trainer.train_episode.return_value = {"total": 0.1, "episode": 1}
        mock_trainer.save_checkpoint.return_value = None
        engine._get_neural_trainer = MagicMock(return_value=mock_trainer)
        engine._get_policy = MagicMock()
        engine._get_policy().get_score.return_value = 0.5
        engine._get_goals = MagicMock()
        engine._get_goals().get_active_goals.return_value = []
        engine._get_memory = MagicMock()
        engine._get_memory().store.return_value = None
        engine._get_epistemic = MagicMock()
        engine._get_epistemic().get_belief.return_value = None
        engine._get_epistemic().update_belief.return_value = None
        engine._get_reasoning_bank = MagicMock(return_value=None)
        c = make_candidate("search_web", confidence=0.5)
        await engine.evaluate([c])
        assert engine._last_neural is not None
        assert "state" in engine._last_neural and "action" in engine._last_neural
        engine.record_outcome(0.8)
        mock_trainer.train_episode.assert_called_once()
        assert engine._last_neural is None  # consumed after learning

    async def test_checkpoint_saved_periodically(self):
        # Checkpoint fires inside record_outcome when _decision_count % 100 == 0.
        engine = DecisionEngine()
        mock_trainer = MagicMock()
        mock_trainer.train_episode.return_value = {"total": 0.1, "episode": 1}
        mock_trainer.save_checkpoint.return_value = None
        engine._get_neural_trainer = MagicMock(return_value=mock_trainer)
        import numpy as np
        engine._decision_count = 100
        engine._last_neural = {"state": np.zeros(8, dtype=np.float32), "action": 3}
        engine.record_outcome(0.5)
        assert mock_trainer.save_checkpoint.called


@pytest.mark.unit
class TestEntropyCollapse:

    async def test_no_collapse_different_scores(self, engine):
        cands = [
            make_candidate("a", confidence=0.9, urgency=0.9),
            make_candidate("b", confidence=0.3, urgency=0.3),
        ]
        decision = await engine.evaluate(cands)
        scores = [c.total_score for c in decision.all_candidates]
        assert scores[0] > scores[1]

    async def test_all_same_score_not_collapse(self, engine):
        c1 = make_candidate("x", confidence=0.5, urgency=0.5, timing_score=0.5)
        c2 = make_candidate("y", confidence=0.5, urgency=0.5, timing_score=0.5)
        decision = await engine.evaluate([c1, c2])
        assert c1.total_score == c2.total_score


@pytest.mark.unit
class TestTemperatureAndRandomness:

    async def test_evaluate_is_deterministic_with_same_inputs(self, engine):
        cands = [
            make_candidate("a", confidence=0.9, urgency=0.9),
            make_candidate("b", confidence=0.1, urgency=0.1),
        ]
        d1 = await engine.evaluate([copy.deepcopy(c) for c in cands])
        d2 = await engine.evaluate([copy.deepcopy(c) for c in cands])
        assert d1.winner.action_type == d2.winner.action_type
        assert d1.winner.total_score == d2.winner.total_score

    async def test_score_proportional_to_input(self, engine):
        c = make_candidate("action_a", confidence=0.2, urgency=0.2, timing_score=0.2)
        await engine.evaluate([c])
        score_low = c.total_score
        c2 = make_candidate("action_b", confidence=0.9, urgency=0.9, timing_score=0.9)
        await engine.evaluate([c2])
        assert c2.total_score > score_low


@pytest.mark.unit
class TestDecisionMetadata:

    async def test_decision_has_all_fields(self, engine):
        decision = await engine.evaluate([make_candidate("test")])
        assert isinstance(decision, Decision)
        assert decision.winner is not None
        assert isinstance(decision.all_candidates, list)
        assert isinstance(decision.reasoning, str)
        assert decision.evaluated >= 1
        assert len(decision.reasoning_chain) >= 1

    async def test_reasoning_contains_key_info(self, engine):
        decision = await engine.evaluate([
            make_candidate("search_web", confidence=0.8),
            make_candidate("set_timer", confidence=0.5),
        ])
        assert decision.winner.action_type in decision.reasoning
        assert str(decision.winner.total_score) in decision.reasoning

    async def test_reasoning_steps_populated(self, engine):
        c = make_candidate("search_web", confidence=0.8, urgency=0.7)
        await engine.evaluate([c])
        assert len(c.reasoning_steps) >= 6
        assert any("FINAL" in s for s in c.reasoning_steps)
