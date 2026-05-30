import asyncio

import pytest
from core.loop.decision_engine import DecisionEngine, Candidate, Decision


@pytest.fixture
def engine():
    return DecisionEngine()


def make_candidate(action_type, confidence=0.7, urgency=0.5, goal_ids=None):
    return Candidate(
        action_type=action_type,
        params={"query": action_type},
        goal_ids=goal_ids or [],
        confidence=confidence,
        urgency=urgency,
    )


@pytest.mark.asyncio
async def test_returns_winner(engine):
    candidates = [
        make_candidate("search_web", confidence=0.9, urgency=0.8),
        make_candidate("set_timer", confidence=0.4, urgency=0.2),
    ]
    decision = await engine.evaluate(candidates)
    assert decision.winner is not None
    assert decision.winner.action_type in ("search_web", "set_timer")


@pytest.mark.asyncio
async def test_higher_confidence_wins_ceteris_paribus(engine):
    candidates = [
        make_candidate("action_a", confidence=0.9, urgency=0.5),
        make_candidate("action_b", confidence=0.1, urgency=0.5),
    ]
    decision = await engine.evaluate(candidates)
    assert decision.winner.action_type == "action_a"


@pytest.mark.asyncio
async def test_score_in_valid_range(engine):
    candidates = [make_candidate("search_web"), make_candidate("set_timer")]
    decision = await engine.evaluate(candidates)
    for c in decision.all_candidates:
        assert 0.0 <= c.total_score <= 1.0


@pytest.mark.asyncio
async def test_evaluated_count(engine):
    candidates = [make_candidate(f"action_{i}") for i in range(4)]
    decision = await engine.evaluate(candidates)
    assert decision.evaluated == 4


@pytest.mark.asyncio
async def test_empty_candidates_returns_noop(engine):
    decision = await engine.evaluate([])
    assert decision.winner.action_type == "noop"
    assert decision.evaluated == 0


@pytest.mark.asyncio
async def test_all_candidates_in_result(engine):
    candidates = [make_candidate(f"action_{i}") for i in range(3)]
    decision = await engine.evaluate(candidates)
    assert len(decision.all_candidates) == 3


@pytest.mark.asyncio
async def test_policy_score_applied(engine):
    c = make_candidate("search_web")
    await engine.evaluate([c])
    assert 0.0 <= c.policy_score <= 1.0


@pytest.mark.asyncio
async def test_reasoning_string_contains_winner(engine):
    candidates = [make_candidate("search_web"), make_candidate("set_timer")]
    decision = await engine.evaluate(candidates)
    assert decision.winner.action_type in decision.reasoning
