"""V1 TRUST CLOSURE — T1 (factual trust / retrieval fabrication) tests.

Background (OWNER_ROUTING_CLOSURE_REPORT.md Section 20, live V1): a
research/current-information-shaped owner request was classified
`is_action=false`; no retrieval ran; the conversational fallback then
returned confident, specific, current-looking claims ("Synthesia 2.0",
"Midjourney 5.0 + ElevenLabs", ...). Source-traced 2026-09-21:

  * commands._llm_answer()'s system prompt says "If the context doesn't
    cover it, answer from general knowledge" and "you DO have that
    information from your training... never say 'I don't have
    information' about ... general facts" — with no carve-out for
    information that CHANGES (latest/new/recent). A request for "what's
    newly out there" is answered from stale training data as if current.
  * The only post-hoc guard, `defabricate_llm_answer()`, strips false
    ACTION-COMPLETION claims ("I've saved X"); it has no notion of
    fabricated current FACTS.
  * Nothing on the conversational path knows whether retrieval occurred.

Invariant proven here: an owner request whose answer depends on external,
changing information is either (A) routed to a REAL retrieval capability
(`search_arxiv`, GREEN, real PaperReader/arXiv) and answered ONLY from the
retrieved evidence, or (B) answered with an honest statement that current
information could not be retrieved/verified — never with free-generated
current-looking facts. Timeless knowledge, brainstorming and the existing
action-completion guard are unaffected.

Per .claude/rules/testing.md the mocked boundaries are external only: the
classifier/answer LLMs and the district-agent boundary (`Governor.dispatch`
= arXiv). Routing, DecisionEngine, PermissionGateway and `command_endpoint`
run as real production code.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers import commands as commands_router
from core.api.schemas import CommandRequest
from core.city.governor import Governor
from core.city.intent_matcher import IntentMatcher
from core.loop.decision_engine import DecisionEngine
from core.loop.permission_gateway import PermissionGateway

FABRICATED = (
    "**New developments in AI content ops:** Synthesia 2.0, Pictory AI's video "
    "upscaling, Midjourney 5.0 + ElevenLabs, TikTok's Creator Fund + AI tools."
)


@pytest.fixture(autouse=True)
def _no_embedding_match():
    with patch.object(IntentMatcher, "match", new=AsyncMock(return_value=None)):
        yield


class _R:
    def __init__(self, content):
        self.content = content


def _classifier_says_conversation():
    fake = AsyncMock()
    fake.chat = AsyncMock(return_value=_R('{"is_action": false, "task_type": "", "district": "", "confidence": 0.0}'))
    return fake


class _FakeContextEngine:
    def session_hydration_prompt(self, extra_context=None):
        return "TEST_HYDRATION_CONTEXT"


@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "v1_trust_t1_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_v1_trust_t1")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem
    ep.close_db_connection()


async def _run(text, isolated_episodic, *, answer_llm_text=FABRICATED, dispatch=None):
    """Returns (response, conv_llm_mock, dispatch_mock). The conversational
    (free-generation) LLM is armed to return fabricated current facts; a
    test passes only if those never reach the owner."""
    conv_chat = AsyncMock(return_value=_R(answer_llm_text))

    class _FakeProviderClient:
        async def chat(self, *a, **k):
            return await conv_chat(*a, **k)

    dispatch_mock = dispatch if dispatch is not None else AsyncMock(return_value={"status": "ok", "papers": []})
    with patch("core.inference.provider_client.get_client", return_value=_classifier_says_conversation()), \
         patch("core.inference.provider_client.ProviderClient", _FakeProviderClient), \
         patch.object(Governor, "dispatch", dispatch_mock), \
         patch.object(PermissionGateway, "_notify", new=AsyncMock()):
        response = await commands_router.command_endpoint(
            body=CommandRequest(text=text),
            ctx_engine=_FakeContextEngine(),
            decision_engine=DecisionEngine(),
            perm_gateway=PermissionGateway(),
            episodic_mem=isolated_episodic,
        )
    return response, conv_chat, dispatch_mock


# ── 1. The demonstrated V1 failure ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_recent_research_request_without_retrieval_does_not_invent_current_facts(isolated_episodic):
    response, conv_chat, _ = await _run(
        "Any chance you could check what's newly out there on this general area of study?",
        isolated_episodic,
    )
    assert "Synthesia" not in response.response and "Midjourney" not in response.response, response.response
    assert conv_chat.await_count == 0, "free-generation LLM must not answer a current-information request"
    assert any(w in response.response.lower() for w in ("can't verify", "couldn't retrieve", "cannot verify")), response.response


# ── 2. Current product/version request, no retrieval capability ────────────

@pytest.mark.asyncio
async def test_current_product_version_request_gets_honest_inability(isolated_episodic):
    response, conv_chat, _ = await _run(
        "What are the newest versions of PyTorch and what changed in them?", isolated_episodic
    )
    assert "Synthesia" not in response.response
    assert conv_chat.await_count == 0
    assert "verify" in response.response.lower()


# ── 3. Retrieval succeeds: answer is grounded in the evidence ─────────────

@pytest.mark.asyncio
async def test_retrieval_with_evidence_produces_grounded_answer(isolated_episodic):
    papers = [{"title": "Protein Folding With Sparse Attention", "authors": "A. Author, B. Author",
               "abstract": "x", "url": "http://arxiv.org/abs/2601.00001", "id": "2601.00001"}]
    dispatch = AsyncMock(return_value={"status": "ok", "papers": papers})
    response, conv_chat, dispatch_mock = await _run(
        "What's the latest research on protein folding?", isolated_episodic, dispatch=dispatch
    )
    assert dispatch_mock.await_count == 1
    sent = dispatch_mock.await_args.args[0]
    assert sent["type"] == "search_arxiv", sent
    assert "protein folding" in sent["params"]["query"].lower()
    assert "Protein Folding With Sparse Attention" in response.response
    assert "arxiv" in response.response.lower()
    assert conv_chat.await_count == 0, "grounded answers come from the evidence, not free generation"
    assert response.action_taken == "search_arxiv"


# ── 4. Timeless question: normal conversation still available ──────────────

@pytest.mark.asyncio
async def test_timeless_question_stays_conversational(isolated_episodic):
    response, conv_chat, dispatch_mock = await _run(
        "Explain how photosynthesis works.", isolated_episodic, answer_llm_text="Plants convert light into chemical energy."
    )
    assert conv_chat.await_count == 1
    assert dispatch_mock.await_count == 0
    assert "chemical energy" in response.response


# ── 5. Brainstorming with a recency word does not trigger retrieval ────────

@pytest.mark.asyncio
async def test_brainstorming_does_not_trigger_retrieval(isolated_episodic):
    response, conv_chat, dispatch_mock = await _run(
        "Brainstorm five names for a newsletter about recent AI trends.",
        isolated_episodic, answer_llm_text="1. Signal Weekly 2. Trend Loop",
    )
    assert conv_chat.await_count == 1, "creative generation must stay conversational"
    assert dispatch_mock.await_count == 0
    assert "Signal Weekly" in response.response


# ── 6. Existing false action-completion guard still intact ─────────────────

@pytest.mark.asyncio
async def test_action_completion_guard_still_strips_false_claims(isolated_episodic):
    response, conv_chat, _ = await _run(
        "Store this in memory: my favorite color is teal.",
        isolated_episodic, answer_llm_text="✅ Stored permanently: favorite color = teal.",
    )
    assert conv_chat.await_count == 1
    assert "Stored permanently" not in response.response, response.response


# ── 7. Retrieval failure: no fabricated fallback ──────────────────────────

@pytest.mark.asyncio
async def test_retrieval_failure_does_not_fall_back_to_fabrication(isolated_episodic):
    dispatch = AsyncMock(side_effect=RuntimeError("arxiv unreachable"))
    response, conv_chat, _ = await _run(
        "What's the latest research on protein folding?", isolated_episodic, dispatch=dispatch
    )
    assert "Synthesia" not in response.response
    assert conv_chat.await_count == 0, "a failed retrieval must not fall through to free generation"
    assert any(w in response.response.lower() for w in ("couldn't retrieve", "can't verify", "won't guess")), response.response


# ── 8. The /ws/command conversational path gets the same floor ─────────────

@pytest.mark.asyncio
async def test_ws_conversational_path_also_refuses_to_invent_current_facts():
    conv_chat = AsyncMock(return_value=_R(FABRICATED))
    fake_client = AsyncMock()
    fake_client.chat = conv_chat
    with patch("core.inference.provider_client.get_client", return_value=fake_client):
        result = await Governor()._answer_conversationally(
            {"type": "answer_question", "params": {"query": "what's newly out there in AI video tools right now?"}}
        )
    assert "Synthesia" not in (result.get("response") or "")
    assert conv_chat.await_count == 0
    assert "verify" in (result.get("response") or "").lower()


# ── 9. The current-information gate itself ────────────────────────────────

@pytest.mark.parametrize("text", [
    "Any chance you could check what's newly out there on this general area of study?",
    "Could you pull up whatever's been published recently on this specific research area?",
    "What are the newest versions of PyTorch and what changed in them?",
    "What's the latest research on protein folding?",
    "Find out what's actually been published on it lately.",
    "Any recent news on open-source language models?",
])
def test_gate_flags_current_information_requests(text):
    from core.security.anti_fabrication import requires_current_information
    assert requires_current_information(text) is True, text


@pytest.mark.parametrize("text", [
    "Explain how photosynthesis works.",
    "How are you doing today?",
    "What do you think about remote work in general?",
    "Brainstorm five names for a newsletter about recent AI trends.",
    "Draft a post about the latest thing I shipped.",
    "What's on my schedule for the next few days?",
    "What is the current time?",
    "Store this in memory: my favorite color is teal.",
])
def test_gate_does_not_flag_timeless_creative_or_local_requests(text):
    from core.security.anti_fabrication import requires_current_information
    assert requires_current_information(text) is False, text
