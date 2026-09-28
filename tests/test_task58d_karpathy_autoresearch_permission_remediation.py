"""
Task 58D — Behavioral tests for the Karpathy autoresearch permission-bypass
remediation (VECTOR_TECHNICAL_KNOWLEDGE/58D_KARPATHY_AUTORESEARCH_PERMISSION_
REMEDIATION.md, closing Task 59 Finding D).

Original finding (Task 59, Finding D): AutoresearchRunner.run_experiment_cycle()
asked the local reasoning LLM to propose a change to train.py, WROTE that
LLM-generated Python directly to disk, and EXECUTED it via a real, unsandboxed
subprocess.run() — reachable via Governor.dispatch()'s ordinary capability
match, with NO PermissionGateway step anywhere in the chain and no permission-
tier classification for "run_experiment_cycle" at all.

Fix: AutoresearchRunner.run_experiment_cycle() now gates through
PermissionGateway.execute(Action(action_type="run_experiment_cycle",
params={...}, proposed_by=self.name)) BEFORE the git-branch setup, the
baseline subprocess run, the LLM-proposal loop, every train.py write, and
every subsequent subprocess run — and refuses (fail-closed) unless
gate_result.approved is True. "run_experiment_cycle" is now classified RED
in core/config.py.

TEST ISOLATION: the only two OS-level primitives this file's write-then-run
loop can reach are `subprocess.run` (train.py execution, and git branch/
commit operations) — both mocked directly on the `autoresearch_runner`
module's own `subprocess` reference, never via a named wrapper method, per
the lesson from the Task 58A incident (mock the actual primitive, not a
method that might stop being the real call path after a refactor). Real
file writes are permitted ONLY to an isolated pytest `tmp_path` directory —
runner._train_script/_runs_dir are always repointed at tmp_path in these
tests, never at the real repo's data/training_runs/. The real LLM call
(_propose_improvement -> core.inference.vectorcode_llm.chat) is mocked to
avoid a real Ollama call and to produce deterministic proposed code.

No mocking of permission_gateway.py's own gating logic (execute(), classify(),
_handle_red_tier()'s verdict-processing) or of Governor.dispatch()'s routing
logic — per .claude/rules/testing.md ("No Mocking: permission_gateway.py —
test the real gate"). Only the external CouncilBrain LLM dependency and the
human Pushover notification/confirmation boundary are simulated, matching
the established pattern from Tasks 57/58A/58B/58C.
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
from districts.karpathy_lab.autoresearch_runner import AutoresearchRunner
import districts.karpathy_lab.autoresearch_runner as ar_mod


# ── Shared helpers ────────────────────────────────────────────────────────

def _patch_council(monkeypatch, verdict_text: str, confidence: float = 0.9):
    """Stub CouncilBrain.deliberate() so _handle_red_tier() runs for real
    (real gateway logic, real verdict-processing) without a real Ollama
    call — same pattern used across Tasks 57/58A/58B/58C."""
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


def _mock_subprocess(monkeypatch, on_run=None):
    """Mock the actual OS-level primitive (subprocess.run) this file's
    training-run and git-branch/commit operations use. Returns the list of
    every command invoked."""
    calls: list = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        if on_run:
            on_run(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = "---\nval_bpb:          0.9000\ntraining_seconds: 1.0\npeak_vram_mb:     100.0\n---"
        result.stderr = ""
        return result

    monkeypatch.setattr(ar_mod.subprocess, "run", _fake_run)
    return calls


def _new_agent(monkeypatch, tmp_path, *, wait_for_confirmation_result: bool, train_code: str = "def train():\n    pass\n"):
    """A fresh AutoresearchRunner repointed at an isolated tmp_path (never
    the real repo's data/training_runs/), with the gateway's human-
    notification boundary stubbed (never mocking the gateway's own gating
    logic), and the real LLM proposal call mocked to avoid a real Ollama
    call and produce deterministic output."""
    agent = AutoresearchRunner(generation=1)
    agent._runs_dir = tmp_path
    agent._train_script = tmp_path / "train.py"
    agent._train_script.write_text(train_code, encoding="utf-8")
    agent._data_dir = tmp_path / "data"
    agent._data_dir.mkdir(exist_ok=True)

    agent._gateway._notify = AsyncMock()
    agent._gateway._wait_for_confirmation = AsyncMock(return_value=wait_for_confirmation_result)

    # Never touch the real git repo during tests — a real branch/commit is
    # itself a real, permanent side effect outside the isolated tmp_path,
    # and is not part of Finding D's core write/execute chain being tested.
    monkeypatch.setattr(agent, "_create_experiment_branch", lambda tag: None)

    # Deterministic, non-Ollama LLM proposal.
    monkeypatch.setattr(
        agent, "_propose_improvement",
        lambda train_code, history: "def train():\n    pass  # proposed improvement\n",
    )

    return agent


def _spy_gateway_execute(agent):
    calls: list = []
    original = agent._gateway.execute

    async def _spy(action):
        calls.append(action)
        return await original(action)

    agent._gateway.execute = _spy
    return calls


# ── TEST 1 — unauthorized/rejected: no write, no subprocess ────────────────

async def test_1_unapproved_run_experiment_cycle_does_not_write_or_execute(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "REJECT — no owner context, refuse")
    proc_calls = _mock_subprocess(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=False)
    original_code = agent._train_script.read_text(encoding="utf-8")
    gw_calls = _spy_gateway_execute(agent)

    result = await agent.run_experiment_cycle()

    assert len(gw_calls) == 1 and gw_calls[0].action_type == "run_experiment_cycle", (
        "PermissionGateway.execute must actually be invoked"
    )
    assert result["status"] == "blocked"
    assert not proc_calls, f"unapproved run_experiment_cycle triggered a real subprocess: {proc_calls}"
    assert agent._train_script.read_text(encoding="utf-8") == original_code, (
        "unapproved run_experiment_cycle must never write to train.py"
    )


# ── TEST 2 — gateway error: fail closed ─────────────────────────────────────

async def test_2_gateway_unreachable_fails_closed(monkeypatch, tmp_path):
    proc_calls = _mock_subprocess(monkeypatch)
    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=True)
    original_code = agent._train_script.read_text(encoding="utf-8")

    async def _boom(action):
        raise RuntimeError("simulated gateway outage")

    agent._gateway.execute = _boom

    result = await agent.run_experiment_cycle()

    assert result["status"] == "blocked"
    assert not proc_calls
    assert agent._train_script.read_text(encoding="utf-8") == original_code


# ── TEST 3 — authorized: gateway approves, mocked execution path reached ───

async def test_3_approved_run_experiment_cycle_reaches_mocked_execution(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    proc_calls = _mock_subprocess(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=True)

    call_order: list = []
    original_execute = agent._gateway.execute

    async def _spy_execute(action):
        call_order.append("gateway.execute")
        return await original_execute(action)

    agent._gateway.execute = _spy_execute

    def _on_run(cmd):
        call_order.append("subprocess.run")

    proc_calls = _mock_subprocess(monkeypatch, on_run=_on_run)

    result = await agent.run_experiment_cycle()

    # run_experiment_cycle() itself returns the raw experiment summary
    # ({"experiments", "best_val_bpb", ...}, no "status" key) when the
    # cycle actually runs — "status": "blocked" only appears when the gate
    # refuses. run()'s dispatch wraps this in {"status": "ok", **result}.
    assert result.get("status") != "blocked"
    assert "experiments" in result
    assert proc_calls, "approved run_experiment_cycle must reach the real (mocked) subprocess execution"
    assert call_order[0] == "gateway.execute", (
        f"the gateway approval must happen before any subprocess call — got order: {call_order}"
    )
    assert call_order.index("gateway.execute") < call_order.index("subprocess.run")


# ── TEST 4 — exact Action: action_type + consequential params ──────────────

async def test_4_action_type_and_consequential_params(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    _mock_subprocess(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=True)
    gw_calls = _spy_gateway_execute(agent)

    await agent.run_experiment_cycle()

    assert len(gw_calls) == 1
    action = gw_calls[0]
    assert action.action_type == "run_experiment_cycle"
    assert action.proposed_by == "AutoresearchRunner"
    params = action.params
    assert params["max_experiments"] == agent.MAX_EXPERIMENTS_PER_RUN
    assert params["time_budget_minutes_per_run"] == agent.TIME_BUDGET_MINUTES
    assert params["train_script"] == str(agent._train_script)
    # Human-readable summary must surface the real, concrete scope, not an
    # unqualified "run experiments" — without dumping full prompts/secrets.
    assert str(agent.MAX_EXPERIMENTS_PER_RUN) in params["summary"]
    assert str(agent.TIME_BUDGET_MINUTES) in params["summary"]
    assert "unsandboxed" in params["summary"].lower() or "subprocess" in params["summary"].lower()


# ── TEST 5 — Governor reachability: boundary encountered before side effects ─

@pytest.fixture
def clean_registry():
    reg = get_registry()
    before = list(reg._agents.keys())
    yield
    for aid in list(reg._agents.keys()):
        if aid not in before:
            reg._agents.pop(aid, None)


async def test_5a_governor_dispatch_unapproved_run_experiment_cycle_blocked(monkeypatch, tmp_path, clean_registry):
    _patch_council(monkeypatch, "REJECT — refuse")
    proc_calls = _mock_subprocess(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=False)
    agent.health_points = 999999  # win any HP tie-break unambiguously
    get_registry().register(agent)

    gov = Governor()
    result = await gov.dispatch({
        "type": "run_experiment_cycle",
        "district": "karpathy_lab",
        "params": {},
    })

    assert not proc_calls, f"Governor-routed unapproved run_experiment_cycle triggered a real subprocess: {proc_calls}"


async def test_5b_governor_dispatch_approved_run_experiment_cycle_reaches_mocked_execution(monkeypatch, tmp_path, clean_registry):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    proc_calls = _mock_subprocess(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=True)
    agent.health_points = 999999
    get_registry().register(agent)

    # 2026-09-23: Governor.dispatch() now enforces its own authorization
    # boundary for YELLOW/RED task types -- issue the real receipt.
    from core.loop.permission_gateway import PermissionGateway
    PermissionGateway()._issue_approval_receipt("run_experiment_cycle", purpose="governor_dispatch")

    gov = Governor()
    result = await gov.dispatch({
        "type": "run_experiment_cycle",
        "district": "karpathy_lab",
        "params": {},
    })

    assert proc_calls, f"Governor-routed approved run_experiment_cycle never reached the (mocked) subprocess, got: {result}"


async def test_5c_direct_call_reaches_same_gate_run_dispatch(monkeypatch, tmp_path):
    """run()'s own task_type dispatch (a second, non-Governor entry point)
    must funnel through the identical gate — no alternate code path."""
    _patch_council(monkeypatch, "REJECT — refuse")
    proc_calls = _mock_subprocess(monkeypatch)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=False)
    result = await agent.run({"type": "run_experiment_cycle", "params": {}})

    assert result.get("status") == "blocked"
    assert not proc_calls


# ── TEST 6 — existing behavior: experiment-loop logic intact after approval ─

async def test_6_experiment_loop_logic_still_works_after_approval(monkeypatch, tmp_path):
    """Prove the fix didn't break the pre-existing baseline+propose+keep-or-
    revert logic — with everything mocked, an approved cycle should still
    run a baseline, attempt improvements, and produce a coherent summary."""
    _patch_council(monkeypatch, "DEFER — ask the owner")

    # First call = baseline, subsequent calls = improvement iterations —
    # make the second experiment "improve" so the keep-vs-revert branch and
    # the final permanent-write branch are both exercised.
    call_n = {"n": 0}

    def _fake_run(cmd, **kwargs):
        call_n["n"] += 1
        result = MagicMock()
        result.returncode = 0
        # First (baseline) run: worse score. Later runs: better score.
        bpb = 0.9 if call_n["n"] == 1 else 0.5
        result.stdout = f"---\nval_bpb:          {bpb}\ntraining_seconds: 1.0\npeak_vram_mb:     100.0\n---"
        result.stderr = ""
        return result

    monkeypatch.setattr(ar_mod.subprocess, "run", _fake_run)

    agent = _new_agent(monkeypatch, tmp_path, wait_for_confirmation_result=True)
    result = await agent.run_experiment_cycle()

    assert result.get("status") != "blocked"
    assert result["experiments"] >= 2  # baseline + at least one improvement attempt
    assert result["best_val_bpb"] == 0.5
    assert result["improved"] is True
    # The improved code should have been written permanently.
    assert "proposed improvement" in agent._train_script.read_text(encoding="utf-8")


# ── No self-mint check (mirrors 58B/58C TEST 8) ─────────────────────────────

def test_7a_run_experiment_cycle_source_has_no_self_mint_and_gates_before_side_effect():
    import inspect

    src = inspect.getsource(AutoresearchRunner.run_experiment_cycle)

    assert "grant_control" not in src, (
        "run_experiment_cycle() must not mint its own control/capability token — "
        "authorization must come only from PermissionGateway.execute()"
    )
    assert "self._gateway.execute" in src

    gate_idx = src.index("self._gateway.execute")
    approved_check_idx = src.index("if not gate_result.approved")
    branch_idx = src.index("_create_experiment_branch")
    baseline_idx = src.index("_run_training()")

    assert gate_idx < approved_check_idx < branch_idx < baseline_idx, (
        "the gateway call and its approval check must precede both the git-"
        "branch setup and the baseline training run in source order — the "
        "real side effect must be strictly downstream of the approved "
        "gateway path"
    )


def test_7b_run_experiment_cycle_is_red_tier():
    from core.config import CONFIG
    assert "run_experiment_cycle" in CONFIG["permission"]["red"]
    for tier in ("green", "yellow"):
        assert "run_experiment_cycle" not in CONFIG["permission"][tier]


if __name__ == "__main__":
    ok = pytest.main([__file__, "-v"]) == 0
    print("PASS test_task58d_karpathy_autoresearch_permission_remediation" if ok else "FAIL")
    sys.exit(0 if ok else 1)
