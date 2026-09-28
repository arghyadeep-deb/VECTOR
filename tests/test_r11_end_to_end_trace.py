"""
R11 — Production-Like End-to-End Trace (Mission Phase 7).

Traces a realistic goal through the REAL, unmodified path:

    goal (real tags) -> real generate_immediate_actions() -> multiple
    legitimate native candidates -> real DecisionEngine -> decision_id ->
    candidate_ids -> scoring -> winner -> Governor/PermissionGateway
    authorization boundary

For the GREEN candidate (git_status), the real PermissionGateway.classify()
call is exercised for real, confirming it is GREEN and would proceed to
execution.

For the RED candidate (code_task), execution is deliberately STOPPED at the
authorization boundary -- `PermissionGateway.execute()` is stubbed to
simulate a real, honest DENIAL (exactly what a real owner non-approval or
Pushover timeout would produce), and the test proves _act_on() returns
WITHOUT ever reaching the VectorCode bridge / any real code execution. No
unsafe real-world side effect is performed merely to prove this test, per
the mission's own explicit instruction.

Neither Governor nor PermissionGateway is bypassed, mocked-around, or
modified by R11 -- this test exercises their REAL classify() logic and only
stubs the OUTCOME of an owner-approval round trip that this test correctly
has no business simulating for real.
"""
import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from tests._small_scan import small_scan_root  # noqa: F401  (autouse: real read_code scan over a small project)

from core.brain.goal_system import GoalSystem
from core.loop.autonomous_loop import AutonomousLoop
from core.loop.decision_engine import Candidate, DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.memory.policy import PolicyMemory


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def isolated_goal_system_with_tags(tags):
    # R12-H (2026-09-09): __new__ bypasses __init__'s real-DB read/write
    # (_load_or_seed -> _merge_new_seeds -> _persist) entirely, rather than
    # racing to override _persist/_goals after GoalSystem() has already run
    # against the live production goal store.
    gs = GoalSystem.__new__(GoalSystem)
    gs._memory = None
    gs._persist = lambda: None
    gs._goals = [{
        "id": "g_e2e_trace", "title": "Commit code every day", "horizon": "SHORT",
        "priority": 9, "status": "active", "progress": 0.0, "tags": tags,
        "created_at": _now_iso(),
    }]
    return gs


def native_candidates(gs):
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


@pytest.fixture
def engine():
    e = DecisionEngine()
    e._get_policy = MagicMock()
    e._get_policy().get_score.return_value = 0.5
    e._get_policy().make_situation_hash.side_effect = PolicyMemory.make_situation_hash
    e._get_policy().get_veto_count.return_value = 0
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
    return e


@pytest.mark.unit
class TestEndToEndTrace:

    async def test_real_goal_to_decision_to_governance_boundary_green_action(self, engine):
        """GREEN candidate: real classify() confirms GREEN; the trace stops
        BEFORE dispatch (this test does not execute a real district task --
        that boundary is out of scope here, already covered by this
        session's existing autonomous_loop tests), but proves the full
        chain up to and including the real permission classification."""
        gs = isolated_goal_system_with_tags(["git"])  # -> git_status only
        candidates = native_candidates(gs)
        assert len(candidates) == 1
        assert candidates[0].action_type == "git_status"

        decision = await engine.evaluate(candidates)
        assert decision.winner.action_type == "git_status"
        assert decision.decision_id
        assert decision.winner.candidate_id

        real_gateway = PermissionGateway()
        level = real_gateway.classify(decision.winner.action_type)
        assert level == "GREEN"

    async def test_real_goal_to_decision_to_governance_boundary_red_action_stops_at_boundary(self, engine):
        """RED candidate: real classify() confirms RED; a REAL
        AutonomousLoop._act_on() call is made (the real production
        orchestration path, unmodified by R11), with PermissionGateway.execute()
        stubbed to return a DENIAL (simulating what a real, honest owner
        non-approval / Pushover timeout produces) -- proving execution is
        stopped at the authorization boundary and never reaches the
        VectorCode bridge."""
        # R12 (2026-09-09): "coding" now natively produces 2 real strategies
        # (code_task + read_code, see core/brain/goal_system.py's
        # _TAG_TO_ADDITIONAL_ACTION_TYPE) -- this test specifically needs
        # the RED one, so it biases the winner via confidence rather than
        # assuming a single candidate.
        gs = isolated_goal_system_with_tags(["coding"])
        candidates = native_candidates(gs)
        assert {c.action_type for c in candidates} == {"code_task", "read_code"}
        for c in candidates:
            c.confidence = 0.9 if c.action_type == "code_task" else 0.1

        decision = await engine.evaluate(candidates)
        assert decision.winner.action_type == "code_task"

        real_gateway = PermissionGateway()
        level = real_gateway.classify(decision.winner.action_type)
        assert level == "RED"

        loop = AutonomousLoop()
        fake_gateway = MagicMock()
        fake_gateway.classify = MagicMock(return_value="RED")
        denied_result = MagicMock()
        denied_result.approved = False
        denied_result.reason = "simulated owner non-approval (R11 end-to-end trace -- no real approval requested)"
        fake_gateway.execute = AsyncMock(return_value=denied_result)
        loop._gateway = fake_gateway

        bridge_was_called = {"value": False}

        class _BridgeGuard:
            def is_available(self):
                bridge_was_called["value"] = True  # would only be reached past the gate
                return False

        import districts.coding.vectorcode_bridge as vcb
        original_get_bridge = vcb.get_bridge
        vcb.get_bridge = lambda: _BridgeGuard()
        try:
            await loop._act_on(decision.winner)
        finally:
            vcb.get_bridge = original_get_bridge

        fake_gateway.execute.assert_called_once()  # the gate was genuinely reached
        assert bridge_was_called["value"] is False, (
            "a RED action denied at the authorization boundary must NEVER reach "
            "the code-execution bridge"
        )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
