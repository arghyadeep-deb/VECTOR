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

import pytest

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


# ============================================================
# RR-3.2 -- failure evidence connection
# ============================================================

def _make_isolated_loop(tmp_path, governor_result=None, governor_raises=None):
    """Real AutonomousLoop + real DecisionEngine, with an EpistemicTracker
    isolated to a fresh on-disk DB under tmp_path (EpistemicTracker ignores
    VECTOR_DB_PATH entirely -- see tests/conftest.py's isolated_vector_db
    docstring -- so it must be isolated via its own db_path= kwarg). Only
    governor.dispatch is stubbed; PolicyMemory/CausalGraph use the real
    shared production DB with fresh uuid-unique action_types, matching the
    established convention in tests/test_policy_reward_identity.py and
    tests/test_rr2_meaningful_utility.py."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import DecisionEngine
    from core.brain.epistemic_tracker import EpistemicTracker

    loop = AutonomousLoop()
    engine = DecisionEngine()
    engine._epistemic = EpistemicTracker(db_path=tmp_path / "epistemic_isolated.db")
    loop._decision_engine = engine

    class _FakeGovernor:
        async def dispatch(self, task):
            if governor_raises is not None:
                raise governor_raises
            return dict(governor_result or {"status": "ok"})

    loop._governor = _FakeGovernor()

    from unittest.mock import MagicMock
    fake_memory = MagicMock()
    fake_memory.recall = MagicMock(return_value=[])
    fake_memory.store_chain = MagicMock()
    loop._memory = fake_memory

    return loop, engine


async def _run_n_times(loop, action_type, n):
    from core.loop.decision_engine import Candidate
    for _ in range(n):
        candidate = Candidate(action_type=action_type, params={}, goal_ids=[])
        await loop._act_on(candidate)


def test_rr3_2_blocked_status_does_not_degrade_epistemic_confidence(tmp_path):
    """A Governor-internal security-policy veto (status="blocked", e.g. the
    taint/prompt-injection scanner) is NOT evidence the capability itself
    misbehaves. Before the fix, five repeated "blocked" outcomes for the
    same action_type would degrade its epistemic belief exactly like a
    genuine tool error. After the fix, no belief is ever written for this
    shape -- the domain remains "unknown" (neutral, factor=1.0), not
    penalized."""
    action_type = f"test_rr3_blocked_{uuid.uuid4().hex[:8]}"
    loop, engine = _make_isolated_loop(tmp_path, governor_result={"status": "blocked"})

    asyncio.run(_run_n_times(loop, action_type, 5))

    belief = engine._epistemic.get_belief(f"action_domain:{action_type}")
    assert belief is None, (
        "a repeated security-policy veto ('blocked') must not create any "
        "epistemic belief about this action_type -- it is not evidence the "
        "capability is unreliable"
    )


def test_rr3_2_no_capable_agent_does_not_degrade_epistemic_confidence(tmp_path):
    """A routing gap (status="no_capable_agent" -- no agent anywhere
    declares this capability) is NOT evidence the action itself is broken.
    Must not create epistemic belief, same reasoning as "blocked"."""
    action_type = f"test_rr3_no_agent_{uuid.uuid4().hex[:8]}"
    loop, engine = _make_isolated_loop(tmp_path, governor_result={"status": "no_capable_agent"})

    asyncio.run(_run_n_times(loop, action_type, 5))

    belief = engine._epistemic.get_belief(f"action_domain:{action_type}")
    assert belief is None, (
        "a repeated routing gap ('no_capable_agent') must not create any "
        "epistemic belief about this action_type -- it is a capability-"
        "resolution gap, not evidence the action itself misbehaves"
    )


def test_rr3_2_genuine_error_still_degrades_epistemic_confidence(tmp_path):
    """Control: the shape-differentiation fix must NOT break the existing,
    already-proven mechanism for a genuine capability error/failure. A
    real status="error" outcome must still create and degrade the belief,
    landing in the [0.3, 0.5) confidence bucket after enough repetitions
    (matching the already-integrated 0.42-reward convergence)."""
    action_type = f"test_rr3_real_error_{uuid.uuid4().hex[:8]}"
    loop, engine = _make_isolated_loop(tmp_path, governor_result={"status": "error"})

    asyncio.run(_run_n_times(loop, action_type, 8))

    belief = engine._epistemic.get_belief(f"action_domain:{action_type}")
    assert belief is not None, "a genuine error outcome must still create an epistemic belief"
    conf = belief.get("current_confidence", belief.get("confidence"))
    assert conf is not None and conf < 0.5, (
        f"repeated genuine errors must converge confidence below 0.5 (medium/low bucket), got {conf}"
    )


def test_rr3_2_repeated_exception_connects_to_epistemic_and_changes_future_score(tmp_path):
    """Mandatory decision-influence proof (mission Section 14, Test C): a
    REAL uncaught exception from governor.dispatch(), repeated for the same
    action_type, must now reach PolicyMemory + EpistemicTracker (previously
    it reached ONLY RetryQueue -- pure infrastructure, zero learning
    effect). Proven by directly reading the resulting epistemic penalty
    factor via DecisionEngine._epistemic_penalty() -- NOT via evaluate()'s
    winner selection, so R6 (which only ever swaps a repeatedly-WINNING
    candidate) cannot be the cause of any change observed here: this test
    never lets the same candidate win more than once in one evaluate() call,
    it calls the penalty function directly on a single fresh candidate."""
    from core.loop.decision_engine import Candidate

    action_type = f"test_rr3_exception_{uuid.uuid4().hex[:8]}"
    loop, engine = _make_isolated_loop(tmp_path, governor_raises=RuntimeError("simulated real crash"))

    # Before: an untouched action_type is neutral (factor=1.0, no belief).
    fresh_before = Candidate(action_type=action_type, params={}, goal_ids=[])
    factor_before, _ = engine._epistemic_penalty(fresh_before)
    assert factor_before == 1.0, "an action_type with no history must be neutral, not pre-penalized"

    # Repeated REAL exceptions for the same action_type (never the same
    # Candidate object twice, never scored against alternatives -- R6 has
    # no opportunity to act here at all).
    asyncio.run(_run_n_times(loop, action_type, 6))

    fresh_after = Candidate(action_type=action_type, params={}, goal_ids=[])
    factor_after, conf_after = engine._epistemic_penalty(fresh_after)

    assert factor_after < 1.0, (
        f"repeated real exceptions for '{action_type}' must degrade its epistemic "
        f"penalty factor below neutral (1.0) -- got {factor_after}. Before this fix, "
        f"exceptions reached only RetryQueue and produced zero decision-relevant "
        f"evidence, so this factor would have stayed 1.0 forever."
    )
    assert conf_after < 0.5, f"confidence should have converged toward the 0.42 exception-reward, got {conf_after}"

    # Also confirm PolicyMemory (the other decision-relevant store) recorded
    # the same exception-derived reward under the canonical identity.
    pm_score = engine._get_policy().get_score(action_type, engine._get_policy().make_situation_hash(action_type, {}))
    assert pm_score < 0.5, f"PolicyMemory must also reflect the degraded exception-derived reward, got {pm_score}"


def test_rr3_2_epistemic_penalty_survives_restart(tmp_path):
    """Mission Section 14, Test H: failure-learning persistence must survive
    a process restart, not just live in an in-memory cache. Writes a belief
    via one EpistemicTracker instance backed by an on-disk DB, then opens a
    SECOND, independent instance against the SAME db_path (simulating a
    fresh process start) and confirms the degraded penalty is still read
    back correctly."""
    from core.brain.epistemic_tracker import EpistemicTracker
    from core.loop.decision_engine import DecisionEngine, Candidate

    db_path = tmp_path / "epistemic_restart.db"
    action_type = f"test_rr3_restart_{uuid.uuid4().hex[:8]}"

    tracker_1 = EpistemicTracker(db_path=db_path)
    tracker_1.merge_belief(f"action_domain:{action_type}", "last_outcome=error", 0.42, "test_setup")
    tracker_1.merge_belief(f"action_domain:{action_type}", "last_outcome=error", 0.42, "test_setup")

    # Fresh instance, fresh DecisionEngine -- nothing carried over except the file on disk.
    tracker_2 = EpistemicTracker(db_path=db_path)
    engine_2 = DecisionEngine()
    engine_2._epistemic = tracker_2

    candidate = Candidate(action_type=action_type, params={}, goal_ids=[])
    factor, conf = engine_2._epistemic_penalty(candidate)

    assert factor < 1.0, "the degraded penalty must survive being read by a fresh EpistemicTracker instance/process"
    assert conf < 0.5, f"persisted confidence must still reflect the degraded value after restart, got {conf}"


# ============================================================
# RR-3.3 -- plan-step soft-safety parity
# ============================================================

def test_rr3_3_plan_step_gets_same_counterfactual_veto_as_native_action(monkeypatch):
    """A plan-step candidate whose action_type CounterfactualMemory would
    veto for a native candidate must now ALSO be vetoed. Before the fix,
    _act_on()'s plan branch returned before ever reaching this check, so a
    plan step could execute something native action execution would
    soft-veto."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import Candidate
    from core.memory.counterfactual import CounterfactualMemory

    action_type = f"test_rr3_plan_cf_veto_{uuid.uuid4().hex[:8]}"

    def _fake_should_avoid(self, proposal, threshold=0.4):
        if action_type in proposal:
            return True, 0.95, "matches a past rejection (test)"
        return False, 0.0, ""

    monkeypatch.setattr(CounterfactualMemory, "should_avoid", _fake_should_avoid)

    loop = AutonomousLoop()
    _plan_step_called = {"count": 0}

    async def _fake_act_on_plan_step(winner):
        _plan_step_called["count"] += 1

    monkeypatch.setattr(loop, "_act_on_plan_step", _fake_act_on_plan_step)

    plan_candidate = Candidate(
        action_type=action_type, params={}, goal_ids=[],
        source="plan:test_plan_1:step-1",
    )
    asyncio.run(loop._act_on(plan_candidate))

    assert _plan_step_called["count"] == 0, (
        "a plan step whose action_type CounterfactualMemory vetoes must never "
        "reach _act_on_plan_step() -- before the fix, the plan branch returned "
        "before this check ran at all"
    )


def test_rr3_3_plan_step_gets_same_threat_detector_veto_as_native_action(monkeypatch):
    """Same parity proof for ThreatDetector: a plan step whose description
    is flagged must not execute, matching native-path behavior."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import Candidate

    action_type = f"test_rr3_plan_threat_{uuid.uuid4().hex[:8]}"
    loop = AutonomousLoop()

    monkeypatch.setattr(loop, "_scan_threats", lambda desc, context="act": action_type in desc)

    _plan_step_called = {"count": 0}

    async def _fake_act_on_plan_step(winner):
        _plan_step_called["count"] += 1

    monkeypatch.setattr(loop, "_act_on_plan_step", _fake_act_on_plan_step)

    plan_candidate = Candidate(
        action_type=action_type, params={}, goal_ids=[],
        source="plan:test_plan_3:step-1",
    )
    asyncio.run(loop._act_on(plan_candidate))

    assert _plan_step_called["count"] == 0, "a plan step flagged by ThreatDetector must not execute"


def test_rr3_3_plan_step_without_veto_still_executes(monkeypatch):
    """Control: a plan step none of the three soft checks veto must still
    reach _act_on_plan_step() normally -- proves the new shared pre-check
    doesn't accidentally block legitimate plan steps (GREEN control)."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import Candidate

    action_type = f"test_rr3_plan_clean_{uuid.uuid4().hex[:8]}"
    loop = AutonomousLoop()

    _plan_step_called = {"count": 0}

    async def _fake_act_on_plan_step(winner):
        _plan_step_called["count"] += 1

    monkeypatch.setattr(loop, "_act_on_plan_step", _fake_act_on_plan_step)

    plan_candidate = Candidate(
        action_type=action_type, params={}, goal_ids=[],
        source="plan:test_plan_2:step-1",
    )
    asyncio.run(loop._act_on(plan_candidate))

    assert _plan_step_called["count"] == 1, "a plan step with no veto reason must still execute normally"


def test_rr3_3_native_path_counterfactual_veto_unchanged(monkeypatch):
    """Regression control: extracting the soft-safety checks into a shared
    helper must not change NATIVE path behavior -- a native (non-plan)
    candidate CounterfactualMemory vetoes must still be blocked before
    governor.dispatch(), exactly as before this refactor."""
    from core.loop.autonomous_loop import AutonomousLoop
    from core.loop.decision_engine import Candidate
    from core.memory.counterfactual import CounterfactualMemory

    action_type = f"test_rr3_native_cf_veto_{uuid.uuid4().hex[:8]}"

    def _fake_should_avoid(self, proposal, threshold=0.4):
        if action_type in proposal:
            return True, 0.95, "matches a past rejection (test)"
        return False, 0.0, ""

    monkeypatch.setattr(CounterfactualMemory, "should_avoid", _fake_should_avoid)

    loop = AutonomousLoop()
    _dispatch_calls = {"count": 0}

    class _FakeGovernor:
        async def dispatch(self, task):
            _dispatch_calls["count"] += 1
            return {"status": "ok"}

    monkeypatch.setattr(loop, "_get_governor", lambda: _FakeGovernor())

    candidate = Candidate(action_type=action_type, params={}, goal_ids=[])
    asyncio.run(loop._act_on(candidate))

    assert _dispatch_calls["count"] == 0, "native path CounterfactualMemory veto behavior must be unchanged by the refactor"
