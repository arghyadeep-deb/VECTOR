"""
Task 58B — Behavioral tests for the FinAgent launch_terminal permission-bypass
remediation (VECTOR_TECHNICAL_KNOWLEDGE/58B_FINAGENT_TERMINAL_PERMISSION_
REMEDIATION.md).

Original finding (Task 57, Finding B): FinAgentAgent.launch_terminal() called
FinAgentTerminalLauncher.ensure_built(auto_build=...) and .launch() directly,
with NO PermissionGateway step at all — reachable via Governor.dispatch()
(exact task_type="launch_terminal" AND LLM-classified cross-district routing)
and via the "terminal"/"open_terminal" aliases inside run(). auto_build was
forwarded unfiltered from caller params straight into a real cmake/build
subprocess.run(), and the compiled binary was launched via real
subprocess.Popen() — both completely unguarded.

Fix: FinAgentAgent.launch_terminal() now gates through
PermissionGateway.execute(Action(action_type="launch_terminal",
params={"auto_build": auto_build}, proposed_by=self.name)) BEFORE calling
self._launcher.ensure_built()/.launch(), and refuses (fail-closed) unless
gate_result.approved is True. "launch_terminal" is now classified RED in
core/config.py. Every entry point (direct call, run()'s dispatch table
including the "terminal"/"open_terminal" aliases, and Governor.dispatch()'s
exact + LLM-classified capability routing) funnels through this single
gated method — there is exactly one implementation of launch_terminal(),
so there is nowhere else for the real side effect to occur.

TEST ISOLATION (per the Task 58A incident — a stale method-level mock let a
real Spotify launch slip through after play_music()'s internal call target
changed): every OS-level primitive FinAgentTerminalLauncher.ensure_built()/
.launch() can actually reach was inventoried fresh from the current source
(districts/investment/vector_finagent/terminal_launcher.py) before writing
these tests. It uses exactly two: subprocess.run (build()'s cmake configure
+ build steps) and subprocess.Popen (launch()). No os.system, os.startfile,
shutil.which, or shell=True anywhere in that file. Both are mocked directly
on the terminal_launcher module's `subprocess` reference (the actual
OS-level primitive), not via a named wrapper method, so an internal
refactor can't silently stop the mock from intercepting anything the way it
did in Task 58A. Every dangerous-path test below was also run individually
in isolation with a `tasklist` check immediately after (see the Task 58B
documentation's Test Isolation section for the transcript) — zero real
FinceptTerminal.exe / cmake.exe processes were created.

No mocking of permission_gateway.py's own gating logic (execute(), classify(),
_handle_red_tier()'s verdict-processing) or of Governor.dispatch()'s routing
logic — per .claude/rules/testing.md ("No Mocking: permission_gateway.py —
test the real gate"). Only the external CouncilBrain LLM dependency and the
human Pushover notification/confirmation boundary are simulated, exactly
matching the established pattern in tests/integration/test_phase_a7_council_
red_tier.py and tests/unit/test_permission_gateway.py.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.agent_registry import get_registry
from core.city.governor import Governor
from districts.investment.finagent_agent import FinAgentAgent
from districts.investment.vector_finagent.terminal_launcher import FinAgentTerminalLauncher
import districts.investment.vector_finagent.terminal_launcher as tl_mod


# ── Shared helpers ────────────────────────────────────────────────────────

def _patch_council(monkeypatch, verdict_text: str, confidence: float = 0.9):
    """Stub CouncilBrain.deliberate() so _handle_red_tier() runs for real
    (real gateway logic, real verdict-processing) without a real Ollama
    call — same pattern as tests/integration/test_phase_a7_council_red_tier.py."""
    import core.brain.council as council_mod

    class _Patched(council_mod.CouncilBrain):
        async def deliberate(self, question, hp_gate=700):
            return {
                "stage1": ["vote1"], "stage2": ["vote1"],
                "verdict": verdict_text, "confidence": confidence,
                "timestamp": "2026-01-01T00:00:00",
            }

    cb = _Patched()
    monkeypatch.setattr(council_mod, "CouncilBrain", lambda: cb)


def _mock_terminal_primitives(monkeypatch, on_build_run=None):
    """Mock every OS-level primitive FinAgentTerminalLauncher can reach.
    Returns (run_calls, popen_calls) lists the test can assert against."""
    run_calls: list = []
    popen_calls: list = []

    def _fake_run(cmd, **kwargs):
        run_calls.append(cmd)
        if on_build_run:
            on_build_run(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    def _fake_popen(cmd, **kwargs):
        popen_calls.append(cmd)
        proc = MagicMock()
        proc.pid = 999999
        proc.poll.return_value = None
        return proc

    monkeypatch.setattr(tl_mod.subprocess, "run", _fake_run)
    monkeypatch.setattr(tl_mod.subprocess, "Popen", _fake_popen)
    return run_calls, popen_calls


def _new_agent(monkeypatch, *, wait_for_confirmation_result: bool):
    """A fresh FinAgentAgent with its gateway's human-notification boundary
    stubbed (never mocking the gateway's own gating logic)."""
    agent = FinAgentAgent()
    agent._gateway._notify = AsyncMock()
    agent._gateway._wait_for_confirmation = AsyncMock(return_value=wait_for_confirmation_result)
    return agent


def _spy_gateway_execute(agent):
    """Wrap the REAL PermissionGateway.execute so tests can assert it was
    actually invoked with the right action_type — not just infer it from a
    boolean result."""
    calls: list = []
    original = agent._gateway.execute

    async def _spy(action):
        calls.append(action.action_type)
        return await original(action)

    agent._gateway.execute = _spy
    return calls


# ── TEST 1 — unapproved launch_terminal does NOT execute ────────────────────

async def test_1_unapproved_launch_terminal_does_not_execute(monkeypatch):
    _patch_council(monkeypatch, "REJECT — no owner context, refuse")
    run_calls, popen_calls = _mock_terminal_primitives(monkeypatch)
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: False))

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=False)
    gw_calls = _spy_gateway_execute(agent)

    result = await agent.launch_terminal(auto_build=True)

    assert gw_calls == ["launch_terminal"], "PermissionGateway.execute must actually be invoked"
    assert result["status"] == "blocked"
    assert not run_calls, f"unapproved launch_terminal triggered a real build: {run_calls}"
    assert not popen_calls, f"unapproved launch_terminal triggered a real launch: {popen_calls}"


# ── TEST 2 — launch_terminal WITH valid authorization works ────────────────

async def test_2_approved_launch_terminal_works_launcher_reached_only_after_authorization(monkeypatch):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    run_calls, popen_calls = _mock_terminal_primitives(monkeypatch)
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: True))

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)

    call_order: list = []
    original_execute = agent._gateway.execute
    original_launch = agent._launcher.launch

    async def _spy_execute(action):
        call_order.append("gateway.execute")
        return await original_execute(action)

    def _spy_launch(*a, **kw):
        call_order.append("launcher.launch")
        return original_launch(*a, **kw)

    agent._gateway.execute = _spy_execute
    monkeypatch.setattr(agent._launcher, "launch", _spy_launch)

    result = await agent.launch_terminal(auto_build=False)

    assert result["status"] == "launched"
    assert call_order == ["gateway.execute", "launcher.launch"], (
        "launch() must only be reached AFTER the gateway approves — "
        f"got order: {call_order}"
    )
    assert popen_calls, "approved launch_terminal must reach the real (mocked) Popen launch"


# ── TEST 3 — auto_build=False reaches launch without triggering build ──────

async def test_3_auto_build_false_reaches_launch_without_triggering_build(monkeypatch):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    run_calls, popen_calls = _mock_terminal_primitives(monkeypatch)
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: True))

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)

    result = await agent.launch_terminal(auto_build=False)

    assert result["status"] == "launched"
    assert not run_calls, "auto_build=False must never trigger a real cmake/build subprocess.run"
    assert popen_calls, "authorized launch must still reach the real (mocked) Popen launch"


# ── TEST 4 — auto_build=True: single RED approval covers build AND launch ──

async def test_4_approved_auto_build_true_triggers_build_then_launch(monkeypatch):
    """Proves design question (E)/(F) explicitly: one RED launch_terminal
    approval — with auto_build=True visible in the approved Action's own
    params — intentionally authorizes BOTH the real (mocked) cmake build
    (binary missing) and the subsequent real (mocked) launch."""
    _patch_council(monkeypatch, "DEFER — ask the owner")

    state = {"built": False}
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: state["built"]))
    monkeypatch.setattr(FinAgentTerminalLauncher, "cmake_source_present", lambda self: True)

    def _on_build_run(cmd):
        if len(cmd) >= 2 and cmd[0] == "cmake" and cmd[1] == "--build":
            state["built"] = True

    run_calls, popen_calls = _mock_terminal_primitives(monkeypatch, on_build_run=_on_build_run)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)

    result = await agent.launch_terminal(auto_build=True)

    assert result["status"] == "launched"
    assert any(c[:2] == ["cmake", "--preset"] for c in run_calls), f"expected a cmake configure call: {run_calls}"
    assert any(c[:2] == ["cmake", "--build"] for c in run_calls), f"expected a cmake build call: {run_calls}"
    assert popen_calls, "after a successful build, launch must still occur"


async def test_4b_unapproved_auto_build_true_never_triggers_build(monkeypatch):
    """The auto_build=True flavor of TEST 1 — an unapproved request must
    never trigger the real build path even though the caller asked for it."""
    _patch_council(monkeypatch, "REJECT — refuse")
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: False))
    monkeypatch.setattr(FinAgentTerminalLauncher, "cmake_source_present", lambda self: True)
    run_calls, popen_calls = _mock_terminal_primitives(monkeypatch)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=False)

    result = await agent.launch_terminal(auto_build=True)

    assert result["status"] == "blocked"
    assert not run_calls
    assert not popen_calls


# ── TEST 5 — Governor.dispatch() capability routing cannot bypass the gate ─

@pytest.fixture
def clean_registry():
    reg = get_registry()
    before = list(reg._agents.keys())
    yield
    for aid in list(reg._agents.keys()):
        if aid not in before:
            reg._agents.pop(aid, None)


async def test_5a_governor_dispatch_unapproved_launch_terminal_blocked(monkeypatch, clean_registry):
    _patch_council(monkeypatch, "REJECT — refuse")
    run_calls, popen_calls = _mock_terminal_primitives(monkeypatch)
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: False))

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=False)
    agent.health_points = 999999  # win any HP tie-break unambiguously
    get_registry().register(agent)

    gov = Governor()
    result = await gov.dispatch({
        "type": "launch_terminal",
        "district": "investment",
        "params": {"auto_build": True},
    })

    assert not run_calls, f"Governor-routed unapproved launch_terminal triggered a real build: {run_calls}"
    assert not popen_calls, f"Governor-routed unapproved launch_terminal triggered a real launch: {popen_calls}"
    assert result.get("status") != "launched"


async def test_5b_governor_dispatch_approved_launch_terminal_reaches_launcher(monkeypatch, clean_registry):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    run_calls, popen_calls = _mock_terminal_primitives(monkeypatch)
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: True))

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)
    agent.health_points = 999999
    get_registry().register(agent)

    # 2026-09-23: Governor.dispatch() now enforces its own authorization
    # boundary for YELLOW/RED task types -- issue the real, gateway-owned
    # receipt PermissionGateway._execute_action() would issue right
    # before dispatching this exact, already-approved task_type in
    # production (see permission_gateway.py's own
    # _PLAN_COMPOSABLE_ACTION_TYPES branch).
    from core.loop.permission_gateway import PermissionGateway
    PermissionGateway()._issue_approval_receipt("launch_terminal", purpose="governor_dispatch")

    gov = Governor()
    result = await gov.dispatch({
        "type": "launch_terminal",
        "district": "investment",
        "params": {"auto_build": False},
    })

    assert popen_calls, f"Governor-routed approved launch_terminal must reach the real (mocked) launcher, got: {result}"


# ── TEST 6 — "terminal"/"open_terminal" aliases cannot bypass the boundary ─

async def test_6a_alias_terminal_unapproved_blocked(monkeypatch):
    _patch_council(monkeypatch, "REJECT — refuse")
    run_calls, popen_calls = _mock_terminal_primitives(monkeypatch)
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: False))

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=False)
    result = await agent.run({"type": "terminal", "params": {"auto_build": True}})

    assert result["status"] == "blocked"
    assert not run_calls
    assert not popen_calls


async def test_6b_alias_open_terminal_unapproved_blocked(monkeypatch):
    _patch_council(monkeypatch, "REJECT — refuse")
    run_calls, popen_calls = _mock_terminal_primitives(monkeypatch)
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: False))

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=False)
    result = await agent.run({"type": "open_terminal", "params": {}})

    assert result["status"] == "blocked"
    assert not run_calls
    assert not popen_calls


async def test_6c_alias_terminal_approved_reaches_launcher(monkeypatch):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    run_calls, popen_calls = _mock_terminal_primitives(monkeypatch)
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: True))

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)
    result = await agent.run({"type": "terminal", "params": {"auto_build": False}})

    assert result["status"] == "launched"
    assert popen_calls


# ── TEST 7 — no regression to existing safe FinAgent behavior ──────────────

async def test_7_terminal_status_still_works_read_only_no_gateway_involved():
    """terminal_status() is inert (no OS primitive) and intentionally stays
    ungated — must keep working exactly as before, with zero gateway calls."""
    agent = FinAgentAgent()
    gw_calls = _spy_gateway_execute(agent)

    result = agent.terminal_status()

    assert isinstance(result, dict)
    assert "binary_built" in result and "running" in result and "platform" in result
    assert gw_calls == [], "terminal_status() must not touch the gateway at all"


def test_7b_capabilities_unaffected_by_the_fix():
    agent = FinAgentAgent()
    assert "launch_terminal" in agent.capabilities
    assert "terminal_status" in agent.capabilities
    # Sanity: the fix must not have deleted or renamed any pre-existing
    # unrelated capability.
    for cap in ("investor_analysis", "alpha_discovery", "corporate_finance",
                "geopolitics_analysis", "quant_backtest"):
        assert cap in agent.capabilities


async def test_7c_run_dispatch_table_unaffected_for_unrelated_action(monkeypatch):
    """A completely unrelated, already-safe action (terminal_status via
    run()) must still work identically — the fix must not have broadly
    disabled FinAgentAgent.run()."""
    agent = FinAgentAgent()
    result = await agent.run({"type": "terminal_status", "params": {}})
    assert isinstance(result, dict)
    assert "binary_built" in result


# ── TEST 8 — no permission self-mint bypass ─────────────────────────────────

def test_8_launch_terminal_source_has_no_self_mint_and_gates_before_side_effect():
    import inspect

    src = inspect.getsource(FinAgentAgent.launch_terminal)

    assert "grant_control" not in src, (
        "launch_terminal() must not mint its own control/capability token — "
        "authorization must come only from PermissionGateway.execute()"
    )
    assert "self._gateway.execute" in src, "launch_terminal() must gate through the real PermissionGateway"

    gate_idx = src.index("self._gateway.execute")
    # "gate_result.approved" alone also appears in the docstring's prose
    # explanation above the real code — anchor on the actual conditional
    # statement so the docstring text can't produce a false match.
    approved_check_idx = src.index("if not gate_result.approved")
    ensure_built_idx = src.index("self._launcher.ensure_built")
    launch_idx = src.index("self._launcher.launch()")

    assert gate_idx < approved_check_idx < ensure_built_idx < launch_idx, (
        "the gateway call and its approval check must precede both "
        "ensure_built() and launch() in source order — the real side "
        "effect must be strictly downstream of the approved gateway path"
    )


def test_8b_launch_terminal_is_red_tier():
    from core.config import CONFIG
    assert "launch_terminal" in CONFIG["permission"]["red"], (
        "launch_terminal must be classified RED — it was previously "
        "UNKNOWN/unclassified, which blocked at the gateway layer but left "
        "it reachable unguarded via FinAgentAgent.run() directly"
    )


def test_8c_gateway_unreachable_fails_closed(monkeypatch):
    """If PermissionGateway.execute() itself raises (e.g. gateway
    unreachable), launch_terminal() must refuse — never fail open."""
    import asyncio

    agent = FinAgentAgent()

    async def _boom(action):
        raise RuntimeError("simulated gateway outage")

    agent._gateway.execute = _boom

    result = asyncio.run(agent.launch_terminal(auto_build=True))
    assert result["status"] == "blocked"


if __name__ == "__main__":
    ok = pytest.main([__file__, "-v"]) == 0
    print("PASS test_task58b_finagent_terminal_permission_remediation" if ok else "FAIL")
    sys.exit(0 if ok else 1)
