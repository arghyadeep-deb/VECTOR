"""Episodic adaptation log — situation_hash + policy_score closure.

Verifies `core/api/routers/commands.py`'s Step 8 `episodic_mem.store()` call
now includes, alongside the pre-existing context fields (winner_score,
candidates_count, gateway_level, chain_id, identity_trace, authorized_task_
type, executed_task_type), the exact same canonical `situation_hash`
computed at Step 6 (`PolicyMemory.make_situation_hash(action_type, params)`)
and the real `decision.winner.policy_score` DecisionEngine reads from
PolicyMemory and blends into `total_score` (see
`DecisionEngine._score_candidate()`).

This lets a live before/after PolicyMemory adaptation check be read directly
from two /command episodic records for the same situation, with no direct
PolicyMemory query needed — proven below by driving the real /command
pipeline twice (git_status-shaped, identical candidate identity both times)
and comparing only the two captured `context` dicts.

Uses an isolated temp SQLite DB (same pattern as
tests/test_postrgc2_situation_hash_identity.py) — never the production DB.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers import commands as commands_router
from core.api.schemas import CommandRequest
from core.loop.decision_engine import DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.memory.policy import PolicyMemory


@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "adaptation_log_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_adaptation_log")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem, ep
    ep.close_db_connection()


class _FakeContextEngine:
    def session_hydration_prompt(self, extra_context=None):
        return "TEST_HYDRATION_CONTEXT"


_GIT_STATUS_RESULT = {
    "status": "ok", "branch": "main", "modified": [], "staged": [],
    "untracked": [], "ahead": 0, "behind": 0,
}


async def _call_command_endpoint_once(text, mem):
    """Drives the real /command pipeline for a fixed git_status Candidate
    (same action_type + params both times this is called), capturing the
    exact `context` dict passed to episodic_mem.store()'s Step 8 call."""
    captured = []
    real_store = mem.store

    def _spy_store(*args, **kwargs):
        captured.append(kwargs.get("context"))
        return real_store(*args, **kwargs)

    spy = MagicMock(side_effect=_spy_store)

    with patch.object(
        commands_router, "_detect_intent_action",
        return_value={"action_type": "git_status", "params": {}},
    ), patch(
        "core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
            return_value=type("R", (), {
                "approved": True, "level": "GREEN", "executed": True,
                "result": dict(_GIT_STATUS_RESULT), "reason": "test",
            })()
        )
    ):
        mem.store = spy
        try:
            await commands_router.command_endpoint(
                body=CommandRequest(text=text),
                ctx_engine=_FakeContextEngine(),
                decision_engine=DecisionEngine(),
                perm_gateway=PermissionGateway(),
                episodic_mem=mem,
            )
        finally:
            mem.store = real_store

    # Step 8's context is the LAST store() call this run made for
    # event_type="api_command" (DecisionEngine.evaluate() also calls
    # mem.store() for its own decision_candidate logging beforehand).
    step8_contexts = [c for c in captured if c is not None and "situation_hash" in c]
    assert len(step8_contexts) == 1, "expected exactly one Step 8 episodic_mem.store() call with situation_hash"
    return step8_contexts[0]


@pytest.mark.asyncio
async def test_step8_context_contains_situation_hash_and_policy_score(isolated_episodic):
    mem, _ = isolated_episodic
    text = "what's my git status"

    ctx1 = await _call_command_endpoint_once(text, mem)
    ctx2 = await _call_command_endpoint_once(text, mem)

    expected_hash = PolicyMemory.make_situation_hash("git_status", {})

    # Both records carry the same canonical situation_hash.
    assert ctx1["situation_hash"] == expected_hash
    assert ctx2["situation_hash"] == expected_hash

    # Both records carry a real, numeric policy_score.
    assert isinstance(ctx1["policy_score"], float)
    assert isinstance(ctx2["policy_score"], float)

    # First call: no prior PolicyMemory row for this situation -> DEFAULT_SCORE.
    assert ctx1["policy_score"] == pytest.approx(PolicyMemory.DEFAULT_SCORE)

    # Second call: the first call's own Step 6 update_from_outcome() write
    # (GREEN-approved git_status, real branch data -> reward=0.8) has already
    # landed under this exact situation_hash by the time the second call's
    # Step 4 evaluate() reads policy_score -- so it must differ from the
    # first call's, readable purely from these two stored dicts.
    assert ctx2["policy_score"] != ctx1["policy_score"]
    assert ctx2["policy_score"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_step8_context_preserves_all_previously_present_fields(isolated_episodic):
    mem, _ = isolated_episodic
    ctx = await _call_command_endpoint_once("what's my git status", mem)

    for key in (
        "user_text", "winner_score", "candidates_count", "gateway_level",
        "chain_id", "authorized_task_type", "executed_task_type",
    ):
        assert key in ctx, f"pre-existing context key '{key}' must remain present"

    assert ctx["authorized_task_type"] == "git_status"
    assert ctx["gateway_level"] == "GREEN"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
