"""
DIAGNOSTIC tests for VECTOR_TECHNICAL_KNOWLEDGE/57_RESIDUAL_SIDE_EFFECT_SURFACE_
VERIFICATION.md — Findings B and C (ungated consequential capabilities
declared by district agents, reachable via Governor.dispatch()'s
capability-match with zero PermissionGateway involvement).

**Findings B and C have since both been remediated** — see VECTOR_TECHNICAL_
KNOWLEDGE/58B_FINAGENT_TERMINAL_PERMISSION_REMEDIATION.md and 58C_MLOPS_
HF_TRAIN_PERMISSION_REMEDIATION.md. This file's Finding-B and Finding-C
tests were both updated in place (per the guidance their own original
assertions carried: "if this assertion fails, re-verify Finding B/C before
assuming it is fixed" — they were, deliberately, in Tasks 58B/58C) to
assert the FIXED behavior instead of the vulnerable one, so this file
continues to serve as a regression guard rather than going permanently red.

Original Finding B (kept for history): districts/investment/
finagent_agent.py declares "launch_terminal" as a capability. run()'s
dispatch table routed task_type in ("launch_terminal", "terminal",
"open_terminal") to launch_terminal(auto_build=...), which called a real
subprocess.Popen-launching helper (FinAgentTerminalLauncher.launch(), and
optionally a real `cmake`/build invocation via ensure_built(auto_build=True))
with NO PermissionGateway step anywhere in the chain — reachable via
Governor.dispatch()'s capability-match with zero gating. The fix:
FinAgentAgent.launch_terminal() now gates through
PermissionGateway.execute(Action(action_type="launch_terminal", ...))
BEFORE calling ensure_built()/launch(), refusing (fail-closed) unless
approved; "launch_terminal" is now classified RED in core/config.py.

Finding C: districts/coding/mlops_agent.py declares "hf_train" as a
capability. run()'s dispatch table routes task_type=="hf_train" to
hf_train(script=...), which submits a caller-supplied Python script string
to a REMOTE HuggingFace Jobs service for execution (real cost, real
remote-code-execution using the owner's HF credentials) — again with no
PermissionGateway involvement anywhere in the chain. STILL OPEN.

These tests prove reachability (and, for Finding B, the presence of a real
gate) by calling the REAL run() methods with the real dispatch tables,
while replacing only the actual external-effect-performing primitives with
spies that record what would have been done. No real GUI application is
launched, no real build is triggered, and no real network call to
HuggingFace is made by this file.

CAUTION FOR FUTURE EDITS (per the Task 58A incident, where a stale
method-level mock silently stopped intercepting anything after an internal
architecture change and a real Spotify launch slipped through): Finding B's
behavioral test mocks the terminal launcher's OS-level primitives directly
(subprocess.run/subprocess.Popen on the terminal_launcher module), not a
named wrapper method, so a future internal refactor of
FinAgentTerminalLauncher can't silently lose coverage the same way.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_finagent_declares_launch_terminal_capability():
    """Confirms Governor.dispatch()'s capability-match would route
    task_type="launch_terminal" straight to this agent (no HP-lottery
    fallback needed) — read from the real, current capabilities list."""
    from districts.investment.finagent_agent import FinAgentAgent

    agent = FinAgentAgent()
    assert "launch_terminal" in agent.capabilities


def test_launch_terminal_action_type_is_now_classified_red():
    """UPDATED for Task 58B: launch_terminal must now be classified RED —
    read from the real, current permission configuration. Before Task 58B
    this asserted the opposite (that it was classified in NO tier at all,
    proving the bypass); that assertion is now inverted because the finding
    is fixed."""
    from core.config import CONFIG

    assert "launch_terminal" in CONFIG["permission"]["red"], (
        "'launch_terminal' is no longer classified RED — Task 58B's fix "
        "(58B_FINAGENT_TERMINAL_PERMISSION_REMEDIATION.md) has regressed"
    )
    for tier in ("green", "yellow"):
        assert "launch_terminal" not in CONFIG["permission"][tier], (
            f"'launch_terminal' must not ALSO be classified {tier.upper()}"
        )


async def test_run_launch_terminal_no_longer_reaches_real_launcher_without_approval(monkeypatch):
    """UPDATED for Task 58B: drive the REAL FinAgentAgent.run() with
    task_type="launch_terminal" (exactly as Governor.dispatch() would after
    a capability match) through an UNAPPROVED PermissionGateway RED path
    and confirm the terminal-launch helper is NEVER reached — the only
    OS-level primitives are mocked (subprocess.run/subprocess.Popen on the
    terminal_launcher module itself, not a named method), so this survives
    future internal refactors of exactly the kind that made the pre-58B
    version of this test start relying on an unguarded call chain."""
    import core.brain.council as council_mod
    from unittest.mock import AsyncMock
    from districts.investment.finagent_agent import FinAgentAgent
    from districts.investment.vector_finagent.terminal_launcher import FinAgentTerminalLauncher
    import districts.investment.vector_finagent.terminal_launcher as tl_mod

    class _RejectingCouncil(council_mod.CouncilBrain):
        async def deliberate(self, question, hp_gate=700):
            return {"stage1": [], "stage2": [], "verdict": "REJECT — refuse",
                     "confidence": 0.9, "timestamp": "2026-01-01T00:00:00"}

    monkeypatch.setattr(council_mod, "CouncilBrain", lambda: _RejectingCouncil())
    monkeypatch.setattr(FinAgentTerminalLauncher, "is_built", property(lambda self: False))

    run_calls: list = []
    popen_calls: list = []
    monkeypatch.setattr(tl_mod.subprocess, "run", lambda cmd, **kw: run_calls.append(cmd))
    monkeypatch.setattr(tl_mod.subprocess, "Popen", lambda cmd, **kw: popen_calls.append(cmd))

    agent = FinAgentAgent()
    agent._gateway._notify = AsyncMock()
    agent._gateway._wait_for_confirmation = AsyncMock(return_value=False)

    result = await agent.run({"type": "launch_terminal", "params": {"auto_build": True}})

    # The caller-supplied auto_build=True flag must NOT reach the real
    # build/launch primitives without gateway approval.
    assert not run_calls, f"unapproved launch_terminal triggered a real build: {run_calls}"
    assert not popen_calls, f"unapproved launch_terminal triggered a real launch: {popen_calls}"
    assert result.get("status") == "blocked"


def test_mlops_declares_hf_train_capability():
    """Confirms Governor.dispatch()'s capability-match would route
    task_type="hf_train" straight to this agent."""
    from districts.coding.mlops_agent import MLOpsAgent

    agent = MLOpsAgent()
    assert "hf_train" in agent.capabilities


def test_hf_train_action_type_is_now_classified_red():
    """UPDATED for Task 58C: hf_train must now be classified RED — read
    from the real, current permission configuration. Before Task 58C this
    asserted the opposite (that it was classified in NO tier at all,
    proving the bypass); that assertion is now inverted because the finding
    is fixed."""
    from core.config import CONFIG

    assert "hf_train" in CONFIG["permission"]["red"], (
        "'hf_train' is no longer classified RED — Task 58C's fix "
        "(58C_MLOPS_HF_TRAIN_PERMISSION_REMEDIATION.md) has regressed"
    )
    for tier in ("green", "yellow"):
        assert "hf_train" not in CONFIG["permission"][tier], (
            f"'hf_train' must not ALSO be classified {tier.upper()}"
        )


async def test_hf_train_no_longer_reaches_real_submission_without_approval(monkeypatch):
    """UPDATED for Task 58C: drive the REAL MLOpsAgent.run() with
    task_type="hf_train" through an UNAPPROVED PermissionGateway RED path
    and confirm the real HF Jobs submission boundary (hf_jobs_handler) is
    NEVER reached. hf_train()'s _run() closure dynamically re-imports
    `agent.tools.jobs_tool` fresh on every call via `_vector_mlops_agent_
    namespace()` — the ORIGINAL version of this test noted that
    monkeypatching that import target directly "proved unreliable across
    repeated runs (a fresh module object each call)" and fell back to
    source-inspection only. Task 58C found a robust alternative: replace
    the single, stable `_vector_mlops_agent_namespace` object itself (not
    re-created per call) with a no-op, and pre-seed sys.modules['agent'*]
    with a fake module whose hf_jobs_handler is a spy — verified reliable,
    now used here for a real behavioral proof instead of source inspection."""
    import types
    import contextlib
    import sys as _sys
    from unittest.mock import AsyncMock
    import core.brain.council as council_mod
    from districts.coding.mlops_agent import MLOpsAgent
    import districts.coding.mlops_agent as mlops_mod

    class _RejectingCouncil(council_mod.CouncilBrain):
        async def deliberate(self, question, hp_gate=700):
            return {"stage1": [], "stage2": [], "verdict": "REJECT — refuse",
                     "confidence": 0.9, "timestamp": "2026-01-01T00:00:00"}

    monkeypatch.setattr(council_mod, "CouncilBrain", lambda: _RejectingCouncil())

    calls: list = []

    async def _fake_handler(arguments, session=None, tool_call_id=None):
        calls.append(arguments)
        return ("mocked-ok: no real HF job was created", True)

    fake_jobs_tool = types.ModuleType("agent.tools.jobs_tool")
    fake_jobs_tool.hf_jobs_handler = _fake_handler
    fake_agent_tools = types.ModuleType("agent.tools")
    fake_agent_tools.jobs_tool = fake_jobs_tool
    fake_agent = types.ModuleType("agent")
    fake_agent.tools = fake_agent_tools
    monkeypatch.setitem(_sys.modules, "agent", fake_agent)
    monkeypatch.setitem(_sys.modules, "agent.tools", fake_agent_tools)
    monkeypatch.setitem(_sys.modules, "agent.tools.jobs_tool", fake_jobs_tool)

    @contextlib.contextmanager
    def _noop_namespace():
        yield

    monkeypatch.setattr(mlops_mod, "_vector_mlops_agent_namespace", _noop_namespace)

    agent = MLOpsAgent()
    agent._gateway._notify = AsyncMock()
    agent._gateway._wait_for_confirmation = AsyncMock(return_value=False)

    malicious_script = "import os; os.system('would be attacker-controlled')"
    result = await agent.run({"params": {
        "action": "hf_train", "script": malicious_script,
        "repo_id": "owner/repo", "hardware": "a100-large",
    }})

    # The caller-supplied script must NOT reach the real HF Jobs submission
    # boundary without gateway approval.
    assert not calls, f"unapproved hf_train reached the real (mocked) HF Jobs submission: {calls}"
    assert result.get("status") == "blocked"
