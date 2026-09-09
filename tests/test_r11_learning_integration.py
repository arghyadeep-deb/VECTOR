"""
R11 — Learning Integration Test (Mission Phase 4).

Question: given candidates the REAL, native, tag-derived candidate generator
produces (never hand-constructed after generation), can VECTOR's EXISTING
learning machinery (PolicyMemory) genuinely change which one wins, using a
real, persisted, restart-surviving reward signal?

Protocol (exactly as the mission specifies):
    1. one realistic goal, tags mapping to >= 2 real distinct action_types
       (git_status GREEN, code_task RED)
    2. real GoalSystem.generate_immediate_actions() generates BOTH natively
       (never injected by hand)
    3. real DecisionEngine.evaluate() -- record decision_id, candidate_ids,
       situation hashes, scores, winner
    4. a real, legitimate PolicyMemory.update_from_outcome() call establishes
       historical evidence for one of the two natively generated
       action_types' exact real situation
    5. a genuine restart: close the SQLite connection, reopen against the
       SAME on-disk file (not a simulation)
    6. the SAME goal, freshly and NATIVELY regenerated (not reused objects)
       -> evaluate() again -> record the same fields
    7. determine whether the winner changed
    8. rule out confounds: an UNRELATED goal's natively generated candidate
       is unaffected; a genuine restart with NO learning applied (control)
       does not flip the winner

This is NOT PolicyMemory learning in isolation (E1 already proved that with
hand-built candidates) — it is the same causal chain, but with the
CANDIDATES themselves coming from the real, fixed R11 generator, closing
the exact gap E6 found: LAB (hand-built candidates) vs NATIVE (candidates
the real production pipeline actually produces).

Per .claude/rules/testing.md and this session's own established convention
(tests/test_e1_persistent_learning.py, tests/test_r10_decision_provenance.py,
tests/test_task89c_goal_progress.py), PolicyMemory has no db_path override —
it always uses the shared episodic-memory singleton connection — so this
file sets VECTOR_DB_PATH before any VECTOR import and must be run standalone,
never mixed into a combined pytest session with other files that import
core.memory.episodic first.

Run standalone:
    pytest tests/test_r11_learning_integration.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["VECTOR_DB_PATH"] = _TMP_DB.name
os.environ.setdefault("VECTOR_DB_KEY", "test-only-key-not-for-production-r11")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import datetime
from unittest.mock import MagicMock

import pytest

from core.brain.goal_system import GoalSystem
from core.loop.decision_engine import Candidate, DecisionEngine
from core.memory.policy import PolicyMemory


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


GOAL_ID = "g_r11_learning_probe"
GOAL_TITLE = "Commit code every day (R11 learning probe)"


def _isolated_goal_system_with_probe_goal(tags: list[str]) -> GoalSystem:
    """Real GoalSystem, real (isolated, per VECTOR_DB_PATH) persistence --
    this file DOES let GoalSystem persist for real, unlike the synchronous
    unit tests in test_r11_native_goal_strategy_candidates.py, because the
    whole point here is a genuine cross-restart round trip through the same
    isolated storage PolicyMemory itself uses."""
    gs = GoalSystem()
    gs._goals = [{
        "id": GOAL_ID, "title": GOAL_TITLE, "horizon": "SHORT",
        "priority": 9, "status": "active", "progress": 0.0,
        "tags": tags, "created_at": _now_iso(),
    }]
    gs._persist()
    return gs


def _isolated_engine() -> DecisionEngine:
    """Real DecisionEngine + REAL PolicyMemory (isolated via VECTOR_DB_PATH,
    same singleton GoalSystem itself uses). Every other subsystem stubbed --
    matches E1's own established isolation pattern exactly."""
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
    # _get_policy intentionally NOT stubbed -- real PolicyMemory, real (isolated) db.
    return e


def _native_candidates(gs: GoalSystem) -> list[Candidate]:
    """The exact production translation autonomous_loop._think_tick() now
    performs. Regenerates FRESH from generate_immediate_actions() every
    call -- never reuses a stale object across the restart boundary."""
    actions = gs.generate_immediate_actions(limit=4)
    return [
        Candidate(
            action_type=a["action_type"],
            params={"goal_id": a["goal_id"], "title": a["title"]},
            goal_ids=[a["goal_id"]],
            urgency={"high": 0.9, "medium": 0.5, "low": 0.2}.get(a.get("urgency", "low"), 0.5),
            confidence=0.7,
            source="think_loop",
        )
        for a in actions
    ]


@pytest.mark.asyncio
async def test_native_candidates_learning_survives_a_real_restart_and_flips_the_winner():
    gs = _isolated_goal_system_with_probe_goal(tags=["coding", "git"])  # code_task listed first
    e1 = _isolated_engine()

    # ---- 1/2/3: real native generation + real DecisionEngine, baseline ----
    baseline_candidates = _native_candidates(gs)
    assert {c.action_type for c in baseline_candidates} == {"code_task", "git_status"}
    baseline_decision = await e1.evaluate(baseline_candidates)
    assert baseline_decision.winner.action_type == "code_task", (
        "sanity check: with no learned history, natively generated code_task "
        "(listed first per tag order) wins the near-tie"
    )
    baseline_decision_id = baseline_decision.decision_id
    baseline_candidate_ids = {c.action_type: c.candidate_id for c in baseline_candidates}

    # ---- 4: a real, legitimate PolicyMemory write for code_task's REAL situation ----
    code_task_candidate = next(c for c in baseline_candidates if c.action_type == "code_task")
    pm = e1._get_policy()
    sit_hash = pm.make_situation_hash(code_task_candidate.action_type, code_task_candidate.params)
    for _ in range(8):
        pm.update_from_outcome(code_task_candidate.action_type, sit_hash, 0.02)  # consistently poor real outcome
    score_after_learning = pm.get_score(code_task_candidate.action_type, sit_hash)
    assert score_after_learning < PolicyMemory.DEFAULT_SCORE, (
        "the real reward signal must have genuinely lowered code_task's learned policy score"
    )

    # ---- 5: genuine restart ----
    from core.memory.episodic import close_db_connection
    close_db_connection()

    # ---- 6: SAME goal, freshly + natively regenerated, fresh engine instance ----
    gs2 = GoalSystem()  # reloads from the SAME isolated persisted store
    e2 = _isolated_engine()
    after_restart_candidates = _native_candidates(gs2)
    assert {c.action_type for c in after_restart_candidates} == {"code_task", "git_status"}, (
        "the goal itself, and its tag-derived candidate set, must survive the restart unchanged"
    )
    after_restart_decision = await e2.evaluate(after_restart_candidates)

    # ---- 7: winner changed ----
    assert after_restart_decision.winner.action_type == "git_status", (
        "persistent, real PolicyMemory learning must survive a genuine restart and flip "
        "the winner between the SAME two natively generated candidates"
    )

    # ---- 8a: R7 provenance -- this is a genuinely DIFFERENT decision occurrence ----
    assert after_restart_decision.decision_id != baseline_decision_id
    after_restart_candidate_ids = {c.action_type: c.candidate_id for c in after_restart_candidates}
    assert after_restart_candidate_ids["code_task"] != baseline_candidate_ids["code_task"]
    assert after_restart_candidate_ids["git_status"] != baseline_candidate_ids["git_status"]

    # ---- 8b: exact persisted score value survives, not just "some" change ----
    after_restart_code_task_candidate = next(c for c in after_restart_candidates if c.action_type == "code_task")
    assert after_restart_code_task_candidate.policy_score == pytest.approx(score_after_learning, abs=0.01)


@pytest.mark.asyncio
async def test_control_unrelated_goal_natively_generated_candidate_is_unaffected():
    """Confound control: a DIFFERENT goal's natively generated code_task
    candidate (distinct params -> distinct situation_hash) must be
    completely unaffected by the learning applied to the probe goal above."""
    gs = GoalSystem()
    gs._goals = [{
        "id": "g_r11_unrelated_probe", "title": "An entirely unrelated goal",
        "horizon": "SHORT", "priority": 5, "status": "active", "progress": 0.0,
        "tags": ["coding"], "created_at": _now_iso(),
    }]
    gs._persist()

    e = _isolated_engine()
    candidates = _native_candidates(gs)
    assert len(candidates) == 1
    assert candidates[0].action_type == "code_task"

    pm = e._get_policy()
    sit_hash = pm.make_situation_hash(candidates[0].action_type, candidates[0].params)
    score = pm.get_score(candidates[0].action_type, sit_hash)
    assert score == PolicyMemory.DEFAULT_SCORE, (
        "an unrelated goal's natively generated candidate must show NO learned "
        "influence from the probe goal's own real, isolated policy history"
    )


@pytest.mark.asyncio
async def test_control_restart_with_no_learning_applied_does_not_flip_the_winner():
    """No-learning control: the exact same restart mechanics (real
    close_db_connection + reopen, natively regenerated candidates) but with
    NO PolicyMemory update applied between runs -- the winner must NOT flip,
    ruling out "restart itself" as a confound."""
    gs = GoalSystem()
    gs._goals = [{
        "id": "g_r11_control_probe", "title": "Commit code every day (control)",
        "horizon": "SHORT", "priority": 9, "status": "active", "progress": 0.0,
        "tags": ["coding", "git"], "created_at": _now_iso(),
    }]
    gs._persist()

    e1 = _isolated_engine()
    candidates1 = _native_candidates(gs)
    decision1 = await e1.evaluate(candidates1)
    assert decision1.winner.action_type == "code_task"

    # No PolicyMemory update here -- this is the control.

    from core.memory.episodic import close_db_connection
    close_db_connection()

    gs2 = GoalSystem()
    e2 = _isolated_engine()
    candidates2 = _native_candidates(gs2)
    decision2 = await e2.evaluate(candidates2)

    assert decision2.winner.action_type == "code_task", (
        "without any real learning applied, a genuine restart alone must NOT "
        "flip the winner -- rules out the restart mechanics themselves as a confound"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
