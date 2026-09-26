"""V1 contract 11/17 (report truthfully; progress only from real evidence): an approved action whose handler result carries a
failure must not be reported to the owner as done, on ANY owner-facing path (found by the 2026-09-27 V1 reconstruction).

Before: /command checked a status blacklist only, so {"status": "ok", "error": "..."} read as success; /ws/command checked
only "error" and "not_implemented", so {"status": "no_agents"} / "timeout" / "blocked" were success=True and were even
stored in memory as successful. The autonomous executor already refused all of these (tests/backend/test_autonomous_executor.py
pins not_implemented; the literal no_agents case is pinned here too).
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.loop.permission_gateway import GatewayResult
from core.runtime.executor import AutonomousExecutor, result_failure_reason

FAILURES = [
    {"status": "no_agents", "district": "coding"},
    {"status": "timeout"},
    {"status": "blocked"},
    {"status": "ok", "error": "boom"},
    {"status": "success", "error": {"code": 500}},
    {"status": "ok", "success": False},
    {"status": "ok", "ok": False},
    {"status": "ok", "verified": False},
    {"status": "unknown"},
]
SUCCESSES = [
    {"status": "ok", "branch": "main"},
    {"status": "ok", "response": "hello", "error": ""},
    {"status": "success", "error": None},
    {"branch": "main", "commits": [{"sha": "abc"}]},
    {"status": "ok", "success": True, "verified": True},   # a positive flag is not evidence, but it is not a failure either
]


@pytest.mark.parametrize("payload", FAILURES)
def test_failure_payloads_are_recognised(payload):
    assert result_failure_reason(payload) is not None


@pytest.mark.parametrize("payload", SUCCESSES)
def test_real_successes_are_not_flagged(payload):
    assert result_failure_reason(payload) is None


def test_non_dict_payloads_are_not_flagged():
    assert result_failure_reason(None) is None and result_failure_reason("ok") is None


# ── /command ────────────────────────────────────────────────────────────────

def _gw(result, level="GREEN"):
    return GatewayResult(approved=True, level=level, executed=True, result=result, reason="Auto")


@pytest.mark.parametrize("payload", FAILURES)
def test_command_does_not_treat_a_failed_handler_result_as_done(payload):
    from core.api.routers.commands import _build_response_text, _is_not_implemented

    gw = _gw(payload)
    assert _is_not_implemented(gw) is True
    text = _build_response_text(gw, SimpleNamespace(action_type="some_action"), "do it")
    assert "Done" not in text and "completed" not in text.lower().replace("did not complete", "")


def test_command_says_what_failed_for_an_ok_status_with_an_error_field():
    from core.api.routers.commands import _build_response_text

    text = _build_response_text(_gw({"status": "ok", "error": "disk full"}), SimpleNamespace(action_type="write_note"), "x")
    assert "disk full" in text and "won't call it done" in text


@pytest.mark.parametrize("payload", SUCCESSES)
def test_command_still_reports_real_successes(payload):
    from core.api.routers.commands import _is_not_implemented

    assert _is_not_implemented(_gw(payload)) is False


# ── /ws/command ─────────────────────────────────────────────────────────────

def _ws(gateway_payload, intent_type=None):
    from core.api.routers import websocket as ws_module
    from core.api.routers.websocket import WSCommandRequest

    action_type = intent_type or f"test_cmdfail_{uuid.uuid4().hex[:8]}"
    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(return_value={"type": action_type, "district": None})):
        with patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(return_value=_gw(gateway_payload))):
            return asyncio.run(ws_module.ws_command_http(WSCommandRequest(text="do the thing", priority="normal", source="test")))


@pytest.mark.parametrize("payload", FAILURES)
def test_ws_command_reports_failure_not_success(payload):
    if payload.get("status") == "error":
        pytest.skip("covered by the pre-existing error branch")
    resp = _ws(payload)
    assert resp.success is False and resp.error


def test_ws_command_still_reports_a_real_success():
    resp = _ws({"status": "ok", "response": "all good"})
    assert resp.success is True and resp.response == "all good"


def test_ws_conversational_branch_does_not_present_no_agents_as_an_answer():
    from core.api.routers import websocket as ws_module
    from core.api.routers.websocket import WSCommandRequest

    with patch("core.city.governor.classify_chat_intent", new=AsyncMock(return_value={"type": "answer_question", "district": None})):
        with patch("core.city.governor.Governor.dispatch", new=AsyncMock(return_value={"status": "no_agents"})):
            resp = asyncio.run(ws_module.ws_command_http(WSCommandRequest(text="hello", priority="normal", source="test")))
    assert resp.success is False and resp.error == "status:no_agents"


# ── the autonomous executor: the literal no_agents case that had no test ────

class _FakeGateway:
    def __init__(self, result):
        self._r = result

    async def execute(self, *a, **k):
        return self._r


@pytest.mark.parametrize("payload,check", [
    ({"status": "no_agents", "district": "coding"}, "result_status:no_agents"),
    ({"status": "ok", "error": "boom"}, "payload_signal:error_field"),
])
def test_executor_never_verifies_no_agents_or_an_error_payload(payload, check):
    report = asyncio.run(AutonomousExecutor(permission_gateway=_FakeGateway(_gw(payload))).execute("git_status", {}))
    assert report.status == "failed" and report.verification["ok"] is False
    assert check in report.verification["checks"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
