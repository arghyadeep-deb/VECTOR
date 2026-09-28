"""Honest reward for GREEN git_status/recent_commits actions whose real
handler ran but returned no usable data.

Root cause (verified): permission_gateway.py's `_execute_action()` for
`_OWNER_READONLY_DISPATCH_ACTION_TYPES` does
`result['status'] = dispatch_result.get('status', 'ok')` after
`Governor().dispatch()` runs `GitBot.run()`, which returns
`get_status()`/`get_recent_commits()`'s raw dict with NO 'status' key on
either success or internal failure — so a genuine failure (empty dict / empty
commits list) silently defaults to `status='ok'`, which
`commands._is_not_implemented()` (only checks for `not_implemented`/
`rejected`) never catches. `commands.py`'s reward computation must instead
read the same real fields (`branch`/`commits`) that
`_render_readonly_evidence()` already uses to report this honestly to the
user.

Per .claude/rules/testing.md only external boundaries are mocked (the LLM
classifier, `PermissionGateway.execute` itself) — `command_endpoint` runs as
real production code end to end.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers import commands as commands_router
from core.api.schemas import CommandRequest
from core.city.intent_matcher import IntentMatcher
from core.loop.decision_engine import DecisionEngine
from core.loop.permission_gateway import GatewayResult


@pytest.fixture(autouse=True)
def _no_embedding_match():
    with patch.object(IntentMatcher, "match", new=AsyncMock(return_value=None)):
        yield


class _FakeContextEngine:
    def session_hydration_prompt(self, extra_context=None):
        return "TEST_HYDRATION_CONTEXT"


class _FakeCompletionResult:
    def __init__(self, content: str):
        self.content = content


def _mock_client(content: str):
    async def _chat(*args, **kwargs):
        return _FakeCompletionResult(content)
    fake = AsyncMock()
    fake.chat = _chat
    return fake


def _llm(task_type: str, district: str, confidence: float = 0.95) -> str:
    return (
        '{"is_action": true, "task_type": "%s", "district": "%s", "confidence": %s}'
        % (task_type, district, confidence)
    )


@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "reward_honesty_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_reward_honesty")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem
    ep.close_db_connection()


async def _run_endpoint(text, llm_json, isolated_episodic, gateway_result: GatewayResult):
    """Drives the real command_endpoint end to end, mocking only the LLM
    classifier and PermissionGateway.execute() (the district-handler
    boundary) — everything else (DecisionEngine, reward computation) is real
    production code."""
    policy_calls = []
    fake_gateway = MagicMock()
    fake_gateway.execute = AsyncMock(return_value=gateway_result)
    with patch("core.inference.provider_client.get_client", return_value=_mock_client(llm_json)), \
         patch.object(commands_router, "update_policy", side_effect=lambda a, h, r: policy_calls.append((a, r))):
        response = await commands_router.command_endpoint(
            body=CommandRequest(text=text),
            ctx_engine=_FakeContextEngine(),
            decision_engine=DecisionEngine(),
            perm_gateway=fake_gateway,
            episodic_mem=isolated_episodic,
        )
    return response, policy_calls


# ── git_status: real data still earns 0.8, empty result earns 0.2 ─────────

@pytest.mark.asyncio
async def test_git_status_with_real_branch_still_rewards_08(isolated_episodic):
    gw_result = GatewayResult(
        approved=True, level="GREEN", executed=True,
        result={"status": "ok", "branch": "main", "modified": [], "staged": [], "untracked": []},
        reason="Auto-executed",
    )
    _, policy_calls = await _run_endpoint(
        "how does the working tree look right now", _llm("git_status", "coding"), isolated_episodic, gw_result
    )
    assert policy_calls and policy_calls[0][1] == 0.8, policy_calls


@pytest.mark.asyncio
async def test_git_status_with_no_branch_rewards_02(isolated_episodic):
    """GitBot.get_status() returned {} on an internal exception; the gateway
    defaulted status to 'ok' with no 'branch' key — a real failure, not a
    success, matching _render_readonly_evidence's own honest message."""
    gw_result = GatewayResult(
        approved=True, level="GREEN", executed=True,
        result={"status": "ok"},
        reason="Auto-executed",
    )
    _, policy_calls = await _run_endpoint(
        "how does the working tree look right now", _llm("git_status", "coding"), isolated_episodic, gw_result
    )
    assert policy_calls and policy_calls[0][1] == 0.2, policy_calls


# ── recent_commits: real data still earns 0.8, empty result earns 0.2 ─────

@pytest.mark.asyncio
async def test_recent_commits_with_commits_still_rewards_08(isolated_episodic):
    gw_result = GatewayResult(
        approved=True, level="GREEN", executed=True,
        result={"status": "ok", "commits": [
            {"hash": "abc1234", "message": "fix", "author": "A", "date": "2026-09-20"}
        ]},
        reason="Auto-executed",
    )
    _, policy_calls = await _run_endpoint(
        "anything new in the codebase lately", _llm("recent_commits", "coding"), isolated_episodic, gw_result
    )
    assert policy_calls and policy_calls[0][1] == 0.8, policy_calls


@pytest.mark.asyncio
async def test_recent_commits_with_empty_commits_rewards_02(isolated_episodic):
    """GitBot.get_recent_commits() returned [] on an internal exception; the
    gateway defaulted status to 'ok' with an empty commits list — a real
    failure, not a success."""
    gw_result = GatewayResult(
        approved=True, level="GREEN", executed=True,
        result={"status": "ok", "commits": []},
        reason="Auto-executed",
    )
    _, policy_calls = await _run_endpoint(
        "anything new in the codebase lately", _llm("recent_commits", "coding"), isolated_episodic, gw_result
    )
    assert policy_calls and policy_calls[0][1] == 0.2, policy_calls


@pytest.mark.asyncio
async def test_recent_commits_with_missing_commits_key_rewards_02(isolated_episodic):
    gw_result = GatewayResult(
        approved=True, level="GREEN", executed=True,
        result={"status": "ok"},
        reason="Auto-executed",
    )
    _, policy_calls = await _run_endpoint(
        "anything new in the codebase lately", _llm("recent_commits", "coding"), isolated_episodic, gw_result
    )
    assert policy_calls and policy_calls[0][1] == 0.2, policy_calls


# ── Regression: not_implemented / rejected still earn 0.2 exactly as before ─

@pytest.mark.asyncio
async def test_not_implemented_git_status_still_rewards_02(isolated_episodic):
    gw_result = GatewayResult(
        approved=True, level="GREEN", executed=True,
        result={"status": "not_implemented", "action": "git_status"},
        reason="Auto-executed",
    )
    _, policy_calls = await _run_endpoint(
        "how does the working tree look right now", _llm("git_status", "coding"), isolated_episodic, gw_result
    )
    assert policy_calls and policy_calls[0][1] == 0.2, policy_calls


@pytest.mark.asyncio
async def test_rejected_unrelated_action_still_rewards_02(isolated_episodic):
    """Regression: a `rejected` handler result for a non-git action_type must
    still earn 0.2 — untouched by the new git-specific check."""
    gw_result = GatewayResult(
        approved=True, level="RED", executed=True,
        result={"status": "rejected", "reason": "no code provided", "action": "execute_code"},
        reason="Auto-executed",
    )
    _, policy_calls = await _run_endpoint(
        "Execute that script and run it now.", _llm("execute_code", "ops", 1.0), isolated_episodic, gw_result
    )
    assert policy_calls and policy_calls[0][1] == 0.2, policy_calls


@pytest.mark.asyncio
async def test_agent_authored_success_status_still_rewards_08(isolated_episodic):
    """2026-09-23 regression test: many real district agents (districts/
    agency/client_manager.py, districts/calls/*, districts/content/*,
    districts/investment/*, ~100+ call sites) use "success", not "ok", as
    their own native status -- Governor.dispatch() passes it through
    unmodified on a real success. A prior fix briefly whitelisted only
    {"ok", "executed"}, which would have wrongly scored this 0.2."""
    gw_result = GatewayResult(
        approved=True, level="GREEN", executed=True,
        result={"status": "success", "client": "acme"},
        reason="Auto-executed",
    )
    _, policy_calls = await _run_endpoint(
        "add a new client called acme", _llm("hand_content", "agency"), isolated_episodic, gw_result
    )
    assert policy_calls and policy_calls[0][1] == 0.8, policy_calls


# ── Regression: every other action_type is byte-for-byte unaffected ───────

@pytest.mark.asyncio
async def test_unrelated_action_with_no_branch_like_result_still_rewards_08(isolated_episodic):
    """A non-git action_type approved with a result dict that happens to lack
    a 'branch'/'commits' key must NOT be penalized — the new check is scoped
    to git_status/check_git/git_log/recent_commits only."""
    gw_result = GatewayResult(
        approved=True, level="GREEN", executed=True,
        result={"status": "ok"},
        reason="Auto-executed",
    )
    _, policy_calls = await _run_endpoint(
        "check the weather please", _llm("check_weather", "ops"), isolated_episodic, gw_result
    )
    assert policy_calls and policy_calls[0][1] == 0.8, policy_calls


# ── Direct unit coverage of the new helper ─────────────────────────────────

def test_is_git_readonly_empty_helper_scoping():
    _GatewayResult = GatewayResult
    ok_status = _GatewayResult(True, "GREEN", True, {"status": "ok", "branch": "main"}, "r")
    empty_status = _GatewayResult(True, "GREEN", True, {"status": "ok"}, "r")
    ok_commits = _GatewayResult(True, "GREEN", True, {"status": "ok", "commits": [{"hash": "a"}]}, "r")
    empty_commits = _GatewayResult(True, "GREEN", True, {"status": "ok", "commits": []}, "r")

    assert commands_router._is_git_readonly_empty("git_status", ok_status) is False
    assert commands_router._is_git_readonly_empty("check_git", empty_status) is True
    assert commands_router._is_git_readonly_empty("git_log", ok_commits) is False
    assert commands_router._is_git_readonly_empty("recent_commits", empty_commits) is True
    # Not one of the four scoped action_types — never flagged, regardless of shape.
    assert commands_router._is_git_readonly_empty("launch_app", empty_status) is False
    assert commands_router._is_git_readonly_empty("play_music", empty_commits) is False
