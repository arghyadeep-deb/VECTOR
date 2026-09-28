"""ContinueGate must be fed real coherence, not the decision's ranking score (fixed 2026-09-26).

_think_tick() acts on any winner scoring above 0.3 but used to hand `winner.total_score` to ContinueGate as its
"coherence", and ContinueGate stops below 0.4 -- so winners scoring 0.30-0.40 were selected every tick and never run
(330 drops of `analyze_progress` in the live log; a plan whose fallback step scored 0.38 could never finish).
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.loop.autonomous_loop import AutonomousLoop


def _loop(monkeypatch, score: float, gate=None):
    monkeypatch.setattr("core.sensing.stuck_detector.get_active_session", lambda: None, raising=False)
    loop = AutonomousLoop.__new__(AutonomousLoop)
    loop._pending_voice = None
    loop._tick_count = 7
    winner = SimpleNamespace(action_type="analyze_progress", total_score=score, goal_ids=[], source="think_loop",
                             params={}, decision_id="d", candidate_id="c")

    async def _evaluate(cands):
        return SimpleNamespace(winner=winner)

    ctx = MagicMock()
    ctx.get_world_state.return_value = {}
    goals = MagicMock()
    goals.generate_immediate_actions.return_value = []
    decision = MagicMock()
    decision.evaluate = _evaluate
    monkeypatch.setattr(loop, "_get_context", lambda: ctx)
    monkeypatch.setattr(loop, "_get_goals", lambda: goals)
    monkeypatch.setattr(loop, "_get_decision", lambda: decision)
    monkeypatch.setattr(loop, "_get_plan_candidates", lambda: [])
    monkeypatch.setattr(loop, "_publish_event", AsyncMock())
    loop._act_on = AsyncMock()
    if gate is not None:
        monkeypatch.setattr(loop, "_get_continue_gate", lambda: gate)
    return loop


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [0.31, 0.38, 0.396])
async def test_winner_between_0_3_and_0_4_is_acted_on_not_silently_dropped(monkeypatch, score):
    loop = _loop(monkeypatch, score)
    await loop._think_tick()
    loop._act_on.assert_awaited_once()


@pytest.mark.asyncio
async def test_winner_at_or_below_0_3_is_still_dropped(monkeypatch):
    loop = _loop(monkeypatch, 0.29)
    await loop._think_tick()
    loop._act_on.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["stop", "pause"])
async def test_a_real_gate_stop_or_pause_still_blocks_the_action(monkeypatch, verdict):
    gate = MagicMock()
    gate.evaluate.return_value = verdict
    loop = _loop(monkeypatch, 0.8, gate=gate)
    await loop._think_tick()
    loop._act_on.assert_not_awaited()
    # ...and what it was given as coherence is the scheduler's number, not the 0.8 ranking score
    assert gate.evaluate.call_args.kwargs["coherence_score"] == pytest.approx(1.0)


def test_coherence_is_neutral_when_guidance_is_unavailable(monkeypatch):
    loop = AutonomousLoop.__new__(AutonomousLoop)
    monkeypatch.setattr(loop, "_get_guidance", lambda: None)
    assert loop._continue_gate_coherence() == 1.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
