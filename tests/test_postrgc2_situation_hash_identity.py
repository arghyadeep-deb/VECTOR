"""POST-RGC2 REPAIR — F-C2-2 (situation-hash identity) regression tests.

Background (RGC2_OWNER_OBJECTIVE_COGNITION_REALITY_GATE_REPORT.md Section
25): `core/api/routers/commands.py` used its own local, non-canonical
`_make_situation_hash(params)` (MD5, params-only, 12-char) for its Step 6
PolicyMemory write and its /command/feedback endpoint, completely different
from `PolicyMemory.make_situation_hash(action_type, params)` (the canonical
`"v2:"`-prefixed SHA-256 identity `DecisionEngine`'s own `_score_candidate()`
reads via `get_score()`). Confirmed live: a real `check_attendance` reward
(0.8, 13 samples) was durably persisted but under a hash DecisionEngine's own
canonical reader could never address — the learning signal was orphaned, not
lost.

This file proves:
1. The local, non-canonical helper is gone (source-level guard).
2. `/command`'s Step 6 write now uses the canonical
   `PolicyMemory.make_situation_hash(action_type, params)` identity.
3. The full closed loop specified in POST-RGC2 REPAIR Section 10: a real
   Candidate(action_type=A, params=P) executed through `/command` writes a
   PolicyMemory row under canonical hash H; a LATER, fresh
   `DecisionEngine.evaluate()` call for the same (A, P) genuinely reads back
   the UPDATED value from that same H (not the DEFAULT_SCORE) — proven by
   comparing real `_score_candidate()`/`get_score()` output before and after,
   never by comparing two helper-function return strings in isolation.
4. Different action_type + same params -> different identity.
5. Same action_type + meaningfully different params -> different identity.
6. `/command/feedback` also uses canonical identity semantics when no
   explicit situation_hash is supplied by the caller.

Uses an isolated temp SQLite DB (same pattern as
tests/test_rr1_command_integration.py) — never the production DB — to avoid
any cross-contamination with real PolicyMemory history, per the mission's
"use synthetic action names/state if necessary" instruction.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers import commands as commands_router
from core.api.schemas import CommandRequest
from core.loop.decision_engine import Candidate, DecisionEngine
from core.loop.permission_gateway import PermissionGateway
from core.memory.policy import PolicyMemory


@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "postrgc2_hash_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_postrgc2_hash")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem, ep
    ep.close_db_connection()


class _FakeContextEngine:
    def session_hydration_prompt(self, extra_context=None):
        return "TEST_HYDRATION_CONTEXT"


async def _call_command_endpoint(text, isolated_episodic, gov_intent):
    mem, _ = isolated_episodic
    with patch(
        "core.city.governor.classify_chat_intent",
        AsyncMock(return_value=gov_intent),
    ), patch("core.loop.permission_gateway.PermissionGateway.execute", new=AsyncMock(
        return_value=type("R", (), {"approved": True, "level": "GREEN", "executed": True,
                                     "result": {"status": "ok"}, "reason": "test"})()
    )):
        return await commands_router.command_endpoint(
            body=CommandRequest(text=text),
            ctx_engine=_FakeContextEngine(),
            decision_engine=DecisionEngine(),
            perm_gateway=PermissionGateway(),
            episodic_mem=mem,
        )


# ── 1. Local non-canonical helper must be gone ──────────────────────────────

def test_local_situation_hash_helper_removed():
    assert not hasattr(commands_router, "_make_situation_hash"), (
        "commands.py's own local, non-canonical _make_situation_hash(params) "
        "(MD5, params-only) must be removed entirely — PolicyMemory."
        "make_situation_hash(action_type, params) is the single canonical "
        "identity function"
    )


def test_command_endpoint_uses_canonical_hash_source():
    import inspect
    src = inspect.getsource(commands_router.command_endpoint)
    assert "PolicyMemory.make_situation_hash(" in src, (
        "Step 6's PolicyMemory write must compute its situation_hash via "
        "the canonical PolicyMemory.make_situation_hash(action_type, params), "
        "not a local duplicate"
    )


# ── 2. Closed-loop write -> later-read proof (Section 10) ───────────────────

@pytest.mark.asyncio
async def test_closed_loop_write_then_later_read(isolated_episodic):
    """The exact loop POST-RGC2 REPAIR Section 10 requires: execute a real
    action through /command, then independently verify DecisionEngine's own
    canonical read path sees the updated value under the SAME identity — not
    by comparing hash strings, by comparing real get_score() output."""
    action_type = "postrgc2_synth_action_a"
    params = {"query": "synthetic closed-loop probe"}

    canonical_hash = PolicyMemory.make_situation_hash(action_type, params)
    pm = PolicyMemory()
    before = pm.get_score(action_type, canonical_hash)
    assert before == PolicyMemory.DEFAULT_SCORE, "must start at the default score (fresh synthetic action_type)"

    gov_intent = {"type": action_type, "district": "research", "confidence": 0.95}

    # Drive the real /command pipeline: classify -> Candidate(action_type, params)
    # -> DecisionEngine.evaluate() -> PermissionGateway.execute() (mocked GREEN
    # approval only — DecisionEngine itself is fully real) -> Step 6 write.
    text = f"please handle this: {params['query']}"
    with patch.object(commands_router, "_detect_intent_action", return_value={"action_type": "respond", "params": {}}):
        resp = await _call_command_endpoint(text, isolated_episodic, gov_intent)

    # The real winner's params include "query"/"content"/"source" (and
    # district) per command_endpoint's own intent_action construction (see
    # Step 2) -- so the ACTUAL params written differ from the bare `params`
    # dict above. Recompute the real hash from the real winner to prove the
    # write landed under whatever PolicyMemory.make_situation_hash() the
    # production code itself derives -- and then prove a fresh evaluate()
    # for that exact (action_type, real_params) reads the updated value.
    real_params = {
        "query": text, "content": text, "source": "api_command", "district": "research",
    }
    real_hash = PolicyMemory.make_situation_hash(action_type, real_params)
    after = pm.get_score(action_type, real_hash)
    assert after != PolicyMemory.DEFAULT_SCORE, (
        "the real /command execution must have written a real PolicyMemory "
        "row under the canonical hash for the REAL (action_type, params) "
        "pair DecisionEngine actually scored"
    )

    # Now prove a fresh, later DecisionEngine.evaluate() call for the exact
    # same (action_type, params) reads this updated value as its policy_score
    # factor -- not merely that get_score() alone returns it.
    engine = DecisionEngine()
    later_candidate = Candidate(action_type=action_type, params=real_params, goal_ids=[])
    decision = await engine.evaluate([later_candidate])
    scored = decision.all_candidates[0]
    assert scored.policy_score == pytest.approx(after), (
        "a LATER DecisionEngine.evaluate() call for the identical "
        "(action_type, params) must read back the exact value /command's "
        "own Step 6 write persisted -- proving the write/read identity loop "
        "is genuinely closed, not merely that two hash strings match"
    )


# ── 3. Identity differentiation ─────────────────────────────────────────────

def test_different_action_type_same_params_differ():
    params = {"query": "same params"}
    h1 = PolicyMemory.make_situation_hash("postrgc2_synth_action_x", params)
    h2 = PolicyMemory.make_situation_hash("postrgc2_synth_action_y", params)
    assert h1 != h2


def test_same_action_type_different_params_differ():
    action_type = "postrgc2_synth_action_z"
    h1 = PolicyMemory.make_situation_hash(action_type, {"query": "alpha"})
    h2 = PolicyMemory.make_situation_hash(action_type, {"query": "beta"})
    assert h1 != h2


# ── 4. Feedback endpoint uses canonical identity when hash not supplied ────

@pytest.mark.asyncio
async def test_feedback_endpoint_uses_canonical_identity_when_hash_omitted(isolated_episodic):
    mem, _ = isolated_episodic
    action_type = "postrgc2_synth_feedback_action"
    body = {"action_type": action_type, "rating": 5, "note": "great"}
    await commands_router.feedback_endpoint(body, episodic_mem=mem)

    expected_hash = PolicyMemory.make_situation_hash(action_type, {})
    pm = PolicyMemory()
    score = pm.get_score(action_type, expected_hash)
    assert score == pytest.approx(1.0), (
        "feedback_endpoint's fallback hash (when the caller supplies no "
        "explicit situation_hash) must use PolicyMemory.make_situation_hash"
        "(action_type, {}) -- the same canonical function, not a separate "
        "non-canonical shape -- so the write is at least self-consistently "
        "addressable going forward"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
