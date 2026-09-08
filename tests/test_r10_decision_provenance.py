"""
R10 — Decision Provenance: end-to-end retrieval proof.

R7 (Task 92) already introduced `decision_id`/`candidate_id` on the
`Candidate`/`Decision` dataclasses and propagated them into four existing,
already-schemaless sinks: the episodic `decision_candidate` log,
`CounterfactualMemory.rejections`' existing `decision_id`/`context` params,
`loop_state.save_decision()`'s JSON payload, and `reasoning_chains.steps`'
appended correlation entry. R7's own tests proved this via CALL-SITE
assertions (the right values were passed to the right mocked/real methods).

R10's audit re-confirmed that design is unchanged and complete (no missing
edge required a schema redesign; STOP conditions never triggered) and adds
the one thing R7's own tests did not: proof that a decision's correlation is
GENUINELY RETRIEVABLE from real, persisted storage after the fact -- not just
that the right values were passed into a write call. This file does that with
a REAL EpisodicMemory + REAL CounterfactualMemory, both backed by isolated
temp-file databases (CounterfactualMemory takes a `db_path` constructor arg
directly; EpisodicMemory is a module-level singleton keyed off the
`VECTOR_DB_PATH` env var, so this file follows the exact isolation pattern
already established in tests/test_task89c_goal_progress.py: set the env var
before any VECTOR import, and note that this file must be run standalone,
never as part of a combined multi-file session).

Per .claude/rules/testing.md ("SQLite episodic_memory -- use a test DB, not
mocks"), this is a genuine SQLite round-trip against real tables, not an
assertion about mock call arguments.

Run standalone:
    pytest tests/test_r10_decision_provenance.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["VECTOR_DB_PATH"] = _TMP_DB.name
os.environ.setdefault("VECTOR_DB_KEY", "test-only-key-not-for-production-r10")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import Candidate, DecisionEngine
from core.memory.policy import PolicyMemory


def make_candidate(action_type, confidence=0.6, urgency=0.5, params=None):
    return Candidate(action_type=action_type, params=params or {}, confidence=confidence, urgency=urgency)


def _query_reasoning_chains(like_pattern: str) -> list[tuple]:
    """Real SQL read against the SAME isolated, SQLCipher-encrypted db
    EpisodicMemory's singleton is writing to -- via the module's own
    connection helper (get_temp_cursor), which already knows the encryption
    key. A plain sqlite3.connect() cannot open this file directly (SQLCipher
    encrypted, not plain SQLite) -- this proves genuine retrievability
    through the real storage layer, not a bypass of it. Returns
    (reward, steps) tuples -- this connection has no row_factory set."""
    from core.memory.episodic import get_temp_cursor
    with get_temp_cursor() as cursor:
        cursor.execute(
            "SELECT reward, steps FROM reasoning_chains WHERE steps LIKE ?",
            (like_pattern,),
        )
        return cursor.fetchall()


@pytest.fixture
def loop_with_fakes():
    """Real AutonomousLoop._act_on() + REAL EpisodicMemory (isolated temp
    db) + REAL DecisionEngine.evaluate(). Only Governor/PolicyMemory are
    stubbed -- neither is part of what R10 is proving."""
    loop = AutonomousLoop()
    fake_governor = MagicMock()
    fake_governor.dispatch = AsyncMock(return_value={"status": "ok", "goal_progress": 0.5})
    loop._governor = fake_governor

    fake_policy = MagicMock()
    fake_policy.get_score = MagicMock(return_value=0.5)
    fake_policy.make_situation_hash = MagicMock(side_effect=PolicyMemory.make_situation_hash)
    fake_policy.update_from_outcome = MagicMock()
    fake_policy.record_suppression = MagicMock()
    loop._policy = fake_policy
    return loop


async def _real_decision(action_type, params=None):
    """A real DecisionEngine.evaluate() call -- real decision_id/candidate_id,
    only unrelated heavy subsystems (policy hash aside) stubbed."""
    e = DecisionEngine()
    e._get_policy = MagicMock()
    e._get_policy().get_score.return_value = 0.5
    e._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
    e._get_goals = MagicMock()
    e._get_goals().get_active_goals.return_value = []
    e._get_memory = MagicMock()  # decision_engine's own per-candidate log -- not what this test reads back
    e._get_memory().store.return_value = None
    e._get_epistemic = MagicMock()
    e._get_epistemic().get_belief.return_value = None
    e._get_reasoning_bank = MagicMock(return_value=None)
    e._get_neural_trainer = MagicMock(return_value=None)
    e._get_context_engine = MagicMock()
    e._get_context_engine().get_world_state.return_value = {}
    e._get_correction_learner = MagicMock(return_value=None)
    return await e.evaluate([make_candidate(action_type, params=params)])


@pytest.mark.asyncio
async def test_decision_to_outcome_to_persisted_reward_retrievable_by_decision_id(loop_with_fakes):
    """The task's own required chain:
        decision D -> candidates A/B -> A wins -> outcome recorded ->
        reward recorded -> later retrieval identifies D
    proven against REAL persisted storage, not mock call arguments."""
    decision = await _real_decision("r10_exec_action", params={"p": 1})
    winner = decision.winner
    winner.reasoning_chain = [{"factor": "goal_alignment", "value": 0.5, "weight": 0.3}]

    await loop_with_fakes._act_on(winner)

    rows = _query_reasoning_chains(f"%{winner.decision_id}%")
    assert len(rows) == 1, f"expected exactly one reasoning_chains row for {winner.decision_id}"
    reward, steps_json = rows[0]
    steps = json.loads(steps_json)
    correlation = next(s["correlation"] for s in steps if "correlation" in s)
    assert correlation["decision_id"] == winner.decision_id
    assert correlation["candidate_id"] == winner.candidate_id
    assert reward is not None  # a real reward value was persisted alongside the id


@pytest.mark.asyncio
async def test_unrelated_outcome_cannot_attach_to_a_different_decision(loop_with_fakes):
    """Adversarial requirement: an unrelated outcome must not be retrievable
    under a decision_id it does not belong to."""
    decision1 = await _real_decision("r10_action_one", params={})
    winner1 = decision1.winner
    winner1.reasoning_chain = [{"factor": "x", "value": 1, "weight": 1}]
    await loop_with_fakes._act_on(winner1)

    decision2 = await _real_decision("r10_action_two", params={})
    winner2 = decision2.winner
    winner2.reasoning_chain = [{"factor": "y", "value": 2, "weight": 1}]
    await loop_with_fakes._act_on(winner2)

    assert winner1.decision_id != winner2.decision_id

    rows_for_1 = _query_reasoning_chains(f"%{winner1.decision_id}%")
    assert len(rows_for_1) == 1
    _, steps_json = rows_for_1[0]
    steps = json.loads(steps_json)
    assert winner2.decision_id not in json.dumps(steps), (
        "decision 2's identity must never appear in decision 1's persisted record"
    )


@pytest.mark.asyncio
async def test_same_situation_hash_aggregates_legitimately_across_distinct_decisions():
    """The reusable situation_hash (PolicyMemory identity) is DIFFERENT from
    decision_id/candidate_id -- two decisions of the same action_type/params
    share one situation_hash (legitimate aggregation for policy learning)
    while their decision_id/candidate_id remain fully distinct (per-occurrence
    identity). Both properties proven together, not asserted independently."""
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
    e._get_correction_learner = MagicMock(return_value=None)

    params = {"goal_id": "g_repeat_r10"}
    d1 = await e.evaluate([make_candidate("r10_repeat_action", params=params)])
    d2 = await e.evaluate([make_candidate("r10_repeat_action", params=params)])

    h1 = e._make_situation_hash(d1.winner)
    h2 = e._make_situation_hash(d2.winner)
    assert h1 == h2, "same action_type+params must share one reusable situation_hash"
    assert d1.decision_id != d2.decision_id
    assert d1.winner.candidate_id != d2.winner.candidate_id


@pytest.mark.asyncio
async def test_veto_retains_decision_identity_in_real_counterfactual_storage(loop_with_fakes):
    """Veto/rejection correlation, proven against a REAL CounterfactualMemory
    backed by an isolated temp db (not the episodic singleton -- this table
    has its own constructor db_path arg)."""
    from core.memory.counterfactual import CounterfactualMemory

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cf_db = f.name
    try:
        cf = CounterfactualMemory(db_path=cf_db)
        action_type = "r10_veto_action"
        proposal_seed = f"{action_type} {{}}"
        cf.record_rejection("seed", proposal_seed, "seed rejection for should_avoid()")

        import unittest.mock as _mock
        with _mock.patch("core.memory.counterfactual.CounterfactualMemory", lambda: cf):
            decision = await _real_decision(action_type, params={})
            winner = decision.winner
            await loop_with_fakes._act_on(winner)

        conn = sqlite3.connect(cf_db)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT decision_id, context FROM rejections WHERE decision_id = ?",
                (winner.decision_id,),
            ).fetchall()
            assert len(rows) == 1, "the veto must be retrievable by the exact real decision_id"
            ctx = json.loads(rows[0]["context"]) if rows[0]["context"] else {}
            assert ctx.get("candidate_id") == winner.candidate_id
        finally:
            conn.close()
        cf.close()
    finally:
        Path(cf_db).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
