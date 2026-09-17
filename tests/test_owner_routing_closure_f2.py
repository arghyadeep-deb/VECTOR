"""OWNER ROUTING CLOSURE — F2 (is_action=false false negative) tests.

Background (VECTOR_TECHNICAL_KNOWLEDGE/RGC2R_RGD2_COMBINED_REALITY_GATE_
REPORT.md Section 11/36): C3 — "When you get a moment, I'd appreciate a
look back at how today's gone and any thoughts worth flagging." — was
classified `is_action=false, task_type="", district="", confidence=0.0`
despite `daily_review`/`reflect` being real, GREEN-tier reflection
capabilities. `_REGEX_PRECLASSIFY` already has a deterministic pattern for
the exact same shape of request but only for WEEKLY framing
('weekly'/'my week' + review/patterns/reflect/gone); there was no
equivalent for TODAY-framed daily review language, so this fell all the
way through to the LLM classifier, which judged it conversational.

Per the mission's explicit prohibition ("do NOT fix this by `if is_action
== false: is_action = true`" / "do not simply keyword-match 'look',
'review', 'today'"), the fix is a narrow, symmetric extension of the
EXISTING deterministic regex-preclassify mechanism — requiring BOTH a
today/day reference AND a review/reflect/gone/went/thoughts term, the same
two-signal rigor the existing weekly pattern already uses (week/my-week +
review/patterns/reflect/gone) — not a bare "if action_shaped: is_action =
true" hack, and not single-keyword matching.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.city import governor
from core.city.intent_matcher import IntentMatcher


@pytest.fixture(autouse=True)
def _no_embedding_match():
    with patch.object(IntentMatcher, "match", new=AsyncMock(return_value=None)):
        yield


class _FakeCompletionResult:
    def __init__(self, content: str):
        self.content = content


def _mock_client(content: str):
    async def _chat(*args, **kwargs):
        return _FakeCompletionResult(content)
    fake = AsyncMock()
    fake.chat = _chat
    return fake


async def _classify(text: str, llm_json: str | None = None) -> dict:
    """llm_json=None means the LLM should NEVER be called — used to prove
    the regex-preclassify layer fires before any LLM round trip, exactly
    like the existing weekly_review pattern already does."""
    if llm_json is None:
        with patch("core.inference.provider_client.get_client") as mock_get_client:
            mock_get_client.side_effect = AssertionError(
                "LLM classifier must not be called — a deterministic "
                "regex-preclassify match should have short-circuited first"
            )
            return await governor.classify_chat_intent(text)
    with patch("core.inference.provider_client.get_client", return_value=_mock_client(llm_json)):
        return await governor.classify_chat_intent(text)


# ── ACTION-SHAPED: the exact demonstrated C3 failure ───────────────────────

@pytest.mark.asyncio
async def test_c3_exact_wording_now_reaches_reflection():
    text = "When you get a moment, I'd appreciate a look back at how today's gone and any thoughts worth flagging."
    result = await _classify(text)
    assert result.get("district") == "reflection"
    assert result.get("type") == "daily_review"


# ── ACTION-SHAPED: polite indirect wording, different phrasing ─────────────

@pytest.mark.asyncio
async def test_polite_indirect_daily_reflection_wording():
    text = "Could you look back over how today went and flag anything worth noting?"
    result = await _classify(text)
    assert result.get("district") == "reflection"
    assert result.get("type") == "daily_review"


# ── ACTION-SHAPED: imperative wording ───────────────────────────────────────

@pytest.mark.asyncio
async def test_imperative_daily_reflection_wording():
    text = "Review how today went and flag anything worth noting."
    result = await _classify(text)
    assert result.get("district") == "reflection"
    assert result.get("type") == "daily_review"


# ── CONVERSATIONAL: must remain conversation, NOT become an action ─────────

@pytest.mark.asyncio
async def test_opinion_question_about_today_stays_conversation():
    """Contains 'today' but no review/reflect/gone/went/thoughts term —
    must not match the new pattern, must reach the LLM (which we mock to
    genuinely say not-an-action)."""
    llm_json = '{"is_action": false, "task_type": "", "district": "", "confidence": 0.0}'
    text = "What do you think about today?"
    result = await _classify(text, llm_json)
    assert result.get("type") == "answer_question"


@pytest.mark.asyncio
async def test_general_discussion_stays_conversation():
    llm_json = '{"is_action": false, "task_type": "", "district": "", "confidence": 0.0}'
    text = "I've been thinking about how things are going in general lately."
    result = await _classify(text, llm_json)
    assert result.get("type") == "answer_question"


@pytest.mark.asyncio
async def test_ambiguous_statement_stays_conversation():
    llm_json = '{"is_action": false, "task_type": "", "district": "", "confidence": 0.0}'
    text = "Today was something else, honestly."
    result = await _classify(text, llm_json)
    assert result.get("type") == "answer_question"


# ── SECURITY: RED-shaped request must not become GREEN via this fallback ───

@pytest.mark.asyncio
async def test_red_shaped_request_not_downgraded_by_daily_pattern():
    """Even though this contains 'today' language, a delete/money-movement
    request must never be captured by the new daily-review pattern — the
    trade/money-movement guard runs earlier in the function and forces
    answer_question regardless."""
    text = "Today, could you go ahead and transfer some money for me, reflecting on how much is worth flagging?"
    result = await _classify(text)
    assert result.get("type") == "answer_question"


@pytest.mark.asyncio
async def test_nonexistent_capability_not_captured():
    """A request that superficially mentions 'today'/'thoughts' but asks for
    a capability VECTOR doesn't have must not be swept into daily_review —
    the new pattern's own vocabulary requirement (today/day + review-ish
    term) is necessarily narrow, so this simply must not spuriously match a
    clearly unrelated ask."""
    llm_json = '{"is_action": false, "task_type": "", "district": "", "confidence": 0.0}'
    text = "Could you translate this alien language I invented today?"
    result = await _classify(text, llm_json)
    assert result.get("type") == "answer_question"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
