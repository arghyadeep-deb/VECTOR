"""Stage 4 finding #1 (external review 2026-09-24): with zero goal-derived
actions, _think_tick() used to return early and never reached the plan-
candidate block, starving active plans. Guard the fix: an empty GoalSystem
must still let plan candidates reach DecisionEngine.evaluate().
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import Candidate


@pytest.mark.asyncio
async def test_plan_candidates_reach_decision_engine_when_goal_system_is_empty(monkeypatch):
    monkeypatch.setattr(
        "core.sensing.stuck_detector.get_active_session", lambda: None, raising=False
    )
    loop = AutonomousLoop.__new__(AutonomousLoop)
    loop._pending_voice = None
    loop._tick_count = 1

    plan_cand = Candidate(
        action_type="git_status", params={"_plan_id": "p", "_step_id": "s1"},
        goal_ids=[], confidence=0.5, urgency=0.6, source="plan:p:s1",
    )
    seen: list[list] = []

    async def _evaluate(cands):
        seen.append(list(cands))
        return SimpleNamespace(winner=SimpleNamespace(
            action_type="noop", total_score=0.0, goal_ids=[]))

    ctx = MagicMock()
    ctx.get_world_state.return_value = {}
    goals = MagicMock()
    goals.generate_immediate_actions.return_value = []
    decision = MagicMock()
    decision.evaluate = _evaluate

    monkeypatch.setattr(loop, "_get_context", lambda: ctx)
    monkeypatch.setattr(loop, "_get_goals", lambda: goals)
    monkeypatch.setattr(loop, "_get_decision", lambda: decision)
    monkeypatch.setattr(loop, "_get_plan_candidates", lambda: [plan_cand])

    await loop._think_tick()

    assert seen, "evaluate() must be called even with zero goal actions"
    assert [c.source for c in seen[0]] == ["plan:p:s1"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
