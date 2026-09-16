"""
RR-3 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/RR3_OVERNIGHT_REMEDIATION_REPORT.md):
overnight remediation mission covering three proven-minimal repairs:

RR-3.1 -- a RED/YELLOW skill-matched action denied by the PermissionGateway
used to fall through to the ungated general `governor.dispatch()` path
instead of stopping. Fixed with a `return` mirroring the existing FORBIDDEN
branch's pattern.

RR-3.2 -- failure evidence connection: (a) an uncaught exception in
_act_on()'s try block used to reach ONLY RetryQueue (pure infrastructure),
never PolicyMemory/EpistemicTracker/CausalGraph, so repeated real crashes
for the same action_type produced zero decision-relevant learning; (b)
`blocked` (a Governor-internal security-policy veto) and `no_capable_agent`
(a routing gap, not a capability defect) were being fed into
EpistemicTracker identically to a genuine `error`/`failed`/`timeout`,
incorrectly teaching "this capability doesn't work" from a security
denial or a routing gap.

RR-3.3 -- plan-step execution used to skip three native soft-safety
pre-checks (CounterfactualMemory, ThreatDetector, RedTeamAgent) because
`_act_on()`'s plan branch returned before ever reaching them. Fixed by
extracting the three existing blocks into a shared `_run_soft_safety_checks()`
helper invoked identically by both the native and plan-step paths -- a pure
refactor-and-reuse, no PermissionGateway change, no planner redesign.

Per this repo's testing rules: no mocking of permission_gateway.py's real
classification/approval logic, no mocking of PolicyMemory/CausalGraph/
EpistemicTracker (real singletons, fresh uuid-unique action_types per test
so nothing collides with real production rows). Only governor.dispatch(),
SkillManager, and (where a test needs to isolate one seam) the gateway's
own `.execute()`/`.classify()` methods are stubbed -- mirroring the
established pattern in tests/test_policy_reward_identity.py and
tests/test_rr2_meaningful_utility.py.
"""
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================
# RR-3.1 -- skill-match gateway denial must stop execution
# ============================================================

def test_rr3_1_denied_red_skill_action_does_not_fall_through_to_ungated_dispatch(monkeypatch):
    """A RED-tier action that matches a skill and is explicitly DENIED by the
    gateway must never reach governor.dispatch() via the general fallback
    path. Before the fix, `_skill_allowed=False` alone did not stop
    execution -- `_skill_executed` stayed False and control fell through to
    `if not _skill_executed: result = await governor.dispatch(...)`, an
    ungated path with no permission check of its own."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import Candidate
    from core.loop.permission_gateway import GatewayResult

    action_type = f"test_rr3_skill_denied_{uuid.uuid4().hex[:8]}"
    loop = AutonomousLoop()

    class _FakeSkill:
        name = "fake_red_skill"
        confidence = 0.9

    class _FakeSkillManager:
        def match(self, action_type, params):
            return [_FakeSkill()]

        def execute(self, name, params):
            raise AssertionError("sm.execute() must not run after a gateway denial")

    monkeypatch.setattr(
        "vectorcode.src.skills.manager.SkillManager", lambda: _FakeSkillManager()
    )

    class _FakeGateway:
        def classify(self, action_type):
            return "RED"

        async def execute(self, action):
            return GatewayResult(
                approved=False, level="RED", executed=False,
                result={}, reason="owner rejected",
            )

    monkeypatch.setattr(loop, "_get_gateway", lambda: _FakeGateway())

    _dispatch_calls = {"count": 0}

    class _FakeGovernor:
        async def dispatch(self, task):
            _dispatch_calls["count"] += 1
            return {"status": "ok"}

    monkeypatch.setattr(loop, "_get_governor", lambda: _FakeGovernor())
    monkeypatch.setattr(loop, "_get_recent_feedback", lambda action_type: None)

    candidate = Candidate(action_type=action_type, params={}, goal_ids=[])
    asyncio.run(loop._act_on(candidate))

    assert _dispatch_calls["count"] == 0, (
        "governor.dispatch() must NEVER be called after the gateway explicitly "
        "denied this exact action -- a denial must stop execution entirely, "
        "not just skip the skill-specific execution route"
    )


def test_rr3_1_approved_yellow_skill_action_still_executes(monkeypatch):
    """Control: a YELLOW skill action the gateway APPROVES must still execute
    via the skill handler (proves the fix didn't turn the approval path into
    a dead end -- only denial should stop execution)."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import Candidate
    from core.loop.permission_gateway import GatewayResult

    action_type = f"test_rr3_skill_approved_{uuid.uuid4().hex[:8]}"
    loop = AutonomousLoop()

    _executed = {"count": 0}

    class _FakeSkillResult:
        status = "ok"

    class _FakeSkill:
        name = "fake_yellow_skill"
        confidence = 0.9

    class _FakeSkillManager:
        def match(self, action_type, params):
            return [_FakeSkill()]

        def execute(self, name, params):
            _executed["count"] += 1
            return _FakeSkillResult()

    monkeypatch.setattr(
        "vectorcode.src.skills.manager.SkillManager", lambda: _FakeSkillManager()
    )

    class _FakeGateway:
        def classify(self, action_type):
            return "YELLOW"

        async def execute(self, action):
            return GatewayResult(
                approved=True, level="YELLOW", executed=True,
                result={"status": "ok"}, reason="owner approved",
            )

    monkeypatch.setattr(loop, "_get_gateway", lambda: _FakeGateway())

    class _FakeGovernor:
        async def dispatch(self, task):
            raise AssertionError("governor.dispatch() must not run when the skill handler executed")

    monkeypatch.setattr(loop, "_get_governor", lambda: _FakeGovernor())
    monkeypatch.setattr(loop, "_get_recent_feedback", lambda action_type: None)

    candidate = Candidate(action_type=action_type, params={}, goal_ids=[])
    asyncio.run(loop._act_on(candidate))

    assert _executed["count"] == 1, "an approved YELLOW skill action must still execute via the skill handler"
