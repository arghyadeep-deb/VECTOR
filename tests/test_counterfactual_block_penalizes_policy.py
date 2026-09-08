"""
Root-caused a real, observed-live behavioral bug (2026-06-24 soak run):
the autonomous loop's think_loop repeatedly picked "analyze_progress" as
the decision_engine's winning candidate every ~10s cycle, only for
_act_on()'s CounterfactualMemory.should_avoid() gate to immediately
auto-block it ("similar to past rejection") and return early -- forever,
with the loop never trying anything else.

ORIGINAL fix (superseded by Task 89 D3, see below): the counterfactual-block
branch called policy.update_from_outcome(action_type, situation_hash,
reward=0.05) -- a hardcoded literal blended into the same avg_reward
cumulative mean real 5-factor/VectorCode outcomes accumulate into. This did
stop the infinite-reproposal loop (policy_score dropped, letting other
candidates win), but it did so by permanently contaminating the real reward
signal with a control-flow constant that has no relationship to any actual
outcome -- a veto and a genuinely bad execution became indistinguishable in
avg_reward.

Task 89 (D3) — suppression/reward channel separation: the counterfactual-block
branch now calls policy.record_suppression(action_type, situation_hash)
instead. This increments a separate `veto_count` column and leaves
avg_reward/sample_count completely untouched by vetoes -- avg_reward is now
reserved exclusively for real outcomes (VectorCode reward, 5-factor reward).
CounterfactualMemory's own `rejections` table (asserted below, unchanged)
already records every veto in full detail; record_suppression() does not
duplicate that -- it only makes suppression-vs-outcome distinguishable under
PolicyMemory's own canonical (action_type, params) identity.

Residual, explicitly out-of-scope risk: because avg_reward no longer drops on
veto, a candidate whose OTHER four scoring factors (goal_alignment,
confidence, urgency, timing) never change between cycles could in principle
keep winning and keep getting vetoed indefinitely, since nothing in
decision_engine's candidate generation or scoring changed here (Task 89's
scope explicitly excludes DecisionEngine's scoring weights, candidate
generation logic, and the "Goal feedback loop" section of
autonomous_loop.py). The real, durable fix for that class of loop is
decoupling goal.progress from the reward formula so more/different
candidates become eligible over time (tracked separately, not this task) --
suppressing the veto's contamination of avg_reward here is a prerequisite
for that fix to mean anything, not a substitute for it.

Mirrors decision_engine.py's reader via PolicyMemory.make_situation_hash()
directly (the same canonical function both the reader and this test's
writer now call) rather than reimplementing the hash formula locally --
that reimplementation is exactly the kind of format drift Task 89 fixed.
"""
import asyncio
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_counterfactual_auto_block_records_suppression_not_reward(monkeypatch):
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import Candidate
    from core.memory.counterfactual import CounterfactualMemory
    from core.memory.policy import PolicyMemory

    # PolicyMemory has no db_path override -- it always uses the shared,
    # real episodic-memory connection (the same DB the live autonomous
    # loop, if running, also writes to). Use a unique action_type so this
    # test's situation_hash can never collide with real production rows.
    action_type = f"test_auto_block_{uuid.uuid4().hex[:8]}"

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cf_db = f.name
    try:
        cf = CounterfactualMemory(db_path=cf_db)
        # Must match _act_on()'s exact proposal construction:
        # f"{winner.action_type} {json.dumps(winner.params, default=str)}"
        cf.record_rejection(action_type, f"{action_type} {{}}", "auto-blocked: similar to past rejection (score=1.00)")

        loop = AutonomousLoop()
        monkeypatch.setattr("core.memory.counterfactual.CounterfactualMemory", lambda: cf)

        pm = PolicyMemory()
        params: dict = {}
        sit_hash = pm.make_situation_hash(action_type, params)
        score_before = pm.get_score(action_type, sit_hash)

        assert score_before == pm.DEFAULT_SCORE, "no policy row should exist yet (sanity check)"

        candidate = Candidate(action_type=action_type, params=params, goal_ids=[])
        asyncio.run(loop._act_on(candidate))

        score_after = pm.get_score(action_type, sit_hash)
        assert score_after == pm.DEFAULT_SCORE, (
            "Task 89 (D3): a counterfactual veto must NOT change avg_reward -- "
            f"expected the untouched default ({pm.DEFAULT_SCORE}), got {score_after}. "
            "If this fails, the veto path is writing through update_from_outcome() "
            "again instead of record_suppression()."
        )

        # Suppression must still be genuinely recorded -- just in a separate
        # channel (veto_count), not avg_reward.
        from core.memory.episodic import get_temp_cursor
        with get_temp_cursor() as cursor:
            row = cursor.execute(
                "SELECT veto_count, avg_reward, sample_count FROM policy_memory "
                "WHERE action_type=? AND situation_hash=?",
                (action_type, sit_hash),
            ).fetchone()
        assert row is not None, "record_suppression() must create a policy_memory row"
        veto_count, avg_reward, sample_count = row
        assert veto_count == 1, f"expected veto_count=1, got {veto_count}"
        assert avg_reward is None, f"expected avg_reward untouched (NULL), got {avg_reward}"
        assert sample_count == 0, f"expected sample_count untouched (0), got {sample_count}"

        # CounterfactualMemory's own rejections table is unchanged by this
        # task -- the veto is still recorded there, in full, exactly as before.
        assert cf.should_avoid(f"{action_type} {{}}", threshold=0.7)[0], (
            "CounterfactualMemory.should_avoid() must still recognize the "
            "recorded rejection -- record_suppression() is additive, not a "
            "replacement for CounterfactualMemory's own tracking"
        )
    finally:
        cf.close()
        Path(cf_db).unlink(missing_ok=True)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
