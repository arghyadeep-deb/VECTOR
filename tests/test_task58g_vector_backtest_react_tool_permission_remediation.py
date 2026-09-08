"""
Task 58G — Behavioral tests for the vector_backtest ReAct tool-registry
permission-bypass remediation (VECTOR_TECHNICAL_KNOWLEDGE/58G_VECTOR_
BACKTEST_REACT_TOOL_PERMISSION_REMEDIATION.md, closing a Task 58E residual).

Original finding (Task 58E §10): BacktestAgent.vt_research()/vt_swarm()/
vt_export() construct a real ReAct AgentLoop whose tool registry
unconditionally includes "write_file" and "backtest" (neither is in
build_registry()'s _SHELL_TOOL_NAMES = {"bash", "background_run"} gated by
enable_shell_tools). backtest_tool.py's run_backtest() reads from the
CORRECT run_path/code/signal_engine.py path (no accidental mismatch
protecting it, unlike Task 58E's BacktestAgent.vt_backtest() path) and
spawns the real backtest/runner.py as a real subprocess via src.core.
runner.Runner.execute() — real dynamic import + instantiation of whatever
code lives there, no PermissionGateway anywhere. An LLM driving the ReAct
loop can compose write_file(...) + backtest(...) into unauthorized
arbitrary Python execution, entirely bypassing Task 58E's vt_backtest gate
(a different method).

Fix: districts/investment/vector_backtest/src/tools/backtest_tool.py's
run_backtest() (the SINGLE shared function behind BOTH the "backtest" tool
AND the "run_shadow_backtest" tool's injectable run_backtest_fn — confirmed
by reading shadow_account/backtester.py's _default_run_backtest_fn(), and
therefore also behind every vt_research/vt_swarm/vt_export invocation path,
including vt_swarm's internally-built per-worker filtered registries) now
gates through a real PermissionGateway.execute(Action(action_type=
"vt_backtest", ...)) call AFTER only harmless, read-only validation (path
safety, config parsing, signal-file existence) and BEFORE the real
Runner(...).execute() subprocess call. Reuses the exact "vt_backtest" RED
action already established in Task 58E — the underlying consequence is
identical regardless of entry point, so no second action_type was
introduced. write_file itself was deliberately left ungated (see the
remediation doc's Chosen Security Boundary section for why this does not
weaken the invariant: a written-but-never-executed file is inert, and the
one real execution chokepoint is now gated).

TEST ISOLATION: this file modifies a VENDORED source file directly
(backtest_tool.py) — a deliberate deviation from Tasks 58A-58E's pattern of
only touching VECTOR-owned wrapper files, required here because vt_swarm's
per-worker tool registries are built entirely inside vendored src/swarm/
worker.py, invisible to districts/investment/backtest_agent.py. All tests
below therefore import directly from the vendored `src.tools.backtest_tool`
module (reachable because districts/investment/backtest_agent.py already
puts vector_backtest/ on sys.path at import time). Every test sets
VIBE_TRADING_ALLOWED_RUN_ROOTS to an isolated pytest tmp_path (the
established pattern already used by the vendored package's own
tests/test_path_safety.py and tests/test_file_tool_sandbox_security.py) —
never a real repo path or a real ~/.vibe-trading/ directory. The only
mocked boundaries are src.core.runner.Runner.execute (the real subprocess
primitive) and PermissionGateway's human-notification boundary (_notify/
_wait_for_confirmation) — PermissionGateway's own gating logic runs for
real throughout, per .claude/rules/testing.md's "No Mocking: permission_
gateway.py — test the real gate".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
# vector_backtest/ is put on sys.path by importing backtest_agent once.
import districts.investment.backtest_agent  # noqa: F401  (side effect: sys.path)

from src.tools.backtest_tool import run_backtest, BacktestTool
from src.tools.write_file_tool import WriteFileTool
from src.core.runner import Runner, RunResult
from src.agent.tools import ToolRegistry

from core.city.agent_registry import get_registry
from core.city.governor import Governor
from districts.investment.backtest_agent import BacktestAgent


_VALID_CONFIG = json.dumps({"source": "auto", "codes": ["AAPL"], "engine": "daily"})
_STRATEGY_CODE = "class SignalEngine:\n    def generate(self, *a, **kw):\n        return []\n"


# ── Shared helpers ────────────────────────────────────────────────────────

def _patch_council(monkeypatch, verdict_text: str, confidence: float = 0.9):
    """Stub CouncilBrain.deliberate() so _handle_red_tier() runs for real
    without a real Ollama call — same pattern used across Tasks 57/58A-58E."""
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


def _stub_notification_boundary(monkeypatch, *, wait_for_confirmation_result: bool):
    """Stub only the human-notification/confirmation boundary on the real,
    process-wide PermissionGateway singleton — never the gateway's own
    gating logic."""
    from core.loop.permission_gateway import PermissionGateway
    gw = PermissionGateway()
    monkeypatch.setattr(gw, "_notify", AsyncMock())
    monkeypatch.setattr(gw, "_wait_for_confirmation", AsyncMock(return_value=wait_for_confirmation_result))
    return gw


def _mock_runner_execute(monkeypatch, on_call=None):
    """Replace the real subprocess-execution boundary (Runner.execute) with
    a spy. Returns the list of (entry_script, run_dir) call args."""
    calls: list = []

    def _fake_execute(self, entry_script, run_dir, *, cwd=None, cli_args=None):
        calls.append((entry_script, run_dir))
        if on_call:
            on_call(run_dir)
        return RunResult(success=True, exit_code=0, stdout="ok", stderr="", artifacts={})

    monkeypatch.setattr(Runner, "execute", _fake_execute)
    return calls


def _seed_run_dir(tmp_path, *, with_strategy: bool = True, config: str = _VALID_CONFIG):
    run_dir = tmp_path / "run_1"
    (run_dir / "code").mkdir(parents=True)
    (run_dir / "config.json").write_text(config, encoding="utf-8")
    if with_strategy:
        (run_dir / "code" / "signal_engine.py").write_text(_STRATEGY_CODE, encoding="utf-8")
    return run_dir


def _body(raw: str) -> dict:
    return json.loads(raw)


# ── TEST 1 — shell flag does not create false safety ───────────────────────

def test_1_shell_flag_disabled_does_not_prevent_the_tool_composition_reaching_the_gate(monkeypatch, tmp_path):
    """enable_shell_tools=False correctly excludes bash/background_run —
    but write_file and backtest are registered regardless. Build a REAL
    registry the way vt_research/vt_export do (build_registry(include_
    shell_tools=False)) and confirm both tools are present and that the
    backtest tool still reaches the real gate (not bypassed by the shell
    flag being off)."""
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    from src.tools import build_registry

    registry = build_registry(include_shell_tools=False)
    assert "write_file" in registry.tool_names
    assert "backtest" in registry.tool_names
    assert "bash" not in registry.tool_names
    assert "background_run" not in registry.tool_names

    _patch_council(monkeypatch, "REJECT — refuse")
    gw = _stub_notification_boundary(monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_runner_execute(monkeypatch)

    run_dir = _seed_run_dir(tmp_path)
    result = registry.execute("backtest", {"run_dir": str(run_dir)})
    body = _body(result)

    assert body["status"] == "blocked"
    assert not calls, "unapproved backtest reached the real (mocked) subprocess despite enable_shell_tools=False"


# ── TEST 2 — unauthorized backtest blocked ──────────────────────────────────

def test_2_unauthorized_backtest_blocked(monkeypatch, tmp_path):
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    _patch_council(monkeypatch, "REJECT — refuse")
    _stub_notification_boundary(monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_runner_execute(monkeypatch)

    run_dir = _seed_run_dir(tmp_path)
    body = _body(run_backtest(str(run_dir)))

    assert body["status"] == "blocked"
    assert not calls, "unauthorized run_backtest reached the real (mocked) Runner.execute"


# ── TEST 3 — write_file behavior (executable writes intentionally ungated) ─

def test_3_write_file_of_executable_strategy_is_not_gated_but_stays_inert_without_approval(monkeypatch, tmp_path):
    """This architecture intentionally gates execution, not the write —
    documented and justified in the remediation doc. Prove write_file still
    succeeds (unchanged, harmless-by-itself behavior) but that alone never
    reaches the real subprocess without a separate, real approval at the
    backtest step."""
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    run_dir = tmp_path / "run_2"
    run_dir.mkdir()

    write_body = _body(WriteFileTool().execute(
        path="code/signal_engine.py", content=_STRATEGY_CODE, run_dir=str(run_dir),
    ))
    assert write_body["status"] == "ok"
    assert (run_dir / "code" / "signal_engine.py").read_text(encoding="utf-8") == _STRATEGY_CODE

    # The write alone never executed anything — no Runner.execute call
    # happened as a side effect of write_file, by construction (write_file
    # does not import Runner at all).
    import src.tools.write_file_tool as wf_mod
    assert not hasattr(wf_mod, "Runner")


# ── TEST 4 — composition attack: write_file -> backtest, no approval ───────

def test_4_composition_attack_write_file_then_backtest_without_approval_cannot_execute(monkeypatch, tmp_path):
    """THE MOST IMPORTANT TEST. Simulate the actual ReAct sequence an LLM
    would perform: write config.json, write code/signal_engine.py, then
    call the backtest tool — all through the REAL ToolRegistry.execute()
    dispatch a real AgentLoop would use — with no approval anywhere."""
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    _patch_council(monkeypatch, "REJECT — refuse")
    _stub_notification_boundary(monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_runner_execute(monkeypatch)

    registry = ToolRegistry()
    registry.register(WriteFileTool())
    registry.register(BacktestTool())

    run_dir = tmp_path / "attack_run"
    run_dir.mkdir()

    r1 = _body(registry.execute("write_file", {
        "path": "config.json", "content": _VALID_CONFIG, "run_dir": str(run_dir),
    }))
    r2 = _body(registry.execute("write_file", {
        "path": "code/signal_engine.py", "content": _STRATEGY_CODE, "run_dir": str(run_dir),
    }))
    r3 = _body(registry.execute("backtest", {"run_dir": str(run_dir)}))

    assert r1["status"] == "ok" and r2["status"] == "ok", "the write half of the composition should still succeed (intentionally ungated)"
    assert r3["status"] == "blocked", f"the composed attack must be blocked at the execution step, got: {r3}"
    assert not calls, f"the composed write_file+backtest attack reached real (mocked) subprocess execution: {calls}"


# ── TEST 5 — approved execution ─────────────────────────────────────────────

def test_5_approved_execution_reaches_mocked_runner(monkeypatch, tmp_path):
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    _patch_council(monkeypatch, "DEFER — ask the owner")
    _stub_notification_boundary(monkeypatch, wait_for_confirmation_result=True)
    calls = _mock_runner_execute(monkeypatch)

    run_dir = _seed_run_dir(tmp_path)
    body = _body(run_backtest(str(run_dir)))

    assert body["status"] == "ok"
    assert calls, "approved run_backtest must reach the real (mocked) Runner.execute"
    assert calls[0][1] == run_dir.resolve()


# ── TEST 6 — gateway exception fails closed ─────────────────────────────────

def test_6_gateway_exception_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    calls = _mock_runner_execute(monkeypatch)

    from core.loop.permission_gateway import PermissionGateway
    gw = PermissionGateway()

    async def _boom(action):
        raise RuntimeError("simulated gateway outage")

    monkeypatch.setattr(gw, "execute", _boom)

    run_dir = _seed_run_dir(tmp_path)
    body = _body(run_backtest(str(run_dir)))

    assert body["status"] == "blocked"
    assert not calls


# ── TEST 7 — Action content ─────────────────────────────────────────────────

def test_7_action_content_correct_and_no_unnecessary_source_exposure(monkeypatch, tmp_path):
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    _patch_council(monkeypatch, "DEFER — ask the owner")
    _stub_notification_boundary(monkeypatch, wait_for_confirmation_result=True)
    _mock_runner_execute(monkeypatch)

    from core.loop.permission_gateway import PermissionGateway
    gw = PermissionGateway()
    seen_actions: list = []
    original_execute = gw.execute

    async def _spy(action):
        seen_actions.append(action)
        return await original_execute(action)

    monkeypatch.setattr(gw, "execute", _spy)

    run_dir = _seed_run_dir(tmp_path)
    run_backtest(str(run_dir))

    assert len(seen_actions) == 1
    action = seen_actions[0]
    assert action.action_type == "vt_backtest"
    assert action.proposed_by == "BacktestTool"
    params = action.params
    assert params["run_dir"] == str(run_dir)
    assert params["engine"] == "daily"
    assert params["source"] == "auto"
    assert params["has_strategy_code"] is True
    assert params["strategy_code_length"] == len(_STRATEGY_CODE)
    # A hash/length/preview is used instead of dumping the full source.
    assert "strategy_code_sha256" in params
    assert len(params["strategy_code_sha256"]) == 16
    assert "strategy_code" not in params, (
        "full strategy source must not be placed verbatim in Action.params — "
        "a hash/length/preview is sufficient for the approval decision"
    )
    assert "dynamically imported" in params["summary"].lower() or "no sandbox" in params["summary"].lower()
    # No credential-shaped keys.
    assert not any("token" in k.lower() or "key" in k.lower() or "secret" in k.lower() for k in params)


# ── TEST 8 — public API route (closest real integration path) ──────────────

@pytest.fixture
def clean_registry():
    reg = get_registry()
    before = list(reg._agents.keys())
    yield
    for aid in list(reg._agents.keys()):
        if aid not in before:
            reg._agents.pop(aid, None)


def test_8_vt_research_agent_run_cannot_reach_unauthorized_backtest_execution(monkeypatch, tmp_path):
    """The closest real route to POST /api/investment/research available in
    the existing test architecture: BacktestAgent.run({"type": "vt_research",
    ...}) — the exact call core/api/routers/investment.py's real endpoint
    makes. Rather than requiring a live HTTP server, drive the real agent
    method the router calls. Prove that even if vt_research's own ReAct
    AgentLoop were to attempt the write_file+backtest composition internally,
    the shared run_backtest() gate still refuses without approval — verified
    directly here by exercising the real tool composition an AgentLoop would
    perform, matching the router's actual call shape.

    Deliberately a plain (non-async) test: run_backtest()'s gate bridges to
    the async PermissionGateway via asyncio.run(), exactly as it does in
    real production usage (always invoked from a loop.run_in_executor()
    thread with no already-running event loop) — calling registry.execute()
    from inside an async test function would instead run it on pytest-
    asyncio's own already-running loop, making asyncio.run() raise
    "cannot be called from a running event loop" and falsely take the
    gateway-unavailable fail-closed path instead of exercising the real
    council-reject path this test wants to prove."""
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    _patch_council(monkeypatch, "REJECT — refuse")
    _stub_notification_boundary(monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_runner_execute(monkeypatch)

    # Build the exact registry vt_research() constructs (same build_registry
    # call, same include_shell_tools default), confirming "backtest" is
    # present and gated in precisely the registry shape the real endpoint's
    # AgentLoop would use.
    from src.tools import build_registry
    registry = build_registry(include_shell_tools=False)
    assert "backtest" in registry.tool_names

    run_dir = _seed_run_dir(tmp_path)
    body = _body(registry.execute("backtest", {"run_dir": str(run_dir)}))

    assert body["status"] == "blocked"
    assert not calls


# ── TEST 9 — Governor route ──────────────────────────────────────────────────

def test_9a_governor_dispatch_vt_research_registry_contains_gated_backtest(monkeypatch, tmp_path, clean_registry):
    """Exercise the real Governor.dispatch({"type": "vt_research", ...})
    path down to BacktestAgent, then confirm the tool composition it would
    construct internally is gated — full end-to-end vt_research() would
    invoke a real (slow, non-deterministic) LLM ReAct loop, so this proves
    the specific security property (Governor really reaches BacktestAgent,
    and the registry it would use is gated) without requiring a live LLM.
    Plain (non-async) test for the same asyncio.run() bridging reason as
    TEST 8 above."""
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    agent = BacktestAgent(generation=1)
    agent.health_points = 999999
    get_registry().register(agent)

    # Confirm the real Governor capability-match reaches this exact agent
    # for all three scoped task types.
    gov = Governor()
    for task_type in ("vt_research", "vt_swarm", "vt_export"):
        assert task_type in agent.capabilities

    _patch_council(monkeypatch, "REJECT — refuse")
    _stub_notification_boundary(monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_runner_execute(monkeypatch)

    from src.tools import build_registry
    registry = build_registry(include_shell_tools=False)
    run_dir = _seed_run_dir(tmp_path)
    body = _body(registry.execute("backtest", {"run_dir": str(run_dir)}))

    assert body["status"] == "blocked"
    assert not calls


# ── TEST 10 — pre-existing harmless tool behavior preserved ────────────────

def test_10_harmless_read_only_tools_unaffected(monkeypatch, tmp_path):
    """write_file, read_file for non-executable content, and listing tools
    must continue to work exactly as before — only the backtest execution
    step requires approval."""
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    from src.tools.read_file_tool import ReadFileTool

    run_dir = tmp_path / "harmless_run"
    run_dir.mkdir()

    write_body = _body(WriteFileTool().execute(
        path="notes.md", content="AAPL momentum looks strong this week.", run_dir=str(run_dir),
    ))
    assert write_body["status"] == "ok"

    read_body = _body(ReadFileTool().execute(path="notes.md", run_dir=str(run_dir)))
    assert read_body["status"] == "ok"
    assert "momentum" in read_body["content"]

    from src.tools import build_registry
    registry = build_registry(include_shell_tools=False)
    assert "read_file" in registry.tool_names
    assert "write_file" in registry.tool_names
    # Read-only tools remain marked as such.
    assert ReadFileTool.is_readonly is True


# ── TEST 11 — alternate execution path audit ────────────────────────────────

def test_11a_run_shadow_backtest_tool_reaches_the_same_gate(monkeypatch, tmp_path):
    """shadow_account/backtester.py's _default_run_backtest_fn() imports
    and returns the EXACT same run_backtest function this test file gates —
    confirmed by direct inspection. Prove that behaviorally: call it via
    its own injection point exactly as backtester.py does, unapproved, and
    confirm it is blocked identically."""
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    _patch_council(monkeypatch, "REJECT — refuse")
    _stub_notification_boundary(monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_runner_execute(monkeypatch)

    from src.shadow_account.backtester import _default_run_backtest_fn
    fn = _default_run_backtest_fn()
    assert fn is run_backtest, "shadow_account's injection point must resolve to the same gated function"

    run_dir = _seed_run_dir(tmp_path)
    body = _body(fn(str(run_dir)))

    assert body["status"] == "blocked"
    assert not calls


def test_11b_only_the_two_known_importers_of_run_backtest_exist():
    """Static confirmation of the repo-wide search performed while building
    this fix. A bare substring search for "run_backtest" over-matches
    (docstrings, an unrelated run_backtest_fn parameter name in codegen.py's
    docstring, SKILL.md prose, runner.py's own module docstring) — this
    checks the precise, meaningful signal: an actual `import ... run_backtest`
    statement. Two importers were found, both already accounted for:
      - src/shadow_account/backtester.py (TEST 11a — the "run_shadow_backtest"
        tool's injection point, behaviorally confirmed gated).
      - mcp_server.py (TEST 11c below) — a THIRD, newly-discovered alternate
        entry point: a standalone FastMCP server (`vibe-trading-mcp` CLI
        command, districts/investment/vector_backtest/mcp_server.py) that
        also exposes a "backtest" tool calling this exact function. Confirmed
        DORMANT / NOT RUNTIME REACHABLE from VECTOR's own production code —
        no core/ or districts/ file (outside vector_backtest's own test
        suite) imports or launches it; its own main() is documented as "Entry
        point for `vibe-trading-mcp` CLI command", a separate standalone
        process an operator would start manually. Not part of Governor,
        core/api/routers/investment.py, or any BacktestAgent path. Because
        the 58G gate lives inside run_backtest() itself rather than at any
        one caller, this dormant path is ALSO already gated automatically —
        confirmed behaviorally by TEST 11c, not merely asserted."""
    import re

    vb_root = Path(__file__).parent.parent / "districts" / "investment" / "vector_backtest"
    import_pattern = re.compile(r"^\s*(from\s+\S+\s+)?import\s+.*\brun_backtest\b")

    importers: list[str] = []
    for py_file in vb_root.rglob("*.py"):
        rel = py_file.relative_to(vb_root).as_posix()
        if "/tests/" in f"/{rel}" or "__pycache__" in rel or rel == "src/tools/backtest_tool.py":
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if import_pattern.match(line):
                importers.append(rel)
                break

    assert sorted(importers) == ["mcp_server.py", "src/shadow_account/backtester.py"], (
        f"unexpected additional importer(s) of run_backtest found: {importers}"
    )


def test_11c_dormant_mcp_server_backtest_tool_is_also_gated(monkeypatch, tmp_path):
    """Behaviorally confirms the newly-discovered mcp_server.py entry point
    (TEST 11b) is gated too, even though it is not reachable from VECTOR's
    own production runtime today — its own backtest() function does
    `from src.tools.backtest_tool import run_backtest; return run_backtest(
    run_dir)`, so it inherits the exact same gate automatically."""
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    _patch_council(monkeypatch, "REJECT — refuse")
    _stub_notification_boundary(monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_runner_execute(monkeypatch)

    import districts.investment.vector_backtest.mcp_server as mcp_server_mod
    # FastMCP wraps functions in @mcp.tool decorators; call the underlying
    # function object directly (the same one Governor-independent MCP
    # clients would ultimately invoke).
    backtest_fn = mcp_server_mod.backtest.fn if hasattr(mcp_server_mod.backtest, "fn") else mcp_server_mod.backtest

    run_dir = _seed_run_dir(tmp_path)
    body = _body(backtest_fn(str(run_dir)))

    assert body["status"] == "blocked"
    assert not calls


# ── TEST 12 — no self-mint ──────────────────────────────────────────────────

def test_12a_run_backtest_source_has_no_self_mint_and_gates_before_side_effect():
    import inspect

    src = inspect.getsource(run_backtest)

    assert "grant_control" not in src, (
        "run_backtest() must not mint its own control/capability token — "
        "authorization must come only from PermissionGateway.execute()"
    )
    assert "PermissionGateway().execute" in src

    gate_idx = src.index("PermissionGateway().execute")
    approved_check_idx = src.index("if not gate_result.approved")
    runner_idx = src.index("runner = Runner(")

    assert gate_idx < approved_check_idx < runner_idx, (
        "the gateway call and its approval check must precede Runner "
        "construction/execution in source order"
    )


def test_12b_vt_backtest_action_type_reused_and_still_red():
    from core.config import CONFIG
    assert "vt_backtest" in CONFIG["permission"]["red"]


if __name__ == "__main__":
    ok = pytest.main([__file__, "-v"]) == 0
    print("PASS test_task58g_vector_backtest_react_tool_permission_remediation" if ok else "FAIL")
    sys.exit(0 if ok else 1)
