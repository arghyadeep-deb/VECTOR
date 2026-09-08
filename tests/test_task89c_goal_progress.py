"""
Task 89C — Goal Progress Semantics regression tests.

Bug: core/loop/autonomous_loop.py's "Goal feedback loop" block called
GoalSystem.update_goal_progress() with a reward-scaled increment on every
successful action linked to a goal. Because update_goal_progress()
unconditionally sets status="completed" once progress >= 1.0 (no completion-
criterion check), pure reward accumulation could — and did, in production —
silently and permanently auto-complete a goal that should never have had a
one-time "done" state (g_daily_commit, a recurring/habitual goal).

Fix: the reward-derived update_goal_progress() call site was removed from
autonomous_loop.py (see the "Goal feedback loop: REMOVED 2026-09-08" comment
around _act_on()). This file proves that removal:

1. A real-outcome reward processed by AutonomousLoop._act_on() no longer
   changes goal.progress for the linked goal.
2. Repeating (1) many times never drives progress to >= 1.0 and never
   auto-completes the goal.
3. An EXPLICIT call to GoalSystem.update_goal_progress(goal_id, 1.0, ...)
   (simulating a genuine external/API caller) still sets status="completed"
   — the pre-existing explicit mechanism is untouched.
4. A goal already "completed" stays "completed" through any sequence of
   reward-processing events — never reactivated.
5. decision_engine.py's goal_alignment scoring for a goal does not change
   merely because a reward was emitted for an action linked to that goal
   (decision_engine.py itself is read-only in this task — not modified).
6. generate_immediate_actions()'s candidate output does not silently shrink
   as a side effect of reward processing when progress genuinely didn't move.
7. Historical/pre-existing goal data reads back unchanged across a fresh
   GoalSystem load — no migration, no rewrite.

Per this project's testing convention (.claude/rules/testing.md: "SQLite
episodic_memory — use a test DB, not mocks"), this suite uses a REAL
GoalSystem backed by an isolated temp-file SQLite DB (VECTOR_DB_PATH
override, set before any VECTOR module import) rather than mocking
goal_system.py or episodic storage. Only unrelated heavy subsystems
(governor.dispatch, policy memory, episodic recall/store_chain) are stubbed
so the test exercises the real reward-computation + goal-feedback code path
in _act_on() without triggering real district dispatch, network calls, or
Pushover notifications.

Run in isolation (NOT as part of the full suite — see Task 89 instructions):
    pytest tests/test_task89c_goal_progress.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# --- Redirect VECTOR's memory DB to an isolated temp file BEFORE any VECTOR
# module import touches core.memory.episodic (module-level singleton
# connection + singleton DB key). Must happen at import time of this file,
# and this file must be run in isolation (not mixed into a session where
# another test module already opened the real/default DB).
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["VECTOR_DB_PATH"] = _TMP_DB.name
os.environ.setdefault("VECTOR_DB_KEY", "test-only-key-not-for-production-task89c")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock, AsyncMock

import pytest

from core.brain.goal_system import GoalSystem
from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import DecisionEngine, Candidate


def make_winner(action_type="test_action_89c", goal_ids=None, params=None):
    return Candidate(
        action_type=action_type,
        params=params or {},
        goal_ids=goal_ids or [],
        confidence=0.6,
        urgency=0.5,
        timing_score=1.0,
        estimated_cost_inr=0.0,
    )


@pytest.fixture
def loop_with_fake_governor():
    """Real AutonomousLoop + real GoalSystem (temp DB). Only the governor
    dispatch (district execution), policy memory, and episodic
    recall/store_chain are stubbed — none of those are what this task
    changed or what these tests are about."""
    loop = AutonomousLoop()

    fake_governor = MagicMock()
    fake_governor.dispatch = AsyncMock(return_value={"status": "ok"})
    loop._governor = fake_governor

    fake_policy = MagicMock()
    fake_policy.update_from_outcome = MagicMock()
    fake_policy.get_score = MagicMock(return_value=0.5)
    loop._policy = fake_policy

    fake_memory = MagicMock()
    fake_memory.recall = MagicMock(return_value=[])
    fake_memory.store_chain = MagicMock()
    loop._memory = fake_memory

    return loop


@pytest.mark.unit
async def test_reward_does_not_mutate_linked_goal_progress(loop_with_fake_governor):
    """C1 — a successful action's reward must not change goal.progress."""
    loop = loop_with_fake_governor
    gs = loop._get_goals()  # real GoalSystem, real (temp) DB
    goal_id = "g_daily_commit"
    before = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    before_progress = before["progress"]
    before_status = before["status"]

    winner = make_winner(goal_ids=[goal_id])
    await loop._act_on(winner)

    after = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    assert after["progress"] == before_progress, "reward processing must not change goal.progress"
    assert after["status"] == before_status


@pytest.mark.unit
async def test_repeated_reward_never_completes_goal(loop_with_fake_governor):
    """C2 — repeating the reward path many times must never drive progress to
    >= 1.0 or auto-complete the goal."""
    loop = loop_with_fake_governor
    gs = loop._get_goals()
    goal_id = "g_karpathy_30"

    for _ in range(50):
        winner = make_winner(goal_ids=[goal_id])
        await loop._act_on(winner)

    goal = next(g for g in gs.get_active_goals() if g["id"] == goal_id)
    assert goal["progress"] == 0.0
    assert goal["status"] == "active"


@pytest.mark.unit
def test_explicit_update_goal_progress_still_completes():
    """C6 — the pre-existing explicit (human/API) completion mechanism must
    still work exactly as before: update_goal_progress()'s unconditional
    progress>=1.0 -> status="completed" transition is untouched."""
    gs = GoalSystem()
    new_id = gs.add_goal("Explicit completion probe 89C", "SHORT", priority=1)
    ok = gs.update_goal_progress(new_id, 1.0, note="explicit test completion")
    assert ok is True
    goal = next(g for g in gs._goals if g["id"] == new_id)
    assert goal["progress"] == 1.0
    assert goal["status"] == "completed"


@pytest.mark.unit
async def test_completed_goal_never_reactivated(loop_with_fake_governor):
    """C4 — a goal already completed stays completed through any sequence of
    reward-processing events; never reactivated."""
    loop = loop_with_fake_governor
    gs = loop._get_goals()
    new_id = gs.add_goal("Already-completed probe 89C", "SHORT", priority=1)
    gs.update_goal_progress(new_id, 1.0, note="explicit completion")
    goal = next(g for g in gs._goals if g["id"] == new_id)
    assert goal["status"] == "completed"

    for _ in range(10):
        winner = make_winner(goal_ids=[new_id])
        await loop._act_on(winner)

    goal_after = next(g for g in gs._goals if g["id"] == new_id)
    assert goal_after["status"] == "completed"
    assert goal_after["progress"] == 1.0
    assert new_id not in {g["id"] for g in gs.get_active_goals()}


@pytest.mark.unit
async def test_goal_alignment_score_unchanged_by_reward(loop_with_fake_governor):
    """C5 — decision_engine.py's goal_alignment score for a goal must not move
    merely because a reward was just emitted for an action linked to that
    goal, since its progress didn't move. decision_engine.py is read-only in
    this task — not modified."""
    loop = loop_with_fake_governor
    gs = loop._get_goals()
    goal_id = "g_placement_prep"  # preseeded, progress 0.0, untouched by other tests

    engine = DecisionEngine()
    engine._get_goals = MagicMock(return_value=gs)

    probe = Candidate(action_type="probe", params={}, goal_ids=[goal_id],
                       confidence=0.5, urgency=0.5, timing_score=1.0)
    score_before = engine._score_goal_alignment(probe)

    for _ in range(5):
        winner = make_winner(goal_ids=[goal_id])
        await loop._act_on(winner)

    probe2 = Candidate(action_type="probe", params={}, goal_ids=[goal_id],
                        confidence=0.5, urgency=0.5, timing_score=1.0)
    score_after = engine._score_goal_alignment(probe2)

    assert score_after == score_before


@pytest.mark.unit
async def test_generate_immediate_actions_not_shrunk_by_reward_processing(loop_with_fake_governor):
    """Regression guard (not candidate-diversity work) — a goal eligible for
    the LONG/MID 'unstarter' branch before reward-processing activity is
    still eligible after, since its progress genuinely didn't change."""
    loop = loop_with_fake_governor
    gs = loop._get_goals()
    new_id = gs.add_goal("Unstarter branch probe 89C", "MID", priority=5)

    before = gs.generate_immediate_actions(limit=50)
    before_ids = {a["goal_id"] for a in before}
    assert new_id in before_ids, "fresh zero-progress MID goal must be unstarter-eligible"

    winner = make_winner(goal_ids=[new_id])
    await loop._act_on(winner)

    after = gs.generate_immediate_actions(limit=50)
    after_ids = {a["goal_id"] for a in after}
    assert new_id in after_ids, "goal must still be candidate-eligible — progress did not change"


@pytest.mark.unit
def test_historical_goal_state_read_back_unchanged():
    """C3/C7 — historical progress/status values are not migrated or
    rewritten merely by loading GoalSystem again. Simulates a goal that was
    already at progress=0.076 (or completed) before this fix — that value
    must read back byte-identical, with no migration path touching it."""
    gs1 = GoalSystem()
    gs1.update_goal_progress("g_kiit_attendance", 0.076, note="historical baseline (pre-fix)")

    gs2 = GoalSystem()  # fresh load from the same persisted (temp) store
    goal = next(g for g in gs2._goals if g["id"] == "g_kiit_attendance")
    assert goal["progress"] == 0.076
    assert goal["status"] == "active"

    # g_daily_commit's real production state is progress=1.0/status=completed
    # (established fact per Task 89 brief) — verify complete_goal()/
    # update_goal_progress() reproduces and preserves that exact state
    # without any special-casing or reversal logic anywhere in this fix.
    gs1.update_goal_progress("g_daily_commit", 1.0, note="simulated pre-existing completion")
    gs3 = GoalSystem()
    dc = next(g for g in gs3._goals if g["id"] == "g_daily_commit")
    assert dc["progress"] == 1.0
    assert dc["status"] == "completed"


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"],
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    print("[OK] test_task89c_goal_progress" if result.returncode == 0 else "[FAILED] test_task89c_goal_progress")
