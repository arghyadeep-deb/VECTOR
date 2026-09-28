"""
Task 58E — Behavioral tests for the vector_backtest strategy-code
permission-bypass remediation (VECTOR_TECHNICAL_KNOWLEDGE/58E_VECTOR_
BACKTEST_STRATEGY_PERMISSION_REMEDIATION.md, closing a Task 59 high-risk
residual).

Original finding (Task 59, §6): BacktestAgent.vt_backtest(strategy_code=...)
wrote caller-supplied Python directly to disk and called the vendored
vector_backtest runner's bt_main(run_dir), which dynamically imports and
instantiates that code as a SignalEngine — with NO PermissionGateway
anywhere in the chain. Task 59 found this currently non-functional in
practice due to an unrelated path mismatch (BacktestAgent writes
run_dir/signal_engine.py; runner.py reads run_dir/code/signal_engine.py) —
Task 59 explicitly warned this accidental failure "MUST NOT be treated as a
security boundary."

Fix: BacktestAgent.vt_backtest() now gates through PermissionGateway.execute
(Action(action_type="vt_backtest", params={...}, proposed_by=self.name))
BEFORE writing config.json/signal_engine.py or calling bt_main(), and
refuses (fail-closed) unless gate_result.approved is True. The gate applies
UNCONDITIONALLY (not only when strategy_code is truthy) — see the
remediation doc's Remediation Design section for why. "vt_backtest" is now
classified RED in core/config.py. The path mismatch itself was deliberately
NOT fixed by this task (see the remediation doc §6/§11) — this file
includes a dedicated test (TEST 9) proving the gate is NOT relying on that
mismatch: it still blocks an unapproved call even when the mismatch is
simulated as corrected.

EXTERNAL BOUNDARY MOCKING: districts/investment/backtest_agent.py inserts
vector_backtest/ onto sys.path ONCE at module-import time (unlike vector_
mlops's per-call namespace-swap trick) — `backtest.runner` is therefore an
ordinarily-cached module under sys.modules['backtest.runner'], directly and
reliably monkeypatchable (`import backtest.runner; monkeypatch.setattr(
backtest.runner, "main", fake)`), verified working end-to-end before this
file was written. This mocks ONLY the external bt_main() boundary — the
single, well-defined function vt_backtest()'s _run() closure calls, fully
encapsulating the downstream dynamic-import/execution primitive.
PermissionGateway.execute(), Governor.dispatch(), and BacktestAgent.run()/
vt_backtest() all run for real throughout, per .claude/rules/testing.md's
"No Mocking: permission_gateway.py — test the real gate". All real file I/O
in these tests is confined to an isolated pytest tmp_path (BacktestAgent.
_runs_dir() is monkeypatched to return it) — never the real repo or the
real ~/.vector/vector_backtest/runs/ directory.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city.agent_registry import get_registry
from core.city.governor import Governor
from districts.investment.backtest_agent import BacktestAgent

# districts/investment/backtest_agent.py inserts vector_backtest/ onto
# sys.path at import time — importing BacktestAgent above makes this
# resolvable.
import backtest.runner as runner_mod


# ── Shared helpers ────────────────────────────────────────────────────────

_STRATEGY_CODE = "class SignalEngine:\n    def generate(self, *a, **kw):\n        return []\n"


def _patch_council(monkeypatch, verdict_text: str, confidence: float = 0.9):
    """Stub CouncilBrain.deliberate() so _handle_red_tier() runs for real
    (real gateway logic, real verdict-processing) without a real Ollama
    call — same pattern used across Tasks 57/58A/58B/58C/58D."""
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


def _mock_bt_main(monkeypatch, on_call=None):
    """Replace the external bt_main() execution boundary with a spy.
    Returns the list of run_dir paths it was called with."""
    calls: list = []

    def _fake_main(run_dir):
        calls.append(run_dir)
        if on_call:
            on_call(run_dir)

    monkeypatch.setattr(runner_mod, "main", _fake_main)
    return calls


def _new_agent(monkeypatch, tmp_path, *, wait_for_confirmation_result: bool):
    """A fresh BacktestAgent repointed at an isolated tmp_path (never the
    real repo or ~/.vector/vector_backtest/runs/), with the gateway's
    human-notification boundary stubbed (never mocking the gateway's own
    gating logic)."""
    agent = BacktestAgent(generation=1)
    monkeypatch.setattr(agent, "_runs_dir", lambda: tmp_path)

    agent._gateway._notify = AsyncMock()
    agent._gateway._wait_for_confirmation = AsyncMock(return_value=wait_for_confirmation_result)
    return agent


def _spy_gateway_execute(agent):
    calls: list = []
    original = agent._gateway.execute

    async def _spy(action):
        calls.append(action)
        return await original(action)

    agent._gateway.execute = _spy
    return calls


def _any_py_files_under(tmp_path) -> list[Path]:
    return list(tmp_path.rglob("*.py"))


# ── TEST 1 — rejected: no persistence, no bt_main, no dynamic import ───────

async def test_1_unapproved_vt_backtest_does_not_persist_or_execute(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "REJECT — no owner context, refuse")
    bt_calls = _mock_bt_main(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=False)
    gw_calls = _spy_gateway_execute(agent)

    result = await agent.vt_backtest(
        codes=["AAPL"], start_date="2024-01-01", end_date="2024-02-01",
        strategy_code=_STRATEGY_CODE,
    )

    assert len(gw_calls) == 1 and gw_calls[0].action_type == "vt_backtest", (
        "PermissionGateway.execute must actually be invoked"
    )
    assert result["status"] == "blocked"
    assert not bt_calls, f"unapproved vt_backtest reached the real (mocked) bt_main: {bt_calls}"
    assert not _any_py_files_under(tmp_path), (
        "unapproved vt_backtest must never persist strategy_code to any .py file"
    )
    assert not list(tmp_path.iterdir()), "unapproved vt_backtest must not even create a run_dir/config.json"


# ── TEST 2 — gateway error: fail closed ─────────────────────────────────────

async def test_2_gateway_unreachable_fails_closed(monkeypatch, tmp_path):
    bt_calls = _mock_bt_main(monkeypatch)
    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=True)

    async def _boom(action):
        raise RuntimeError("simulated gateway outage")

    agent._gateway.execute = _boom

    result = await agent.vt_backtest(
        codes=["AAPL"], start_date="2024-01-01", end_date="2024-02-01",
        strategy_code=_STRATEGY_CODE,
    )

    assert result["status"] == "blocked"
    assert not bt_calls
    assert not _any_py_files_under(tmp_path)


# ── TEST 3 — approved: persistence + mocked execution reached ──────────────

async def test_3_approved_vt_backtest_reaches_persistence_and_mocked_execution(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    bt_calls = _mock_bt_main(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=True)

    result = await agent.vt_backtest(
        codes=["AAPL"], start_date="2024-01-01", end_date="2024-02-01",
        strategy_code=_STRATEGY_CODE,
    )

    assert result["status"] == "ok"
    assert bt_calls, "approved vt_backtest must reach the real (mocked) bt_main"
    # strategy_code was persisted somewhere under the run dir (current,
    # pre-existing write path — see the path-mismatch analysis in the doc).
    py_files = _any_py_files_under(tmp_path)
    assert py_files, "approved vt_backtest must persist strategy_code to disk"
    assert any(_STRATEGY_CODE in f.read_text(encoding="utf-8") for f in py_files)


# ── TEST 4 — ordering: gate strictly before persistence and execution ──────

async def test_4_gate_precedes_persistence_and_bt_main(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "DEFER — ask the owner")

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=True)

    call_order: list = []
    original_execute = agent._gateway.execute

    async def _spy_execute(action):
        call_order.append("gateway.execute")
        return await original_execute(action)

    agent._gateway.execute = _spy_execute

    def _on_bt_main(run_dir):
        call_order.append("bt_main")
        # At the moment bt_main is invoked, config.json must already exist
        # (real pre-existing write logic) — proving persistence happened
        # strictly after the gate too, not interleaved before it.
        assert (Path(run_dir) / "config.json").exists()

    _mock_bt_main(monkeypatch, on_call=_on_bt_main)

    await agent.vt_backtest(
        codes=["AAPL"], start_date="2024-01-01", end_date="2024-02-01",
        strategy_code=_STRATEGY_CODE,
    )

    assert call_order == ["gateway.execute", "bt_main"], (
        f"gate must precede persistence and execution — got order: {call_order}"
    )


# ── TEST 5 — Action content: correct type, description, no leakage ─────────

async def test_5_action_content_correct_and_no_unnecessary_exposure(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    _mock_bt_main(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=True)
    gw_calls = _spy_gateway_execute(agent)

    await agent.vt_backtest(
        codes=["AAPL", "TSLA"], start_date="2024-01-01", end_date="2024-02-01",
        strategy_code=_STRATEGY_CODE, source="yfinance", engine="daily", interval="1D",
    )

    assert len(gw_calls) == 1
    action = gw_calls[0]
    assert action.action_type == "vt_backtest"
    assert action.proposed_by == "BacktestAgent"
    params = action.params
    assert params["codes"] == ["AAPL", "TSLA"]
    assert params["start_date"] == "2024-01-01"
    assert params["end_date"] == "2024-02-01"
    assert params["source"] == "yfinance"
    assert params["engine"] == "daily"
    assert params["has_strategy_code"] is True
    assert params["strategy_code"] == _STRATEGY_CODE
    # Human-readable summary must clearly describe real code execution, not
    # an unqualified "run backtest".
    summary = params["summary"].lower()
    assert "caller-supplied" in summary or "signal engine" in summary
    assert "dynamically imported" in summary or "no sandbox" in summary
    # No unrelated sensitive content (e.g. no API keys/tokens) is injected —
    # params are exactly the run's own declared arguments.
    assert set(params.keys()) == {
        "codes", "start_date", "end_date", "source", "engine", "interval",
        "has_strategy_code", "strategy_code", "summary",
    }


# ── TEST 6 — Governor capability routing ────────────────────────────────────

@pytest.fixture
def clean_registry():
    reg = get_registry()
    before = list(reg._agents.keys())
    yield
    for aid in list(reg._agents.keys()):
        if aid not in before:
            reg._agents.pop(aid, None)


def _vt_backtest_task(**overrides):
    task = {
        "type": "vt_backtest", "district": "investment",
        "params": {
            "codes": ["AAPL"], "start_date": "2024-01-01", "end_date": "2024-02-01",
            "strategy_code": _STRATEGY_CODE,
        },
    }
    task.update(overrides)
    return task


async def test_6a_governor_dispatch_unapproved_vt_backtest_blocked(monkeypatch, tmp_path, clean_registry):
    _patch_council(monkeypatch, "REJECT — refuse")
    bt_calls = _mock_bt_main(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=False)
    agent.health_points = 999999
    get_registry().register(agent)

    gov = Governor()
    result = await gov.dispatch(_vt_backtest_task())

    assert not bt_calls, f"Governor-routed unapproved vt_backtest reached bt_main: {bt_calls}"


async def test_6b_governor_dispatch_approved_vt_backtest_reaches_mocked_execution(monkeypatch, tmp_path, clean_registry):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    bt_calls = _mock_bt_main(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=True)
    agent.health_points = 999999
    get_registry().register(agent)

    # 2026-09-23: Governor.dispatch() now enforces its own authorization
    # boundary for YELLOW/RED task types -- issue the real receipt.
    from core.loop.permission_gateway import PermissionGateway
    PermissionGateway()._issue_approval_receipt("vt_backtest", purpose="governor_dispatch")

    gov = Governor()
    result = await gov.dispatch(_vt_backtest_task())

    assert bt_calls, f"Governor-routed approved vt_backtest never reached the (mocked) bt_main, got: {result}"


# ── TEST 7 — direct entry point hits the same gate ──────────────────────────

async def test_7_direct_vt_backtest_call_cannot_bypass_gate(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "REJECT — refuse")
    bt_calls = _mock_bt_main(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=False)
    result = await agent.vt_backtest(
        codes=["AAPL"], start_date="2024-01-01", end_date="2024-02-01",
        strategy_code=_STRATEGY_CODE,
    )

    assert result["status"] == "blocked"
    assert not bt_calls


async def test_7b_run_dispatch_reaches_same_gate(monkeypatch, tmp_path):
    """run()'s own task_type dispatch (a second, non-Governor entry point)
    must funnel through the identical gate — no alternate code path."""
    _patch_council(monkeypatch, "REJECT — refuse")
    bt_calls = _mock_bt_main(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=False)
    result = await agent.run({
        "type": "vt_backtest",
        "params": {"codes": ["AAPL"], "start_date": "2024-01-01", "end_date": "2024-02-01",
                   "strategy_code": _STRATEGY_CODE},
    })

    assert result.get("status") == "blocked"
    assert not bt_calls


# ── TEST 8 — no strategy_code: still gated (architecture requires it) ──────

async def test_8_no_strategy_code_still_gated_and_reflects_absence_in_action(monkeypatch, tmp_path):
    """Confirms the deliberate design choice (documented in §7 of the
    remediation doc): the gate applies unconditionally, not only when
    strategy_code is truthy."""
    _patch_council(monkeypatch, "REJECT — refuse")
    bt_calls = _mock_bt_main(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=False)
    gw_calls = _spy_gateway_execute(agent)

    result = await agent.vt_backtest(codes=["AAPL"], start_date="2024-01-01", end_date="2024-02-01")

    assert len(gw_calls) == 1
    assert gw_calls[0].params["has_strategy_code"] is False
    assert result["status"] == "blocked"
    assert not bt_calls


# ── TEST 9 — path-mismatch diagnostic: gate holds even if path is "fixed" ──

async def test_9_gate_blocks_unapproved_even_with_corrected_path_simulated(monkeypatch, tmp_path):
    """Task 59/58E explicitly warn: the current write-path mismatch (writes
    to run_dir/signal_engine.py; runner.py reads run_dir/code/signal_engine.py)
    must NOT be treated as the security boundary. This test simulates the
    mismatch being corrected (bt_main() reading from the SAME location the
    agent writes to, i.e. a fully "working" pipeline) and proves the real
    PermissionGateway boundary — not the accidental path bug — is what
    blocks an unapproved request."""
    _patch_council(monkeypatch, "REJECT — refuse")

    reached_dynamic_import = {"value": False}

    def _fake_main_matching_current_write_path(run_dir):
        # Simulates a "fixed" runner.py that correctly reads from wherever
        # BacktestAgent actually writes (today: run_dir/signal_engine.py
        # directly, no "code" subdirectory) and would dynamically import it.
        signal_path = Path(run_dir) / "signal_engine.py"
        if signal_path.exists():
            reached_dynamic_import["value"] = True

    monkeypatch.setattr(runner_mod, "main", _fake_main_matching_current_write_path)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=False)
    result = await agent.vt_backtest(
        codes=["AAPL"], start_date="2024-01-01", end_date="2024-02-01",
        strategy_code=_STRATEGY_CODE,
    )

    assert result["status"] == "blocked"
    assert reached_dynamic_import["value"] is False, (
        "even with the path mismatch simulated as corrected, an unapproved "
        "request must never reach the point of dynamic import — the real "
        "gate, not the accidental bug, must be what blocks it"
    )
    assert not _any_py_files_under(tmp_path)


# ── No self-mint check (mirrors 58B/58C/58D) ────────────────────────────────

def test_10a_vt_backtest_source_has_no_self_mint_and_gates_before_side_effect():
    import inspect

    src = inspect.getsource(BacktestAgent.vt_backtest)

    assert "grant_control" not in src, (
        "vt_backtest() must not mint its own control/capability token — "
        "authorization must come only from PermissionGateway.execute()"
    )
    assert "self._gateway.execute" in src

    gate_idx = src.index("self._gateway.execute")
    approved_check_idx = src.index("if not gate_result.approved")
    run_def_idx = src.index("def _run():")

    assert gate_idx < approved_check_idx < run_def_idx, (
        "the gateway call and its approval check must precede the closure "
        "that persists strategy_code and calls bt_main()"
    )


def test_10b_vt_backtest_is_red_tier():
    from core.config import CONFIG
    assert "vt_backtest" in CONFIG["permission"]["red"]
    for tier in ("green", "yellow"):
        assert "vt_backtest" not in CONFIG["permission"][tier]


if __name__ == "__main__":
    ok = pytest.main([__file__, "-v"]) == 0
    print("PASS test_task58e_vector_backtest_strategy_permission_remediation" if ok else "FAIL")
    sys.exit(0 if ok else 1)
