"""
Task 58C — Behavioral tests for the MLOps hf_train permission-bypass
remediation (VECTOR_TECHNICAL_KNOWLEDGE/58C_MLOPS_HF_TRAIN_PERMISSION_
REMEDIATION.md).

Original finding (Task 57, Finding C): MLOpsAgent.hf_train() forwarded a
caller-supplied Python `script` string, unvalidated, into a real remote job
submission to HuggingFace Jobs (`hf_jobs_handler()`), using the owner's HF
credentials and incurring real (potentially GPU-tier) billing — with NO
PermissionGateway step anywhere in the chain. Reachable via Governor.
dispatch()'s exact-match AND LLM-classified cross-district capability
routing, and via a direct `run()`/`hf_train()` call.

Fix: MLOpsAgent.hf_train() now gates through PermissionGateway.execute(
Action(action_type="hf_train", params={"script", "repo_id", "hardware",
"timeout", "requirements", "summary"}, proposed_by=self.name)) BEFORE
calling the real HF Jobs submission helper, and refuses (fail-closed)
unless gate_result.approved is True. "hf_train" is now classified RED in
core/config.py.

FRESH DISCOVERY THIS TASK (documented in the remediation doc, §3/§19, NOT
fixed here — out of scope for a security remediation): hf_train()'s `_run()`
closure builds an `args` dict for `hf_jobs_handler()` that never sets the
required `"operation"` key, and never passes a `session` (so `hf_token` is
always None inside the handler). This means the PRE-EXISTING, UNMODIFIED
call to the real HF Jobs library would itself error out early today
(`HfJobsTool.execute()`'s "'operation' parameter is required" branch) —
this is an unrelated, pre-existing FUNCTIONAL bug, not something this
security fix needed to touch. It does not weaken this task's security
proof: the tests below mock at the `hf_jobs_handler()` boundary itself
(the single, well-defined interface `hf_train()` calls), so they correctly
prove "was the real external boundary reached" independent of whether that
boundary's own internal call would additionally fail for an unrelated
reason.

EXTERNAL BOUNDARY MOCKING STRATEGY: `hf_train()`'s `_run()` closure imports
`hf_jobs_handler` fresh, inside a `with _vector_mlops_agent_namespace():`
block, via a bare `from agent.tools.jobs_tool import hf_jobs_handler` —
this dynamically swaps `sys.path`/`sys.modules['agent'*]` in and out on
every single call (districts/coding/mlops_agent.py's own namespace-
isolation mechanism, needed because the vendored package's internal
imports assume a bare `agent` top-level package). A monkeypatch applied to
one particular imported module OBJECT does not survive to the next call,
since the namespace manager deletes and re-creates that sys.modules entry
each time — Task 57's own diagnostic file documented this exact difficulty
("attempting to monkeypatch that import target proved unreliable across
repeated runs — a fresh module object each call") and fell back to
source-inspection only for this specific call. This task needed a more
robust mechanism for real behavioral tests, and found one: replace
mlops_agent._vector_mlops_agent_namespace itself (a single, stable,
directly-monkeypatchable module-level object — NOT re-created per call)
with a no-op context manager, and pre-seed `sys.modules['agent']` /
`['agent.tools']` / `['agent.tools.jobs_tool']` (via monkeypatch.setitem,
so pytest reverts them automatically) with a fake module whose
`hf_jobs_handler` is an async spy. Verified working end-to-end before
writing these tests. This mocks ONLY the external HF submission interface
— PermissionGateway.execute(), Governor.dispatch(), and MLOpsAgent.run()/
hf_train() all run for real throughout, per .claude/rules/testing.md's
"No Mocking: permission_gateway.py — test the real gate".
"""
from __future__ import annotations

import sys
import types
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# NOTE: an earlier draft of this file also added an autouse fixture that
# monkeypatched httpx.Client/AsyncClient globally to prove no real HTTP
# client could be constructed anywhere in this file. That broke an
# unrelated huggingface_hub module (`hf_api.py`'s `_GLOBAL_CLIENT: httpx.
# Client | None = None` type annotation evaluates `httpx.Client | None` at
# import time, which raises TypeError once `httpx.Client` is replaced by a
# plain function) — collateral damage for zero additional safety, since the
# `_stub_hf_jobs_handler()` boundary below already makes the real
# `agent.tools.jobs_tool` module (the only importer of HfApi in the
# hf_train() call chain) structurally unreachable: it is never imported at
# all when the fake sys.modules entries are in place. Removed; the
# hf_jobs_handler-level mock is sufficient and was verified end-to-end
# before this file was written (see the module docstring above).

from core.city.agent_registry import get_registry
from core.city.governor import Governor
from districts.coding.mlops_agent import MLOpsAgent
import districts.coding.mlops_agent as mlops_mod


# ── Shared helpers ────────────────────────────────────────────────────────

def _patch_council(monkeypatch, verdict_text: str, confidence: float = 0.9):
    """Stub CouncilBrain.deliberate() so _handle_red_tier() runs for real
    (real gateway logic, real verdict-processing) without a real Ollama
    call — same pattern used across Tasks 57/58A/58B."""
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


def _stub_hf_jobs_handler(monkeypatch):
    """Replace the external HF Jobs submission boundary with an async spy.
    Returns the `calls` list — each entry is the exact `arguments` dict
    hf_train()'s _run() closure passed to hf_jobs_handler()."""
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

    monkeypatch.setitem(sys.modules, "agent", fake_agent)
    monkeypatch.setitem(sys.modules, "agent.tools", fake_agent_tools)
    monkeypatch.setitem(sys.modules, "agent.tools.jobs_tool", fake_jobs_tool)

    @contextlib.contextmanager
    def _noop_namespace():
        yield

    monkeypatch.setattr(mlops_mod, "_vector_mlops_agent_namespace", _noop_namespace)
    return calls


def _new_agent(monkeypatch, *, wait_for_confirmation_result: bool):
    agent = MLOpsAgent()
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


_SCRIPT = "print('hello from a caller-supplied training script')"


# ── TEST 1 — unapproved hf_train is blocked (via run()) ────────────────────

async def test_1_unapproved_hf_train_via_run_is_blocked(monkeypatch):
    _patch_council(monkeypatch, "REJECT — no owner context, refuse")
    hf_calls = _stub_hf_jobs_handler(monkeypatch)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=False)
    gw_calls = _spy_gateway_execute(agent)

    result = await agent.run({"params": {
        "action": "hf_train", "script": _SCRIPT, "repo_id": "owner/repo",
        "hardware": "a100-large", "timeout": 3600,
    }})

    assert len(gw_calls) == 1 and gw_calls[0].action_type == "hf_train", (
        "PermissionGateway.execute must actually be invoked"
    )
    assert result["status"] == "blocked"
    assert not hf_calls, f"unapproved hf_train reached the real (mocked) HF Jobs submission: {hf_calls}"


# ── TEST 2 — approved hf_train reaches remote submission ───────────────────

async def test_2_approved_hf_train_reaches_submission_only_after_authorization(monkeypatch):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    hf_calls = _stub_hf_jobs_handler(monkeypatch)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)

    call_order: list = []
    original_execute = agent._gateway.execute

    async def _spy_execute(action):
        call_order.append("gateway.execute")
        return await original_execute(action)

    agent._gateway.execute = _spy_execute

    real_stub = sys.modules["agent.tools.jobs_tool"].hf_jobs_handler

    async def _tracking_handler(arguments, session=None, tool_call_id=None):
        call_order.append("hf_jobs_handler")
        return await real_stub(arguments, session=session, tool_call_id=tool_call_id)

    sys.modules["agent.tools.jobs_tool"].hf_jobs_handler = _tracking_handler

    result = await agent.hf_train(
        script=_SCRIPT, repo_id="owner/repo", hardware="cpu-basic", timeout=1800,
    )

    assert result["status"] == "ok"
    assert call_order == ["gateway.execute", "hf_jobs_handler"], (
        "the real submission must only be reached AFTER the gateway approves — "
        f"got order: {call_order}"
    )
    assert hf_calls and hf_calls[0]["script"] == _SCRIPT
    assert hf_calls[0]["repo_id"] == "owner/repo"
    assert hf_calls[0]["hardware"] == "cpu-basic"


# ── TEST 3 — direct hf_train() call cannot bypass the gate ─────────────────

async def test_3_direct_hf_train_call_cannot_bypass_gate(monkeypatch):
    _patch_council(monkeypatch, "REJECT — refuse")
    hf_calls = _stub_hf_jobs_handler(monkeypatch)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=False)

    result = await agent.hf_train(
        script=_SCRIPT, repo_id="owner/repo", hardware="a100-large", timeout=3600,
    )

    assert result["status"] == "blocked"
    assert not hf_calls, "a direct hf_train() import+call bypassed the gate"


async def test_3b_direct_hf_train_call_approved_still_reaches_submission(monkeypatch):
    """Sanity complement to TEST 3: a direct call is not MORE restricted
    than the gated path either — approval still works when called directly."""
    _patch_council(monkeypatch, "DEFER — ask the owner")
    hf_calls = _stub_hf_jobs_handler(monkeypatch)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)

    result = await agent.hf_train(
        script=_SCRIPT, repo_id="owner/repo", hardware="cpu-basic", timeout=600,
    )

    assert result["status"] == "ok"
    assert hf_calls


# ── TEST 4 — Governor exact-match route ─────────────────────────────────────

@pytest.fixture
def clean_registry():
    reg = get_registry()
    before = list(reg._agents.keys())
    yield
    for aid in list(reg._agents.keys()):
        if aid not in before:
            reg._agents.pop(aid, None)


def _hf_train_task(script=_SCRIPT, **overrides):
    """The real task shape a Governor-routed caller must use to reach
    hf_train(): task["type"] drives Governor's capability match, and
    MLOpsAgent.run() separately reads p.get("action") from task.get(
    "params", task) with NO task["type"] fallback (confirmed by a fresh
    read of run()'s dispatch — unlike FinAgentAgent.run(), which does fall
    back to task["type"]). A flat dict carrying both "type" (for Governor)
    and "action" (for MLOpsAgent.run()) is the simplest real shape; nested
    under "params" also works identically since p = task.get("params", task)."""
    task = {
        "type": "hf_train", "action": "hf_train",
        "script": script, "repo_id": "owner/repo",
        "hardware": "a100-large", "timeout": 3600,
    }
    task.update(overrides)
    return task


async def test_4a_governor_exact_match_unapproved_blocked(monkeypatch, clean_registry):
    _patch_council(monkeypatch, "REJECT — refuse")
    hf_calls = _stub_hf_jobs_handler(monkeypatch)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=False)
    agent.health_points = 999999
    get_registry().register(agent)

    gov = Governor()
    result = await gov.dispatch(_hf_train_task())

    assert not hf_calls, f"Governor-routed unapproved hf_train reached submission: {hf_calls}"
    assert result.get("status") != "ok" or result.get("result", {}).get("status") == "blocked"


async def test_4b_governor_exact_match_approved_reaches_submission(monkeypatch, clean_registry):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    hf_calls = _stub_hf_jobs_handler(monkeypatch)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)
    agent.health_points = 999999
    get_registry().register(agent)

    # 2026-09-23: Governor.dispatch() now enforces its own authorization
    # boundary for YELLOW/RED task types -- issue the real receipt.
    from core.loop.permission_gateway import PermissionGateway
    PermissionGateway()._issue_approval_receipt("hf_train", purpose="governor_dispatch")

    gov = Governor()
    result = await gov.dispatch(_hf_train_task())

    assert hf_calls, f"Governor-routed approved hf_train never reached the (mocked) submission, got: {result}"
    assert hf_calls[0]["script"] == _SCRIPT


# ── TEST 5 — LLM-classified / cross-district route ──────────────────────────

def _register_decoy(district: str):
    """A real, non-capable agent registered in `district` — needed because
    Governor.dispatch() only reaches the capable/_llm_classified logic when
    `registry.get_by_district(district)` is non-empty; an empty district
    short-circuits to status="no_agents" BEFORE ever checking `_llm_classified`
    (confirmed by a fresh read of governor.py's dispatch() body)."""
    import uuid
    from core.city.agent_base import AgentBase

    decoy = AgentBase(str(uuid.uuid4()), f"Decoy_{uuid.uuid4().hex[:6]}", district)
    decoy.capabilities = ["unrelated_capability"]
    decoy.health_points = 1
    get_registry().register(decoy)
    return decoy


async def test_5a_llm_classified_cross_district_unapproved_blocked(monkeypatch, clean_registry):
    """Force the REAL Governor LLM-classified whole-city fallback to
    actually be entered: a non-capable decoy occupies "chief_of_staff" (so
    the district isn't empty and the dispatch doesn't short-circuit to
    "no_agents"), MLOpsAgent is registered under a DIFFERENT district it
    would not be guessed into, and the task carries district="chief_of_staff"
    + _llm_classified=True. The exact-match `capable` list in chief_of_staff
    is then empty (decoy doesn't declare hf_train), so Governor's whole-city
    capability search must find MLOpsAgent elsewhere — landing on the SAME
    agent.run() call as the exact-match path (§10/16 of the remediation doc
    explain why a second implementation cannot exist for this to diverge to)."""
    _patch_council(monkeypatch, "REJECT — refuse")
    hf_calls = _stub_hf_jobs_handler(monkeypatch)
    _register_decoy("chief_of_staff")

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=False)
    agent.health_points = 999999
    agent.district = "chief_of_staff_llm_test_double"  # NOT "coding" — forces empty exact-match
    get_registry().register(agent)

    gov = Governor()
    result = await gov.dispatch(_hf_train_task(district="chief_of_staff", _llm_classified=True))

    assert not hf_calls, f"LLM-classified unapproved hf_train reached submission: {hf_calls}"


async def test_5b_llm_classified_cross_district_approved_reaches_submission(monkeypatch, clean_registry):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    hf_calls = _stub_hf_jobs_handler(monkeypatch)
    _register_decoy("chief_of_staff")

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)
    agent.health_points = 999999
    agent.district = "chief_of_staff_llm_test_double"
    get_registry().register(agent)

    from core.loop.permission_gateway import PermissionGateway
    PermissionGateway()._issue_approval_receipt("hf_train", purpose="governor_dispatch")

    gov = Governor()
    result = await gov.dispatch(_hf_train_task(district="chief_of_staff", _llm_classified=True))

    assert hf_calls, f"LLM-classified approved hf_train never reached the (mocked) submission, got: {result}"


# ── TEST 6 — caller-supplied script ─────────────────────────────────────────

async def test_6a_unapproved_script_never_reaches_submission(monkeypatch):
    _patch_council(monkeypatch, "REJECT — refuse")
    hf_calls = _stub_hf_jobs_handler(monkeypatch)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=False)
    malicious_script = "import os; os.system('this would be attacker-controlled')"

    result = await agent.hf_train(script=malicious_script, repo_id="owner/repo")

    assert result["status"] == "blocked"
    assert not any(c.get("script") == malicious_script for c in hf_calls)


async def test_6b_approved_script_passed_through_intact(monkeypatch):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    hf_calls = _stub_hf_jobs_handler(monkeypatch)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)
    exact_script = "# exact script content\nprint('training')\n"

    result = await agent.hf_train(script=exact_script, repo_id="owner/repo")

    assert result["status"] == "ok"
    assert hf_calls[0]["script"] == exact_script


# ── TEST 7 — security-relevant parameters seen by the authorization decision ─

async def test_7_consequential_parameters_visible_to_gate(monkeypatch):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    _stub_hf_jobs_handler(monkeypatch)

    agent = _new_agent(monkeypatch, wait_for_confirmation_result=True)
    gw_calls = _spy_gateway_execute(agent)

    await agent.hf_train(
        script=_SCRIPT, repo_id="owner/repo", hardware="a100-large",
        timeout=7200, requirements=["torch", "transformers"],
    )

    assert len(gw_calls) == 1
    seen = gw_calls[0].params
    assert seen["script"] == _SCRIPT
    assert seen["repo_id"] == "owner/repo"
    assert seen["hardware"] == "a100-large"
    assert seen["timeout"] == 7200
    assert seen["requirements"] == ["torch", "transformers"]
    # Human-readable summary must not just say "run training" — it must
    # surface the actual consequential values.
    assert "a100-large" in seen["summary"]
    assert "7200" in seen["summary"]
    assert "owner/repo" in seen["summary"]


# ── TEST 8 — no self-mint ────────────────────────────────────────────────────

def test_8a_hf_train_source_has_no_self_mint_and_gates_before_submission():
    import inspect

    src = inspect.getsource(MLOpsAgent.hf_train)

    assert "grant_control" not in src, (
        "hf_train() must not mint its own control/capability token — "
        "authorization must come only from PermissionGateway.execute()"
    )
    assert "self._gateway.execute" in src

    gate_idx = src.index("self._gateway.execute")
    approved_check_idx = src.index("if not gate_result.approved")
    run_def_idx = src.index("def _run():")

    assert gate_idx < approved_check_idx < run_def_idx, (
        "the gateway call and its approval check must precede the closure "
        "that performs the real remote submission"
    )


def test_8b_hf_train_is_red_tier():
    from core.config import CONFIG
    assert "hf_train" in CONFIG["permission"]["red"]
    for tier in ("green", "yellow"):
        assert "hf_train" not in CONFIG["permission"][tier]


def test_8c_gateway_unreachable_fails_closed(monkeypatch):
    import asyncio

    hf_calls = _stub_hf_jobs_handler(monkeypatch)
    agent = MLOpsAgent()

    async def _boom(action):
        raise RuntimeError("simulated gateway outage")

    agent._gateway.execute = _boom

    result = asyncio.run(agent.hf_train(script=_SCRIPT, repo_id="owner/repo"))
    assert result["status"] == "blocked"
    assert not hf_calls


# ── No regression to other MLOps capabilities ───────────────────────────────

async def test_9_other_mlops_capabilities_unaffected(monkeypatch):
    """hf_dataset/hf_hub/github_ml/ml_research/ml_plan must remain
    unaffected — this fix must not have broadly disabled MLOpsAgent."""
    agent = MLOpsAgent()
    gw_calls = _spy_gateway_execute(agent)

    def _fake_hub_api(*a, **kw):
        class _Fake:
            def list_repo_files(self, repo_id):
                return ["README.md"]
        return _Fake()

    monkeypatch.setattr("huggingface_hub.HfApi", _fake_hub_api)

    result = await agent.hf_hub(action="list", repo_id="owner/repo")
    assert result["status"] == "ok"
    assert gw_calls == [], "hf_hub() must not be gated by this fix — it is a separate, unmodified capability"


def test_9b_capabilities_unaffected_by_the_fix():
    agent = MLOpsAgent()
    assert set(agent.capabilities) == {"ml_research", "hf_train", "hf_dataset", "hf_hub", "github_ml", "ml_plan"}


if __name__ == "__main__":
    ok = pytest.main([__file__, "-v"]) == 0
    print("PASS test_task58c_mlops_hf_train_permission_remediation" if ok else "FAIL")
    sys.exit(0 if ok else 1)
