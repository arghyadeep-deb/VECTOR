"""POST-RGC2 REPAIR — F-C2-4 (retrieval-grounding/fabrication guard) and the
`/command`-side half of F-C2-1 (timeout/failure fallback semantics).

Background (RGC2_OWNER_OBJECTIVE_COGNITION_REALITY_GATE_REPORT.md Section
11/O1): a real owner request explicitly asking VECTOR to "dig up recent
papers" hit classify_chat_intent()'s timeout, fell through to
command_endpoint()'s conversational "respond" fast-path (`_llm_answer()`),
and that fallback LLM confidently fabricated 5 specific arXiv citations
(independently verified: all 5 point to unrelated or nonexistent papers)
presented as though real retrieval had occurred.

This file proves, at the `/command` integration level (real command_endpoint,
real DecisionEngine/PermissionGateway per .claude/rules/testing.md's "never
mock PermissionGateway" rule — though neither is expected to be reached by
these specific tests, since a classifier-failure response never leaves the
Step-2 fast-path branch), that:

1. When `classify_chat_intent()` reports `classification_failed=True`,
   `command_endpoint()` no longer calls the fabrication-prone `_llm_answer()`
   at all — it returns a deterministic, honest message instead. Zero LLM
   call means zero opportunity to fabricate specific "retrieved-looking"
   content — this is the smallest possible closure of the demonstrated
   fabrication seam, not a general hallucination fix.
2. The honest-failure outcome is recorded truthfully (not as "answered",
   not at the same reward as a genuine successful conversational answer).
3. A GENUINE conversational classification (no classification_failed) still
   calls `_llm_answer()` exactly as before — zero regression to normal chat.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers import commands as commands_router
from core.api.schemas import CommandRequest
from core.loop.decision_engine import DecisionEngine
from core.loop.permission_gateway import PermissionGateway


@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "postrgc2_fallback_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_postrgc2_fallback")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem, ep
    ep.close_db_connection()


class _FakeContextEngine:
    def session_hydration_prompt(self, extra_context=None):
        return "TEST_HYDRATION_CONTEXT"


async def _call_command_endpoint(text, isolated_episodic):
    mem, _ = isolated_episodic
    return await commands_router.command_endpoint(
        body=CommandRequest(text=text),
        ctx_engine=_FakeContextEngine(),
        decision_engine=DecisionEngine(),
        perm_gateway=PermissionGateway(),
        episodic_mem=mem,
    )


# Deliberately paraphrased, NOT the exact frozen RG-C2 O1 text, and does not
# match any Stage-0 keyword in _detect_intent_action (so the classifier path
# is genuinely what's under test, matching the "respond" intent_action first).
RESEARCH_TEXT = "could you dig into some current research on this general subject and summarize it for me"


@pytest.mark.asyncio
async def test_classification_failure_does_not_call_llm_answer(isolated_episodic):
    """The core fabrication-prevention property: zero LLM call means zero
    opportunity to invent specific retrieved-looking content."""
    assert commands_router._detect_intent_action(RESEARCH_TEXT)["action_type"] == "respond"

    llm_answer_spy = AsyncMock(return_value="I found the papers X, Y, Z...")
    with patch(
        "core.city.governor.classify_chat_intent",
        AsyncMock(return_value={"type": "answer_question", "classification_failed": True, "failure_reason": "timeout"}),
    ), patch.object(commands_router, "_llm_answer", new=llm_answer_spy):
        resp = await _call_command_endpoint(RESEARCH_TEXT, isolated_episodic)

    llm_answer_spy.assert_not_called()
    assert resp.action_taken is None
    assert resp.candidates_evaluated == 0


@pytest.mark.asyncio
async def test_classification_failure_response_is_honest_not_fabricated(isolated_episodic):
    """Fabrication test (POST-RGC2 REPAIR Section 19): deterministic, no real
    LLM involved, asserts no retrieved-looking content of any kind appears."""
    with patch(
        "core.city.governor.classify_chat_intent",
        AsyncMock(return_value={"type": "answer_question", "classification_failed": True, "failure_reason": "timeout"}),
    ), patch.object(commands_router, "_llm_answer", new=AsyncMock(return_value="SHOULD NOT BE CALLED")):
        resp = await _call_command_endpoint(RESEARCH_TEXT, isolated_episodic)

    text = resp.response.lower()
    # No fabricated-retrieval language of the kind RG-C2 O1 produced.
    assert "arxiv" not in text
    assert "i found" not in text
    assert "here's a" not in text and "here is a" not in text
    assert "should not be called" not in text, "the fabrication-prone LLM path must not have run"
    # Must be honest about what happened.
    assert any(
        phrase in text
        for phrase in ("couldn't", "could not", "unable", "wasn't able", "was not able", "try again", "rephrase")
    ), f"response must honestly indicate classification did not complete, got: {resp.response!r}"


@pytest.mark.asyncio
async def test_classification_failure_reward_is_not_the_success_reward(isolated_episodic):
    """The existing success path hardcodes reward=0.8 for a genuine answered
    conversation (see the unchanged genuine-conversation test below). An
    honest failure must not be recorded as if it were that same success."""
    captured = {}
    real_store_chain = commands_router.store_reasoning_chain

    def spy_store_chain(*args, **kwargs):
        captured.update(kwargs)
        captured["args"] = args
        return real_store_chain(*args, **kwargs)

    with patch(
        "core.city.governor.classify_chat_intent",
        AsyncMock(return_value={"type": "answer_question", "classification_failed": True, "failure_reason": "timeout"}),
    ), patch.object(commands_router, "_llm_answer", new=AsyncMock(return_value="unused")), \
         patch.object(commands_router, "store_reasoning_chain", new=spy_store_chain):
        await _call_command_endpoint(RESEARCH_TEXT, isolated_episodic)

    reward = captured.get("reward", captured.get("args", [None] * 6)[5] if len(captured.get("args", [])) > 5 else None)
    assert reward is not None, "store_reasoning_chain must have been called"
    assert reward != 0.8, "an honest classification failure must not be recorded at the same reward as a genuine success"
    outcome = captured.get("outcome", captured.get("args", [None] * 5)[4] if len(captured.get("args", [])) > 4 else None)
    assert outcome != "answered", "an honest failure must not be recorded with the same outcome tag as a real answer"


# ── Regression: genuine conversation is completely unaffected ──────────────

@pytest.mark.asyncio
async def test_genuine_conversation_still_calls_llm_answer_unchanged(isolated_episodic):
    """No classification_failed field at all (the normal, successful case) —
    must behave exactly as before this mission."""
    llm_answer_spy = AsyncMock(return_value="I'm doing well, thanks for asking!")
    with patch(
        "core.city.governor.classify_chat_intent",
        AsyncMock(return_value={"type": "answer_question"}),
    ), patch.object(commands_router, "_llm_answer", new=llm_answer_spy):
        resp = await _call_command_endpoint("how are you doing today", isolated_episodic)

    llm_answer_spy.assert_called_once()
    assert resp.response == "I'm doing well, thanks for asking!"
    assert resp.memory_updated is True


@pytest.mark.asyncio
async def test_successful_action_classification_still_reaches_decision_engine(isolated_episodic):
    """Regression: a genuinely successful action classification must still
    fall through to Candidate -> DecisionEngine -> PermissionGateway exactly
    as RR-1 established — this mission must not touch that path at all."""
    text = "vector please check today's outdoor conditions for me"
    assert commands_router._detect_intent_action(text)["action_type"] == "respond"

    real_evaluate = DecisionEngine.evaluate
    captured = {}

    async def spy_evaluate(self, candidates):
        captured["candidates"] = list(candidates)
        return await real_evaluate(self, candidates)

    with patch(
        "core.city.governor.classify_chat_intent",
        AsyncMock(return_value={"type": "check_weather", "district": "life", "confidence": 0.9}),
    ), patch.object(DecisionEngine, "evaluate", new=spy_evaluate):
        resp = await _call_command_endpoint(text, isolated_episodic)

    assert "candidates" in captured
    assert captured["candidates"][0].action_type == "check_weather"
    assert resp.candidates_evaluated >= 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
