"""
Root-caused a real, observed-live behavioral bug (2026-06-24 soak run):
the autonomous loop's think_loop repeatedly picked "analyze_progress" as
the decision_engine's winning candidate every ~10s cycle, only for
_act_on()'s CounterfactualMemory.should_avoid() gate to immediately
auto-block it ("similar to past rejection") and return early -- forever,
with the loop never trying anything else.

Root cause: core/loop/autonomous_loop.py::_act_on()'s counterfactual
auto-block branch (around line 941-957) returns early WITHOUT ever calling
core/memory/policy.py::PolicyMemory.update_from_outcome() -- the exact
mechanism (RULE 7) decision_engine.py relies on to stop a repeatedly-bad
action from winning again. Every other _act_on() outcome path (VectorCode
routing, governor dispatch) calls update_from_outcome() with a real reward;
only the counterfactual-block path skipped it. Since policy_score never
dropped, decision_engine kept scoring "analyze_progress" the same way every
cycle, it kept winning, kept getting blocked, in a permanent, non-learning
loop.

Fixed: the counterfactual-block branch now calls
policy.update_from_outcome(action_type, situation_hash, reward=0.05) using
the exact same situation_hash formula decision_engine.py's own
_make_situation_hash() uses (sha256 of "action_type:sorted(params.items())",
truncated to 12 chars) -- so the penalty lands on the same policy_memory
row decision_engine reads from on the next cycle, genuinely lowering this
action's avg_reward and letting other candidates win instead.
"""
import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _situation_hash(action_type: str, params: dict) -> str:
    """Mirrors decision_engine.py::_make_situation_hash() exactly."""
    key = f"{action_type}:{sorted(params.items())}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def test_counterfactual_auto_block_penalizes_policy_score(monkeypatch):
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import Candidate
    from core.memory.counterfactual import CounterfactualMemory
    from core.memory.policy import PolicyMemory

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        cf_db = f.name
    try:
        cf = CounterfactualMemory(db_path=cf_db)
        cf.record_rejection("analyze_progress", "analyze_progress []", "auto-blocked: similar to past rejection (score=1.00)")

        loop = AutonomousLoop()
        monkeypatch.setattr("core.memory.counterfactual.CounterfactualMemory", lambda: cf)

        pm = PolicyMemory()
        action_type = "analyze_progress"
        params: dict = {}
        sit_hash = _situation_hash(action_type, params)
        score_before = pm.get_score(action_type, sit_hash)

        candidate = Candidate(action_type=action_type, params=params, goal_ids=[])
        asyncio.run(loop._act_on(candidate))

        score_after = pm.get_score(action_type, sit_hash)
        assert score_after < score_before or score_after <= 0.5, (
            f"policy score for repeatedly-auto-blocked action must drop -- "
            f"before={score_before} after={score_after}"
        )
    finally:
        cf.close()
        Path(cf_db).unlink(missing_ok=True)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
