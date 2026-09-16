"""
RR-3.7B.1 (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
RR3_7B1_AMBIGUITY_AUTOPILOT_CLOSURE_REPORT.md): closes the
POST /governance/autopilot/trigger unbounded-recursion defect RR-3.7B
flagged but did not fix.

Independent root-cause (corrects RR-3.7B's own characterization): RR-3.7B
described this as "reachable whenever Autopilot happens to be the
highest-HP agent in the governance district" (HP-lottery-dependent). That
is FALSE — `config/agent_manifest.yaml` declares `autopilot.capabilities =
["autopilot_trigger", "autonomous_chaining"]`, an EXACT capability match,
so Governor.dispatch()'s `capable = [a for a in agents if task_type in
a.capabilities]` branch deterministically selects Autopilot every single
time for this action_type — never HP-lottery-dependent, 100% reproducible.

The real bug: `Autopilot.run()`'s "chain" branch calls
`self.run_chain(task)` with NO depth argument (always defaults to 0).
`run_chain()`'s FIRST action is `await gov.dispatch(initial_task)` on the
UNCHANGED task (still `type="autopilot_trigger"`) — which re-enters the
entire Governor.dispatch() pipeline, deterministically re-selects
Autopilot again, calls `Autopilot.run()` again, which calls
`run_chain(task)` again at depth 0 again. `chain_depth` is a plain Python
argument that does NOT survive the Governor.dispatch() round-trip, so
MAX_CHAIN_DEPTH's `if chain_depth >= self.MAX_CHAIN_DEPTH` guard never
sees the depth advance on this self-referential edge — completely
independent of the (correctly depth-tracked) legitimate
chain-to-next-district recursion (`run_chain(follow_on, chain_depth+1)`,
a plain Python call that DOES thread depth correctly).

Pre-fix, this self-terminates only via Python's own RecursionError
(caught by the nearest enclosing `except Exception` — either
`Autopilot.run()`'s or `Governor.dispatch()`'s own broad except — both
present, confirmed by direct source read), after real CPU/episodic-
memory/audit-log/rate-limiter work proportional to however many stack
frames Python allows before RecursionError fires (typically 100+ logical
hops) — a genuine resource-waste/DoS-shaped defect, not a literal
process hang, and not an authorization gap (PermissionGateway is never in
this path; no privileged action executes during the recursion).

Fix: `run_chain()` now stamps `"autopilot_depth": chain_depth + 1` onto
whatever task it dispatches via Governor (the only channel that survives
the dispatch round-trip); `Autopilot.run()`'s "chain" branch reads this
key back (defaulting to 0, with malformed/negative/bool values collapsing
to 0) and threads it into `run_chain(task, chain_depth=incoming_depth)`.
This closes the self-referential edge using the SAME existing
MAX_CHAIN_DEPTH invariant — no second recursion-control system.

Per this repo's testing rules: the real, unmodified Autopilot code is
used throughout. `Governor` is never instantiated (avoids pulling in the
entire real dispatch pipeline, agent registry, PermissionGateway, etc.) --
`Autopilot._get_governor()` lazily imports+instantiates Governor only
when `self._governor is None`, so tests inject a lightweight stand-in
object directly onto `agent._governor` before calling `agent.run()`,
bypassing that lazy import entirely while exercising the real, unmodified
`Autopilot.run()`/`run_chain()` control flow being tested. The stand-in's
`dispatch()` is a HARD-BOUNDED simulation of Governor.dispatch()'s real,
confirmed re-entrant behavior for "autopilot_trigger" (never allowing
genuinely unbounded recursion inside this test process, per the mission's
explicit "never intentionally run an uncontrolled recursion" instruction).
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

HARD_BOUND = 20  # test-only safety cap; real MAX_CHAIN_DEPTH is 5


def _run(coro):
    return asyncio.run(coro)


def _make_agent_with_self_redispatching_governor(depths_seen: list, hard_bound: int = HARD_BOUND):
    """Real, unmodified Autopilot instance, wired to a lightweight
    stand-in Governor whose dispatch() is a bounded simulation of the
    REAL, confirmed behavior: for task_type="autopilot_trigger", real
    Governor.dispatch() deterministically re-selects Autopilot (its own
    declared capability), which is equivalent to re-entering
    agent.run(task) directly. Records each dispatched task's
    "autopilot_depth" value. Hard-bounded at `hard_bound` real recursive
    re-entries so a genuine pre-fix bug can never actually run away inside
    this test process -- mirrors what Python's own RecursionError
    eventually does pre-fix, just capped far lower than the real
    ~hundreds of frames."""
    from districts.governance.autopilot import Autopilot
    agent = Autopilot()
    state = {"calls": 0}

    async def _dispatch(task):
        state["calls"] += 1
        depths_seen.append(task.get("autopilot_depth"))
        if state["calls"] > hard_bound:
            return {"status": "error", "error": "test hard-bound reached (simulated RecursionError)"}
        if task.get("type") == "autopilot_trigger":
            return await agent.run(task)
        return {"status": "ok"}

    agent._governor = SimpleNamespace(dispatch=_dispatch)
    return agent, state


def _make_agent_with_dispatch(dispatch_fn):
    """Real Autopilot with an arbitrary caller-supplied dispatch()."""
    from districts.governance.autopilot import Autopilot
    agent = Autopilot()
    agent._governor = SimpleNamespace(dispatch=dispatch_fn)
    return agent


# ============================================================
# Pre-fix exploit reproduction (mission Section 9/15)
# ============================================================

def test_rr3_7b1_exploit_self_redispatch_never_terminates_pre_fix():
    """Pre-fix: chain_depth never advances past 0 across the self-
    referential redispatch edge, so the real MAX_CHAIN_DEPTH=5 guard
    never fires within the hard bound -- the simulated dispatch is called
    HARD_BOUND+1 times (exhausting the test's own safety cap) rather than
    stopping at depth 5. This must FAIL against pre-fix HEAD (verified via
    git-stash) and PASS against the fixed code."""
    depths_seen: list = []
    agent, state = _make_agent_with_self_redispatching_governor(depths_seen)

    result = _run(agent.run({"type": "autopilot_trigger", "params": {"workflow": "", "params": ""}}))

    # Post-fix: real MAX_CHAIN_DEPTH governs this, so calls stop at 5 real
    # dispatches (the 6th run_chain() invocation short-circuits BEFORE
    # ever calling dispatch() again).
    assert state["calls"] == 5, (
        f"expected exactly 5 real Governor.dispatch() calls (bounded by "
        f"MAX_CHAIN_DEPTH=5), got {state['calls']} -- depth guard is not "
        f"terminating the self-referential chain"
    )
    assert depths_seen == [1, 2, 3, 4, 5], (
        f"expected monotonically increasing depth stamped on each "
        f"dispatched task, got {depths_seen}"
    )
    assert result["status"] == "ok"
    assert result.get("chain_stopped") == "max_depth_reached"
    assert result.get("depth") == 5


def test_rr3_7b1_depth_increases_monotonically():
    """Each real dispatch carries a strictly increasing autopilot_depth,
    never repeating."""
    depths_seen: list = []
    agent, state = _make_agent_with_self_redispatching_governor(depths_seen)

    _run(agent.run({"type": "autopilot_trigger", "params": {}}))

    assert depths_seen == sorted(depths_seen), "depth must never decrease or repeat"
    assert len(depths_seen) == len(set(depths_seen)), "depth must never repeat across dispatches"


def test_rr3_7b1_max_chain_depth_terminates_chain():
    """Direct test of run_chain() itself at the boundary depth."""
    mock_dispatch = AsyncMock()
    agent = _make_agent_with_dispatch(mock_dispatch)

    result = _run(agent.run_chain({"type": "autopilot_trigger"}, chain_depth=5))

    mock_dispatch.assert_not_called()
    assert result == {"status": "ok", "chain_stopped": "max_depth_reached", "depth": 5}


def test_rr3_7b1_no_extra_dispatch_after_maximum_depth():
    """At exactly the boundary, zero further Governor.dispatch() calls
    occur -- not even one more."""
    depths_seen: list = []
    agent, state = _make_agent_with_self_redispatching_governor(depths_seen)

    _run(agent.run({"type": "autopilot_trigger", "params": {}}))

    assert state["calls"] == 5


# ============================================================
# Normal behavior unaffected (mission Section 13, #5, #10)
# ============================================================

def test_rr3_7b1_normal_shallow_chain_still_works():
    """A legitimate, real cross-district chain (research -> stop, per
    classify_next_step's own rules) still completes correctly and is
    unaffected by the depth-stamping change."""
    async def _dispatch(task):
        return {"status": "ok", "response": "Pipeline is done, no further action needed."}

    agent = _make_agent_with_dispatch(_dispatch)
    result = _run(agent.run_chain({"type": "research", "params": {"query": "x"}}))

    assert result["chain_complete"] is True
    assert result["chain_depth"] == 0


def test_rr3_7b1_legitimate_multi_hop_chain_terminates_within_depth():
    """A real multi-district chain (code -> test -> stop) correctly
    advances chain_depth via the pre-existing, unmodified
    run_chain(follow_on, chain_depth+1) direct-call path, and still
    terminates well within MAX_CHAIN_DEPTH."""
    call_n = {"n": 0}

    async def _dispatch(task):
        call_n["n"] += 1
        if task.get("type") == "code":
            # Deliberately avoids rule-0 keywords ("implement","write
            # code","build","create function","python") so
            # classify_next_step() advances to the "test" rule instead of
            # looping back to "code" again.
            return {"status": "ok", "response": "please verify this with tests"}
        return {"status": "ok", "response": "all tests pass, task complete"}

    agent = _make_agent_with_dispatch(_dispatch)
    result = _run(agent.run_chain({"type": "code", "params": {}}))

    assert call_n["n"] == 2
    assert result["chain_complete"] is True
    assert result["chain_depth"] == 1


def test_rr3_7b1_existing_governance_autopilot_smoke_still_works():
    """The module's own real, unmocked __main__ smoke-test logic
    (classify_next_step) is unaffected by this fix."""
    from districts.governance.autopilot import Autopilot
    agent = Autopilot()
    next_step = agent.classify_next_step("You should implement this in Python using FastAPI")
    assert next_step is not None
    assert next_step["district"] == "coding"


# ============================================================
# Malformed / adversarial depth input (mission Section 13, #6-9)
# ============================================================

@pytest.mark.parametrize("bad_depth", [None, "5", 5.5, [], {}, object()])
def test_rr3_7b1_malformed_depth_fails_safely_to_zero(bad_depth):
    """A non-int autopilot_depth (whatever the source) must collapse to 0,
    never crash, never bypass the guard in the dangerous direction."""
    depths_seen: list = []
    agent, state = _make_agent_with_self_redispatching_governor(depths_seen)

    task = {"type": "autopilot_trigger", "params": {}, "autopilot_depth": bad_depth}
    result = _run(agent.run(task))

    # Treated as depth 0 -> full 5-hop chain still runs and terminates.
    assert state["calls"] == 5
    assert result.get("depth") == 5


def test_rr3_7b1_negative_depth_cannot_bypass_guard():
    """A negative autopilot_depth must not let the chain recurse for
    longer than MAX_CHAIN_DEPTH by exploiting `depth >= MAX` never
    becoming true -- collapses to 0."""
    depths_seen: list = []
    agent, state = _make_agent_with_self_redispatching_governor(depths_seen)

    task = {"type": "autopilot_trigger", "params": {}, "autopilot_depth": -1000}
    _run(agent.run(task))

    assert state["calls"] == 5, "a negative depth must not let the chain run longer than MAX_CHAIN_DEPTH"


def test_rr3_7b1_huge_depth_terminates_immediately():
    """A huge (but valid-int) autopilot_depth must terminate the chain
    immediately (fail toward safety, not toward a crash)."""
    mock_dispatch = AsyncMock()
    agent = _make_agent_with_dispatch(mock_dispatch)

    result = _run(agent.run({"type": "autopilot_trigger", "params": {}, "autopilot_depth": 10**9}))

    mock_dispatch.assert_not_called()
    assert result["chain_stopped"] == "max_depth_reached"


def test_rr3_7b1_bool_depth_does_not_bypass_isinstance_int_check():
    """bool is an int subclass in Python -- True/False must not sneak
    past the isinstance(x, int) check as if they were valid depths."""
    depths_seen: list = []
    agent, state = _make_agent_with_self_redispatching_governor(depths_seen)

    task = {"type": "autopilot_trigger", "params": {}, "autopilot_depth": True}
    _run(agent.run(task))

    assert state["calls"] == 5


# ============================================================
# Caller cannot control depth through the real HTTP schema
# (mission Section 13, #7; adversarial claim #12)
# ============================================================

def test_rr3_7b1_caller_cannot_inject_autopilot_depth_via_real_request_schema():
    """AutopilotTriggerReq has no autopilot_depth field and no
    extra='allow' config -- Pydantic v2's default extra='ignore' silently
    drops any such field a caller adds to the JSON body, so the dispatched
    task can never carry a caller-supplied autopilot_depth via this
    endpoint's own schema."""
    from core.api.routers.governance_extended import AutopilotTriggerReq
    body = AutopilotTriggerReq.model_validate({
        "workflow": "test", "params": "x", "autopilot_depth": 999999,
    })
    dumped = body.model_dump()
    assert "autopilot_depth" not in dumped
    assert set(dumped.keys()) == {"workflow", "params"}


def test_rr3_7b1_city_dispatch_cannot_smuggle_autopilot_trigger_type():
    """/city/dispatch's own hardcoded action_type is always
    "direct_dispatch" -- the caller's task_type/params string fields are
    nested INSIDE params, never promoted to the real dispatched task
    "type" -- so this endpoint cannot be used to construct a task with
    type="autopilot_trigger" plus an arbitrary top-level autopilot_depth."""
    import inspect
    from core.api.routers import city as city_module
    src = inspect.getsource(city_module.direct_dispatch)
    assert '"type": "direct_dispatch"' in src or "'type': 'direct_dispatch'" in src


# ============================================================
# Authorization / side-effect analysis (mission Section 11)
# ============================================================

def test_rr3_7b1_autopilot_trigger_never_reaches_permission_gateway():
    """Confirms the recursion is purely a Governor/Autopilot control-flow
    defect, unrelated to any PermissionGateway tier -- "autopilot_trigger"
    is not in _PLAN_COMPOSABLE_ACTION_TYPES and is not hand_-prefixed, so
    /command and /ws/command's PermissionGateway pipelines report
    not_implemented for it and never reach Governor.dispatch() at all."""
    from core.loop.permission_gateway import _PLAN_COMPOSABLE_ACTION_TYPES
    assert "autopilot_trigger" not in _PLAN_COMPOSABLE_ACTION_TYPES


def test_rr3_7b1_autopilot_capability_is_exact_not_hp_lottery():
    """Corrects RR-3.7B's own diagnosis: Autopilot's selection for
    "autopilot_trigger" is deterministic (exact capability match), not
    HP-lottery-dependent. Checked against config/agent_manifest.yaml --
    the real, authoritative bootstrap-time capabilities source (confirmed
    by RR-3.7B: ManifestLoader.register_all() OVERWRITES a freshly-
    constructed agent's in-code __init__ capabilities at real startup) --
    NOT a raw `Autopilot()` instantiation, which only ever has the
    unrelated in-code default set (["ambient","autopilot","classify",
    "directive","governance"]) and was never the state RR-3.7B's own
    finding, or this fix's threat model, is about."""
    import yaml
    raw = yaml.safe_load(open("config/agent_manifest.yaml", encoding="utf-8").read())
    autopilot_entry = next(a for a in raw["districts"]["governance"] if a["name"] == "autopilot")
    assert "autopilot_trigger" in autopilot_entry["capabilities"]


# ============================================================
# RR-3.7B repairs remain intact (mission Section 3 freeze)
# ============================================================

def test_rr3_7b1_rr3_7b_composable_allowlist_unchanged():
    from core.loop.permission_gateway import _PLAN_COMPOSABLE_ACTION_TYPES
    assert {"script", "schedule_post", "idea_validate", "log_exercise", "create_project"} <= _PLAN_COMPOSABLE_ACTION_TYPES


def test_rr3_7b1_log_exercise_still_routes_to_health():
    from core.city.governor import Governor
    assert Governor().route_task("log_exercise") == "health"


def test_rr3_7b1_create_project_still_routes_to_projects():
    from core.city.governor import Governor
    assert Governor().route_task("create_project") == "projects"


def test_rr3_7b1_exercise_logger_still_declares_capability():
    from districts.health.exercise_logger import ExerciseLogger
    assert "log_exercise" in ExerciseLogger().capabilities


def test_rr3_7b1_project_planner_still_declares_capability():
    from districts.projects.project_planner import ProjectPlanner
    assert "create_project" in ProjectPlanner().capabilities


def test_rr3_7b1_ingest_video_still_fails_closed():
    from core.loop.permission_gateway import PermissionGateway
    assert PermissionGateway()._classify("ingest_video") == "UNKNOWN"


if __name__ == "__main__":
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"], cwd=str(Path(__file__).parent.parent))
    print("OK test_rr3_7b1_autopilot_recursion.py" if result.returncode == 0 else "FAILED")
