"""
Task 58F — Behavioral tests for the incident-playbook destructive-action
permission remediation (VECTOR_TECHNICAL_KNOWLEDGE/58F_INCIDENT_PLAYBOOK_
DESTRUCTIVE_ACTION_PERMISSION_REMEDIATION.md, closing a Task 59 residual).

Original finding (Task 59 §11, re-traced fresh this task): IncidentPlaybook
Runner._execute_action()'s handler map includes real, destructive OS-level
primitives — block_ip/unblock_ip (real `netsh advfirewall` firewall rule
add/delete) and kill_process (real, UNRESTRICTED `taskkill` by PID or
process name) — reachable with caller/evidence-controlled targets
(params.ip / evidence.target for block_ip/unblock_ip; params.pid,name for
kill_process; evidence.pid for isolate_process, which delegates to
kill_process) and zero PermissionGateway involvement anywhere. Reachable
via Governor's ordinary exact-match capability routing to
IncidentPlaybookRunner ("execute_playbook" is a declared capability), via
a direct execute_playbook()/run() call, and — a finding made fresh this
task, not present in Task 59's own writeup — via districts/security/
siem_pipeline.py's SIEMPipeline.async_process_event(), a fully-built
autonomous SIEM auto-response pipeline (LogAggregator -> DetectionRules ->
IncidentPlaybookRunner.execute_playbook(), triggerable off of any WARNING+
VECTOR log line once wire_loguru_sink()/run_pipeline_loop() are started)
that calls execute_playbook() with zero owner approval. Confirmed DORMANT
this task (SIEMPipeline is not instantiated anywhere in core/ or districts/
outside its own file and tests, and is not in districts/security/__init__
.py's agent-construction map, unlike IncidentPlaybookRunner itself which
IS registered there) — but the capability exists, fully wired, one
bootstrap-registration away from being genuinely autonomous, which is
exactly the class of latent risk this remediation must not depend on
staying dormant.

Fix: three destructive handlers (_action_block_ip, _action_unblock_ip,
_action_kill_process — the last one gates _action_isolate_process too,
since it delegates internally to _action_kill_process) now call a shared
_gate_destructive_action() helper that runs a real PermissionGateway.
execute(Action(action_type=<"block_ip"|"unblock_ip"|"kill_process">, ...))
BEFORE the real subprocess call, and returns an {"status": "error", ...}
dict (matching this file's OWN pre-existing error-status convention, so
execute_playbook()'s existing `result.get("status") == "error"` failure/
rollback detection treats a blocked destructive step as a real failure
with zero change to that pre-existing logic) unless approved. Read-only/
notification steps (log_evidence, notify, capture_process_snapshot,
escalate_to_human, and the currently-stub collect_memory_dump/
run_antivirus) are deliberately left ungated, preserving execute_playbook()
's ability to run fully autonomously for the operations that were never
dangerous — see the remediation doc's Phase 2/Chosen Security Boundary
sections for the full justification.

TEST ISOLATION: the only dangerous OS-level primitive this file's
destructive handlers reach is subprocess.run (netsh / taskkill) — mocked
directly on the incident_playbook_runner module's own subprocess
reference, never via a named wrapper method, per the Task 58A-incident
lesson. Every test uses an isolated tmp_path for the runner's playbooks_dir
/db_path — never the real repo's data/security/ directory. No real firewall
rule is ever added/removed and no real process is ever killed.

No mocking of permission_gateway.py's own gating logic (execute(),
classify(), _handle_red_tier()'s verdict-processing) or of Governor.
dispatch()'s routing logic — per .claude/rules/testing.md's "No Mocking:
permission_gateway.py — test the real gate". Only the external CouncilBrain
LLM dependency and the human Pushover notification/confirmation boundary
are simulated, matching the established pattern from Tasks 57/58A-58G.
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
from districts.security.incident_playbook_runner import IncidentPlaybookRunner
import districts.security.incident_playbook_runner as ipr_mod


# ── Shared helpers ────────────────────────────────────────────────────────

def _patch_council(monkeypatch, verdict_text: str, confidence: float = 0.9):
    """Stub CouncilBrain.deliberate() so _handle_red_tier() runs for real
    without a real Ollama call — same pattern used across Tasks 57/58A-58G."""
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
    """Mock the actual OS-level primitive (subprocess.run) every
    destructive handler uses. Returns the list of every command invoked."""
    calls: list = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        if on_run:
            on_run(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    monkeypatch.setattr(ipr_mod.subprocess, "run", _fake_run)
    return calls


def _new_runner(tmp_path, monkeypatch, *, wait_for_confirmation_result: bool):
    """A fresh IncidentPlaybookRunner repointed at an isolated tmp_path
    (never the real repo's data/security/ directory), with the gateway's
    human-notification boundary stubbed (never mocking the gateway's own
    gating logic)."""
    runner = IncidentPlaybookRunner(
        playbooks_dir=str(tmp_path / "playbooks"),
        db_path=str(tmp_path / "incidents.db"),
    )
    runner._gateway._notify = AsyncMock()
    runner._gateway._wait_for_confirmation = AsyncMock(return_value=wait_for_confirmation_result)
    return runner


def _spy_gateway_execute(runner):
    calls: list = []
    original = runner._gateway.execute

    async def _spy(action):
        calls.append(action)
        return await original(action)

    runner._gateway.execute = _spy
    return calls


def _destructive_playbook(*, action: str, params: dict) -> dict:
    return {
        "id": "test_pb", "name": "Test Playbook",
        "steps": [{"action": action, "params": params, "timeout": 10}],
    }


# ── TEST 1/2 — kill_process blocked / executes after approval ──────────────

async def test_1_kill_process_blocked_without_approval(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "REJECT — refuse")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_subprocess(monkeypatch)

    result = await runner._action_kill_process({"pid": 4242}, {}, "inc1")

    assert result["status"] == "error"
    assert "blocked" in result["message"].lower()
    assert not calls, f"unapproved kill_process reached the real (mocked) taskkill: {calls}"


async def test_2_kill_process_executes_after_approval(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=True)
    calls = _mock_subprocess(monkeypatch)

    result = await runner._action_kill_process({"pid": 4242}, {}, "inc1")

    assert result["status"] == "ok"
    assert result["pid"] == 4242
    assert calls and calls[0][:3] == ["taskkill", "/F", "/PID"]


# ── TEST 3/4 — isolate blocked / executes after approval ───────────────────

async def test_3_isolate_process_blocked_without_approval(monkeypatch, tmp_path):
    """isolate_process delegates to kill_process — must inherit the same
    gate with zero separate wiring."""
    _patch_council(monkeypatch, "REJECT — refuse")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_subprocess(monkeypatch)

    # evidence-controlled pid, exactly Task 59's original concern.
    result = await runner._action_isolate_process({}, {"pid": 9999}, "inc1")

    assert result["status"] == "error"
    assert "blocked" in result["message"].lower()
    assert not calls, f"unapproved isolate_process reached the real (mocked) taskkill: {calls}"


async def test_4_isolate_process_executes_after_approval(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=True)
    calls = _mock_subprocess(monkeypatch)

    result = await runner._action_isolate_process({}, {"pid": 9999}, "inc1")

    assert result["status"] == "ok"
    assert result["pid"] == 9999
    assert calls and str(9999) in calls[0]


# ── TEST 5/6 — unblock_ip blocked / executes after approval ────────────────

async def test_5_unblock_ip_blocked_without_approval(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "REJECT — refuse")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_subprocess(monkeypatch)

    result = await runner._action_unblock_ip({"ip": "10.0.0.5"}, {}, "inc1")

    assert result["status"] == "error"
    assert "blocked" in result["message"].lower()
    assert not calls, f"unapproved unblock_ip reached the real (mocked) netsh: {calls}"


async def test_6_unblock_ip_executes_after_approval(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=True)
    calls = _mock_subprocess(monkeypatch)

    result = await runner._action_unblock_ip({"ip": "10.0.0.5"}, {}, "inc1")

    assert result["status"] == "ok"
    assert result["ip"] == "10.0.0.5"
    assert calls and "delete" in calls[0]


# Also cover block_ip explicitly — a fourth destructive handler discovered
# during Phase 1 tracing (Task 59's own writeup named only kill_process/
# isolate/unblock_ip; block_ip shares the identical evidence-controlled-
# target pattern and real firewall side effect, and this task's own
# instructions say not to assume the named handlers are exhaustive).

async def test_block_ip_blocked_without_approval(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "REJECT — refuse")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_subprocess(monkeypatch)

    result = await runner._action_block_ip({"ip": "203.0.113.9"}, {}, "inc1")
    assert result["status"] == "error"
    assert not calls


async def test_block_ip_executes_after_approval(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=True)
    calls = _mock_subprocess(monkeypatch)

    result = await runner._action_block_ip({"ip": "203.0.113.9"}, {}, "inc1")
    assert result["status"] == "ok"
    assert calls and "add" in calls[0]


# ── TEST 7 — gateway exception fails closed ─────────────────────────────────

async def test_7_gateway_exception_fails_closed(monkeypatch, tmp_path):
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=True)
    calls = _mock_subprocess(monkeypatch)

    async def _boom(action):
        raise RuntimeError("simulated gateway outage")

    monkeypatch.setattr(runner._gateway, "execute", _boom)

    for coro in (
        runner._action_kill_process({"pid": 111}, {}, "inc1"),
        runner._action_block_ip({"ip": "1.2.3.4"}, {}, "inc1"),
        runner._action_unblock_ip({"ip": "1.2.3.4"}, {}, "inc1"),
    ):
        result = await coro
        assert result["status"] == "error"
        assert "unavailable" in result["message"].lower() or "blocked" in result["message"].lower()

    assert not calls


# ── TEST 8 — no self-mint ───────────────────────────────────────────────────

def test_8_no_self_mint_in_any_destructive_handler():
    import inspect

    for fn in (
        IncidentPlaybookRunner._action_kill_process,
        IncidentPlaybookRunner._action_block_ip,
        IncidentPlaybookRunner._action_unblock_ip,
        IncidentPlaybookRunner._gate_destructive_action,
    ):
        src = inspect.getsource(fn)
        assert "grant_control" not in src, f"{fn.__name__} must not self-mint a control token"


# ── TEST 9/10 — caller-controlled PID/IP cannot bypass authorization ───────

async def test_9_caller_controlled_pid_cannot_bypass_authorization(monkeypatch, tmp_path):
    """Whatever PID an attacker/LLM-controlled caller supplies, the gate is
    still consulted and still blocks without approval — the pid value
    itself has no special-case bypass."""
    _patch_council(monkeypatch, "REJECT — refuse")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_subprocess(monkeypatch)
    gw_calls = _spy_gateway_execute(runner)

    for pid in (1, 4, 9999999, -1):
        result = await runner._action_kill_process({"pid": pid}, {}, "inc1")
        assert result["status"] == "error"

    assert not calls
    assert len(gw_calls) == 4 and all(a.action_type == "kill_process" for a in gw_calls)


async def test_10_caller_controlled_ip_cannot_bypass_authorization(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "REJECT — refuse")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_subprocess(monkeypatch)
    gw_calls = _spy_gateway_execute(runner)

    for ip in ("8.8.8.8", "127.0.0.1", "0.0.0.0", "attacker-supplied-string"):
        result = await runner._action_block_ip({"ip": ip}, {}, "inc1")
        assert result["status"] == "error"

    assert not calls
    assert len(gw_calls) == 4 and all(a.action_type == "block_ip" for a in gw_calls)


# ── TEST 11 — arbitrary playbook content cannot bypass authorization ───────

async def test_11_arbitrary_playbook_content_cannot_bypass_authorization(monkeypatch, tmp_path):
    """A fully caller-constructed playbook dict (not one of the packaged
    YAML files) containing a destructive step must still hit the gate when
    run through the real execute_playbook() step loop."""
    _patch_council(monkeypatch, "REJECT — refuse")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_subprocess(monkeypatch)

    malicious_playbook = _destructive_playbook(action="kill_process", params={"pid": 777})
    incident = await runner.execute_playbook(malicious_playbook, {}, "alert1")

    assert not calls, f"arbitrary playbook content reached the real (mocked) taskkill: {calls}"
    assert incident.status == "FAILED"
    assert incident.steps[0]["status"] == "failed"


# ── TEST 12 — direct execute_playbook invocation cannot bypass authorization ─

async def test_12_direct_execute_playbook_call_cannot_bypass_authorization(monkeypatch, tmp_path):
    _patch_council(monkeypatch, "REJECT — refuse")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_subprocess(monkeypatch)

    playbook = _destructive_playbook(action="unblock_ip", params={"ip": "203.0.113.55"})
    incident = await runner.execute_playbook(playbook, {"target": "203.0.113.55"}, "alert1")

    assert not calls
    assert incident.status == "FAILED"


async def test_12b_run_dispatch_reaches_same_boundary(monkeypatch, tmp_path):
    """A second, non-Governor entry point — run({"type": "execute_playbook",
    ...}) — must funnel through the identical gate."""
    _patch_council(monkeypatch, "REJECT — refuse")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    calls = _mock_subprocess(monkeypatch)
    runner._playbooks["danger"] = _destructive_playbook(action="kill_process", params={"pid": 555})

    result = await runner.run({"type": "execute_playbook", "params": {"playbook_id": "danger", "evidence": {}}})

    assert result["status"] == "ok"  # run()'s own wrapper always says "ok"; the incident inside failed
    assert result["incident"]["status"] == "FAILED"
    assert not calls


# ── TEST 13 — Governor route and direct route converge on the same boundary ─

@pytest.fixture
def clean_registry():
    reg = get_registry()
    before = list(reg._agents.keys())
    yield
    for aid in list(reg._agents.keys()):
        if aid not in before:
            reg._agents.pop(aid, None)


async def test_13a_governor_dispatch_unapproved_destructive_playbook_blocked(monkeypatch, tmp_path, clean_registry):
    _patch_council(monkeypatch, "REJECT — refuse")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    runner.health_points = 999999
    calls = _mock_subprocess(monkeypatch)
    runner._playbooks["danger"] = _destructive_playbook(action="kill_process", params={"pid": 333})
    get_registry().register(runner)

    gov = Governor()
    result = await gov.dispatch({
        "type": "execute_playbook", "district": "security",
        "params": {"playbook_id": "danger", "evidence": {}},
    })

    assert not calls, f"Governor-routed unapproved destructive playbook reached real subprocess: {calls}"


async def test_13b_governor_dispatch_approved_destructive_playbook_reaches_mocked_side_effect(monkeypatch, tmp_path, clean_registry):
    _patch_council(monkeypatch, "DEFER — ask the owner")
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=True)
    runner.health_points = 999999
    calls = _mock_subprocess(monkeypatch)
    runner._playbooks["danger"] = _destructive_playbook(action="kill_process", params={"pid": 333})
    get_registry().register(runner)

    gov = Governor()
    result = await gov.dispatch({
        "type": "execute_playbook", "district": "security",
        "params": {"playbook_id": "danger", "evidence": {}},
    })

    assert calls, f"Governor-routed approved destructive playbook never reached the mocked subprocess, got: {result}"


# ── TEST 14 — harmless/read-only playbook operations continue to work ──────

async def test_14_harmless_operations_unaffected(monkeypatch, tmp_path):
    """log_evidence, notify, capture_process_snapshot, escalate_to_human
    must all continue to run WITHOUT any gateway involvement — only the
    destructive handlers require approval."""
    runner = _new_runner(tmp_path, monkeypatch, wait_for_confirmation_result=False)
    gw_calls = _spy_gateway_execute(runner)
    calls = _mock_subprocess(monkeypatch)

    playbook = {
        "id": "harmless", "name": "Harmless Playbook",
        "steps": [
            {"action": "log_evidence", "params": {}},
            {"action": "notify", "params": {"message": "test"}},
            {"action": "capture_process_snapshot", "params": {}},
            {"action": "escalate_to_human", "params": {"message": "please look at this"}},
        ],
    }
    incident = await runner.execute_playbook(playbook, {"note": "benign"}, "alert1")

    assert incident.status == "COMPLETED"
    assert all(s["status"] == "completed" for s in incident.steps)
    assert not gw_calls, "harmless read-only/notification steps must never touch the gateway"


# ── TEST 15 — SIEM pipeline reachability / dormancy check ──────────────────

def test_15_siem_pipeline_not_bootstrapped_but_would_inherit_the_gate_if_it_were():
    """SIEMPipeline.async_process_event() -> execute_playbook() is a
    fully-built autonomous path this task found while tracing every
    caller (Phase 1). Confirms it is not currently registered/bootstrapped
    (so not independently Governor-reachable today), and — the security-
    relevant half of this test — that it calls the exact same execute_
    playbook() method already proven gated above, so it inherits the fix
    automatically the moment it is ever wired in."""
    import districts.security as security_district
    import inspect
    from districts.security.siem_pipeline import SIEMPipeline

    agent_map = getattr(security_district, "_AGENT_CLASSES", None) or getattr(security_district, "AGENT_CLASSES", None)
    if agent_map is None:
        # Fall back to scanning the module source for the bootstrap dict
        # literal if the district doesn't expose it as a named attribute.
        src = inspect.getsource(security_district)
        assert '"SIEMPipeline"' not in src, (
            "SIEMPipeline appears to now be bootstrapped — re-verify its "
            "reachability and update this test/finding accordingly"
        )
    else:
        assert "SIEMPipeline" not in agent_map

    siem_src = inspect.getsource(SIEMPipeline.async_process_event)
    assert "execute_playbook" in siem_src


if __name__ == "__main__":
    ok = pytest.main([__file__, "-v"]) == 0
    print("PASS test_task58f_incident_playbook_destructive_action_permission_remediation" if ok else "FAIL")
    sys.exit(0 if ok else 1)
