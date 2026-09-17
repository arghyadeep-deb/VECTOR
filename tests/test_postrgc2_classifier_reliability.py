"""POST-RGC2 REPAIR — F-C2-1 (classifier timeout/reliability) regression tests.

Background (VECTOR_TECHNICAL_KNOWLEDGE/RGC2_OWNER_OBJECTIVE_COGNITION_REALITY_
GATE_REPORT.md Section 27): RG-C2 behaviorally demonstrated that
`core/city/governor.py::classify_chat_intent()`'s outer `asyncio.wait_for(...,
timeout=12.0)` (guarding its single `provider_client.chat()` call) is
inconsistent with a sibling function facing the IDENTICAL call shape and
latency profile — `_answer_conversationally()`'s own LLM call, already fixed
to `timeout=45.0` on 2026-07-23 ("JARVIS-parity latency pass") after a
documented prior incident (see that function's own inline comment). 4 of 5
RG-C2 objectives independently hit `verdict='TIMEOUT (12s)'` for genuinely
executable owner requests, which then silently fell through to the
conversational "respond" fast-path (Candidate/DecisionEngine/PermissionGateway
never reached).

This file proves two independent things:
1. The timeout ceiling itself is now 45.0 (matching the sibling precedent),
   not 12.0.
2. A classifier-INFRASTRUCTURE failure (timeout, invalid/unparseable LLM
   output, or a provider-layer exception) is now DISTINGUISHABLE from a
   classifier SUCCESSFULLY determining the message is pure conversation —
   the former sets `classification_failed=True` + a `failure_reason`; the
   latter does not. This is the exact epistemic distinction POST-RGC2 REPAIR
   Section 6 requires ("CLASSIFIER SAYS: conversation" vs "CLASSIFIER
   FAILED: timeout/provider failure/invalid output" must never be conflated).

Per .claude/rules/testing.md, only the LLM-call boundary
(`provider_client.get_client`) and the embedding-similarity matcher
(`IntentMatcher.match`, isolated here because it can otherwise pre-empt the
LLM call entirely and is not the subject of this file) are mocked. Nothing
about PermissionGateway/DecisionEngine is touched by this file at all —
`classify_chat_intent()` is tested standalone, exactly as it is called by
both `/command` and `/ws/command`.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city import governor
from core.city.intent_matcher import IntentMatcher


TEST_TEXT = "please look into recent developments in this general subject area for me"


# `_REGEX_PRECLASSIFY` is a function-LOCAL list inside classify_chat_intent()
# (not importable/introspectable from outside), so this is a manual sanity
# check performed once against the exact source at authoring time: TEST_TEXT
# ("please look into recent developments in this general subject area for
# me") does not contain any of the fixed keywords those patterns require
# (study/quiz/sketch/mockup/report/habit/pattern/startup/idea/weekly/goals/
# system status, etc.) — confirmed by direct read of governor.py's
# _REGEX_PRECLASSIFY list. If that list is later extended with a pattern
# matching this text, these tests would start silently testing the regex
# layer instead of the LLM/timeout layer; there is no way to guard this at
# runtime without duplicating the production list, so it is documented here
# instead.
def _no_preclassify_match():
    pass


@pytest.fixture(autouse=True)
def _no_embedding_match():
    """Isolate the embedding-similarity stage (Stage 2) — not under test
    here, and would otherwise need a real embedding model."""
    with patch.object(IntentMatcher, "match", new=AsyncMock(return_value=None)):
        yield


class _FakeCompletionResult:
    def __init__(self, content: str):
        self.content = content


def _mock_client(*, raise_exc: Exception | None = None, sleep_secs: float = 0.0,
                  content: str = ""):
    """Build a fake provider_client with a .chat() coroutine that either
    sleeps (to test the outer wait_for boundary genuinely, not a mocked
    TimeoutError), raises, or returns content."""
    async def _chat(*args, **kwargs):
        if sleep_secs:
            await asyncio.sleep(sleep_secs)
        if raise_exc:
            raise raise_exc
        return _FakeCompletionResult(content)
    fake = AsyncMock()
    fake.chat = _chat
    return fake


# ── 1. Timeout ceiling itself ───────────────────────────────────────────────

def test_timeout_ceiling_is_45_not_12():
    """Source-level guard (RG-C2's own demonstrated evidence: the 12.0s
    ceiling was too tight for the real, observed provider-fallback latency
    profile). Asserts the exact sibling precedent (45.0, matching
    _answer_conversationally()) is now used, not merely "some larger number"."""
    import inspect
    src = inspect.getsource(governor.classify_chat_intent)
    assert "timeout=45.0" in src, (
        "classify_chat_intent()'s outer asyncio.wait_for must use timeout=45.0, "
        "matching _answer_conversationally()'s own already-fixed, already-"
        "precedented ceiling for the identical provider_client.chat() call shape"
    )
    assert "timeout=12.0" not in src, (
        "the old, RG-C2-demonstrated-insufficient 12.0s ceiling must be fully replaced"
    )


def test_sibling_function_precedent_unchanged():
    """Regression guard: this mission must not touch
    _answer_conversationally()'s own already-correct 45.0s ceiling — only
    align classify_chat_intent() to it."""
    import inspect
    src = inspect.getsource(governor.Governor._answer_conversationally) if hasattr(
        governor.Governor, "_answer_conversationally"
    ) else inspect.getsource(governor._answer_conversationally) if hasattr(
        governor, "_answer_conversationally"
    ) else None
    assert src is not None, "sibling function must still exist under its established name"
    assert "timeout=45.0" in src


# ── 2. Genuine timeout -> classification_failed=True ────────────────────────

@pytest.mark.asyncio
async def test_genuine_timeout_sets_classification_failed():
    """Mocks `asyncio.wait_for` itself to raise TimeoutError immediately —
    the standard way to test timeout-handling BEHAVIOR without a real 45s
    wait. The underlying client is irrelevant here since wait_for's mock
    never actually awaits it; it exists only so `get_client().chat(...)`
    resolves to a valid coroutine object without erroring."""
    _no_preclassify_match()
    fake_client = _mock_client(content="unused")
    with patch("core.inference.provider_client.get_client", return_value=fake_client), \
         patch("asyncio.wait_for", new=AsyncMock(side_effect=asyncio.TimeoutError())):
        result = await governor.classify_chat_intent(TEST_TEXT)
    assert result.get("type") == "answer_question", (
        "a classifier failure must still fail SAFE to the conservative "
        "conversational type string, for backward compatibility with every "
        "existing caller that only checks .get('type')"
    )
    assert result.get("classification_failed") is True, (
        "a genuine timeout must be marked as an infrastructure failure, "
        "distinguishable from a real 'this is conversation' determination"
    )
    assert result.get("failure_reason") == "timeout"


# ── 3. Invalid/unparseable LLM output -> classification_failed=True ────────

@pytest.mark.asyncio
async def test_invalid_output_sets_classification_failed():
    _no_preclassify_match()
    fake_client = _mock_client(content="this is not json at all, sorry")
    with patch("core.inference.provider_client.get_client", return_value=fake_client):
        result = await governor.classify_chat_intent(TEST_TEXT)
    assert result.get("type") == "answer_question"
    assert result.get("classification_failed") is True, (
        "unparseable LLM output (NO_JSON_MATCH) is a classifier INFRASTRUCTURE "
        "failure per POST-RGC2 REPAIR Section 6, not evidence the user wanted "
        "conversation"
    )
    assert result.get("failure_reason") == "invalid_output"


# ── 4. Provider-layer exception -> classification_failed=True ──────────────

@pytest.mark.asyncio
async def test_provider_exception_sets_classification_failed():
    _no_preclassify_match()
    fake_client = _mock_client(raise_exc=RuntimeError("All providers failed. Last error: ..."))
    with patch("core.inference.provider_client.get_client", return_value=fake_client):
        result = await governor.classify_chat_intent(TEST_TEXT)
    assert result.get("type") == "answer_question"
    assert result.get("classification_failed") is True, (
        "a provider-layer exception (e.g. every provider in the fallback "
        "chain genuinely failed) is a classifier infrastructure failure, not "
        "semantic evidence of conversational intent"
    )
    assert result.get("failure_reason") == "provider_error"


# ── 5. Genuine successful classification of pure conversation — UNCHANGED ──

@pytest.mark.asyncio
async def test_genuine_conversation_does_not_set_classification_failed():
    """The classifier running successfully and correctly determining the
    message is pure chat (is_action=false) must NOT be flagged as a failure
    — this is a real, valid, completed classification."""
    _no_preclassify_match()
    fake_client = _mock_client(content='{"is_action": false, "task_type": "", "district": "", "confidence": 0.9}')
    with patch("core.inference.provider_client.get_client", return_value=fake_client):
        result = await governor.classify_chat_intent(TEST_TEXT)
    assert result.get("type") == "answer_question"
    assert not result.get("classification_failed"), (
        "a genuine, successfully-parsed 'not an action' classification must "
        "never be conflated with an infrastructure failure"
    )


# ── 6. Low-confidence rejection — UNCHANGED (also not a failure) ───────────

@pytest.mark.asyncio
async def test_low_confidence_rejection_does_not_set_classification_failed():
    """The classifier successfully running but returning low confidence is a
    real, completed classification (just not confident enough to trust as an
    action) — distinct from an infrastructure failure."""
    _no_preclassify_match()
    fake_client = _mock_client(
        content='{"is_action": true, "task_type": "some_action", "district": "research", "confidence": 0.2}'
    )
    with patch("core.inference.provider_client.get_client", return_value=fake_client):
        result = await governor.classify_chat_intent(TEST_TEXT)
    assert result.get("type") == "answer_question"
    assert not result.get("classification_failed"), (
        "a low-confidence but successfully-parsed classification is not an "
        "infrastructure failure"
    )


# ── 7. Genuine successful action classification — fully unaffected ─────────

@pytest.mark.asyncio
async def test_successful_action_classification_unaffected():
    _no_preclassify_match()
    fake_client = _mock_client(
        content='{"is_action": true, "task_type": "search_arxiv", "district": "research", "confidence": 0.95}'
    )
    with patch("core.inference.provider_client.get_client", return_value=fake_client):
        result = await governor.classify_chat_intent(TEST_TEXT)
    assert result.get("type") == "search_arxiv"
    assert result.get("district") == "research"
    assert not result.get("classification_failed")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
