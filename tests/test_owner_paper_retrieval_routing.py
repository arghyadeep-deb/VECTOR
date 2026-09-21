"""OWNER PAPER-RETRIEVAL ROUTING CLOSURE tests.

Background (PRE_RG_D2_FINAL_CLOSURE_REPORT.md §12/§15 #1): the retrieval
capability (search_arxiv over HTTPS, on-topic query, evidence renderer) was
proven, but two frozen live owner probes never reached it:

  B1 "Any recent papers on retrieval-augmented generation for code?"
     -> the general LLM classifier hit its 45 s ceiling
     -> `classification_failed` early-return; retrieval never reached
  B2 "What new papers have come out on state space models like Mamba?"
     -> classifier said action `research_papers_search` -> canonical
        `research_papers` -> PermissionGateway UNKNOWN -> blocked

Root cause: the T1 deterministic retrieval route (`current_information_plan`)
only ran AFTER the classifier and only when it returned exactly
`answer_question`. Recent-paper retrieval therefore depended on an LLM call
succeeding and picking one specific verdict.

Invariant proven here: when the deterministic plan establishes (recency +
academic cue + concrete topic, and no action verb), the request goes
straight through the NORMAL Candidate -> DecisionEngine -> PermissionGateway
-> search_arxiv -> evidence path without consulting the classifier; an
academic-paper alias (`research_papers*`) folds to the authorized
`search_arxiv` only for a genuine paper-retrieval request; everything
ambiguous stays fail-closed on the old path.

Mocked boundaries are external only (LLMs, `Governor.dispatch` = arXiv);
routing, DecisionEngine, PermissionGateway and `command_endpoint` are real.
"""
from __future__ import annotations

import asyncio
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
from core.security.anti_fabrication import current_information_plan

B1 = "Any recent papers on retrieval-augmented generation for code?"
B2 = "What new papers have come out on state space models like Mamba?"

FABRICATED = "Recent work includes Synthesia 2.0 and Midjourney 5.0 and a 2026 paper by Smith et al."

RESULTS = [{"title": "Sparse State Space Models At Scale", "url": "http://arxiv.org/abs/2609.11111v1",
            "authors": ["Ada Author", "Bo Author"], "published": "2026-09-18", "source": "arxiv"}]


@pytest.fixture(autouse=True)
def _no_embedding_match():
    with patch.object(IntentMatcher, "match", new=AsyncMock(return_value=None)):
        yield


class _R:
    def __init__(self, content):
        self.content = content


class _FakeContextEngine:
    def session_hydration_prompt(self, extra_context=None):
        return "TEST_HYDRATION_CONTEXT"


@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "paper_routing_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_paper_routing")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem
    ep.close_db_connection()


def _classifier(kind):
    fake = AsyncMock()
    if kind == "timeout":
        fake.chat = AsyncMock(side_effect=asyncio.TimeoutError())
    elif kind == "research_papers_search":
        fake.chat = AsyncMock(return_value=_R(
            '{"is_action": true, "task_type": "research_papers_search", "district": "knowledge", "confidence": 0.95}'))
    elif kind == "conversation":
        fake.chat = AsyncMock(return_value=_R('{"is_action": false, "task_type": "", "district": "", "confidence": 0.9}'))
    else:
        raise ValueError(kind)
    return fake


async def _run(text, mem, *, classifier="conversation", dispatch=None, spy=None):
    """Returns (response, classifier_mock, conversational_llm_mock, dispatch_mock)."""
    conv_chat = AsyncMock(return_value=_R(FABRICATED))

    class _PC:
        async def chat(self, *a, **k):
            return await conv_chat(*a, **k)

    clf = _classifier(classifier)
    dispatch_mock = dispatch if dispatch is not None else AsyncMock(return_value={"status": "ok", "results": RESULTS})

    engine = DecisionEngine()
    gateway = PermissionGateway()
    if spy is not None:
        real_eval, real_classify = engine.evaluate, gateway._classify

        async def _eval(cands, *a, **k):
            spy["candidates"] = [c.action_type for c in cands]
            return await real_eval(cands, *a, **k)

        def _cls(action_type, *a, **k):
            spy.setdefault("gateway_classified", []).append(action_type)
            return real_classify(action_type, *a, **k)

        engine.evaluate = _eval
        gateway._classify = _cls

    with patch("core.inference.provider_client.get_client", return_value=clf), \
         patch("core.inference.provider_client.ProviderClient", _PC), \
         patch.object(Governor, "dispatch", dispatch_mock), \
         patch.object(PermissionGateway, "_notify", new=AsyncMock()):
        resp = await commands_router.command_endpoint(
            body=CommandRequest(text=text), ctx_engine=_FakeContextEngine(),
            decision_engine=engine, perm_gateway=gateway, episodic_mem=mem,
        )
    return resp, clf, conv_chat, dispatch_mock


def _dispatched_types(dispatch_mock):
    return [c.args[0].get("type") for c in dispatch_mock.await_args_list]


# ── 1. recent papers + concrete topic + classifier TIMEOUT (demonstrated B1) ─

@pytest.mark.asyncio
async def test_recent_papers_with_classifier_timeout_still_reaches_search_arxiv(isolated_episodic):
    resp, clf, conv, dispatch = await _run(B1, isolated_episodic, classifier="timeout")
    assert _dispatched_types(dispatch) == ["search_arxiv"], resp.response
    assert "classification did not complete" not in resp.response
    assert "Sparse State Space Models At Scale" in resp.response
    assert resp.action_taken == "search_arxiv"
    assert conv.await_count == 0
    assert clf.chat.await_count == 0, "deterministic paper retrieval must not depend on the general LLM classifier"


# ── 2. classifier returns research_papers_search (demonstrated B2) ─────────

@pytest.mark.asyncio
async def test_recent_papers_with_classifier_research_papers_search_reaches_search_arxiv(isolated_episodic):
    resp, clf, conv, dispatch = await _run(B2, isolated_episodic, classifier="research_papers_search")
    assert _dispatched_types(dispatch) == ["search_arxiv"], resp.response
    assert "couldn't determine the action type" not in resp.response
    assert resp.action_taken == "search_arxiv"
    assert "state space models" in dispatch.await_args.args[0]["params"]["query"].lower()
    assert conv.await_count == 0


# ── 3. research_papers alias -> canonical executable identity ──────────────

@pytest.mark.parametrize("raw,canon", [("research_papers_search", "research_papers"), (None, "research_papers")])
def test_research_papers_alias_folds_to_search_arxiv_for_a_genuine_paper_request(raw, canon):
    intent = {"type": canon, "district": "research", "confidence": 0.95, "raw_task_type": raw, "identity": "canonicalized"}
    out = commands_router._fold_paper_retrieval_alias(intent, "Could you pull together papers on graph neural networks?")
    assert out["type"] == "search_arxiv"
    assert out["topic"] == "graph neural networks"
    assert out["identity"] == "alias_to_search_arxiv"
    assert out["raw_task_type"] == raw


@pytest.mark.parametrize("text", [
    "Tell me about research_papers in my repo",          # not a paper request (no academic cue + topic)
    "Email my advisor papers on graph neural networks",  # action verb -> fail closed
    "Could you pull together papers?",                    # no concrete topic -> fail closed
])
def test_research_papers_alias_fails_closed_for_non_paper_or_ambiguous_requests(text):
    intent = {"type": "research_papers", "district": "research", "confidence": 0.95,
              "raw_task_type": "research_papers_search", "identity": "canonicalized"}
    assert commands_router._fold_paper_retrieval_alias(dict(intent), text) == intent


def test_only_paper_aliases_are_folded():
    intent = {"type": "review_code", "district": "ops", "confidence": 0.8, "raw_task_type": "review_code"}
    assert commands_router._fold_paper_retrieval_alias(dict(intent), "Any recent papers on mamba?") == intent


@pytest.mark.asyncio
async def test_alias_fold_applies_after_classification_when_no_recency_marker(isolated_episodic):
    # no recency marker -> the deterministic pre-route does not apply; the classifier
    # answers `research_papers_search`; the fold makes it the authorized capability.
    resp, clf, conv, dispatch = await _run(
        "Could you pull together papers on graph neural networks?", isolated_episodic, classifier="research_papers_search")
    assert clf.chat.await_count == 1
    assert _dispatched_types(dispatch) == ["search_arxiv"], resp.response
    assert resp.action_taken == "search_arxiv"


# ── 4. ordinary timeless academic question -> no forced retrieval ─────────

@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "Can you explain the difference between supervised and unsupervised learning?",
    "What did the original transformer paper propose?",
    "Why do state space models scale linearly in sequence length?",
])
async def test_timeless_academic_question_is_ordinary_conversation(isolated_episodic, text):
    resp, clf, conv, dispatch = await _run(text, isolated_episodic, classifier="conversation")
    assert dispatch.await_count == 0
    assert conv.await_count == 1
    assert resp.action_taken is None


# ── 5. current product / software-version request is NOT sent to arXiv ────

@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "What are the newest versions of PyTorch and what changed in them?",
    "What's the latest news on Tesla published this week?",
    "What is the current price of Bitcoin right now?",
])
async def test_current_non_academic_requests_are_not_routed_to_arxiv(isolated_episodic, text):
    assert (current_information_plan(text) or {}).get("mode") != "retrieve", text
    resp, clf, conv, dispatch = await _run(text, isolated_episodic, classifier="conversation")
    assert dispatch.await_count == 0
    assert conv.await_count == 0, "no free-generated current facts either"
    assert "verify" in resp.response.lower()


# ── 6. vague "what's new?" -> no invented topic, honest ───────────────────

@pytest.mark.asyncio
async def test_vague_whats_new_in_research_never_invents_a_topic(isolated_episodic):
    resp, clf, conv, dispatch = await _run("What's new in research these days?", isolated_episodic)
    assert dispatch.await_count == 0, "no topic named -> no search"
    assert "Synthesia" not in resp.response and "Smith et al" not in resp.response
    assert conv.await_count == 0


@pytest.mark.asyncio
async def test_bare_whats_new_is_small_talk_and_never_searches(isolated_episodic):
    # No external-information marker at all: ordinary conversation, and crucially no invented topic.
    resp, clf, conv, dispatch = await _run("What's new?", isolated_episodic)
    assert dispatch.await_count == 0
    assert clf.chat.await_count == 1


@pytest.mark.asyncio
async def test_vague_research_request_asks_for_a_topic(isolated_episodic):
    resp, clf, conv, dispatch = await _run("What's new in research these days?", isolated_episodic)
    assert "which area" in resp.response.lower() or "topic" in resp.response.lower(), resp.response


# ── 7. retrieval failure -> honest inability, no LLM factual fallback ─────

@pytest.mark.asyncio
@pytest.mark.parametrize("payload,exc", [
    ({"status": "ok", "results": []}, None),
    ({"status": "ok"}, None),
    (None, RuntimeError("arxiv unreachable")),
])
@pytest.mark.parametrize("classifier", ["timeout", "research_papers_search"])
async def test_retrieval_failure_is_honest_with_any_classifier_state(isolated_episodic, payload, exc, classifier):
    dispatch = AsyncMock(return_value=payload, side_effect=exc)
    resp, clf, conv, _ = await _run(B1, isolated_episodic, classifier=classifier, dispatch=dispatch)
    assert "couldn't retrieve" in resp.response and "won't guess" in resp.response, resp.response
    assert "Synthesia" not in resp.response and "Smith et al" not in resp.response
    assert conv.await_count == 0


# ── 8. successful retrieval -> actual evidence rendered ───────────────────

@pytest.mark.asyncio
async def test_successful_retrieval_renders_the_actual_evidence(isolated_episodic):
    resp, *_ = await _run(B2, isolated_episodic, classifier="timeout")
    assert "arXiv results retrieved just now" in resp.response
    assert "Sparse State Space Models At Scale" in resp.response
    assert "http://arxiv.org/abs/2609.11111v1" in resp.response
    assert "Ada Author, Bo Author" in resp.response and "2026-09-18" in resp.response


# ── 9. one identity from Candidate through gateway to dispatch ────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("classifier", ["timeout", "research_papers_search", "conversation"])
async def test_candidate_gateway_and_dispatch_identity_are_all_search_arxiv(isolated_episodic, classifier):
    spy: dict = {}
    resp, clf, conv, dispatch = await _run(B1, isolated_episodic, classifier=classifier, spy=spy)
    assert spy["candidates"] == ["search_arxiv"]
    assert "search_arxiv" in spy["gateway_classified"] and set(spy["gateway_classified"]) == {"search_arxiv"}
    assert _dispatched_types(dispatch) == ["search_arxiv"]
    assert resp.action_taken == "search_arxiv"


# ── 10. permission behaviour unchanged; actions are not swallowed ─────────

def test_permission_tiers_for_search_arxiv_and_gated_actions_are_unchanged():
    gw = PermissionGateway()
    assert gw._classify("search_arxiv") == "GREEN"
    assert gw._classify("send_email") == "RED"
    assert gw._classify("deploy_production") == "RED"
    assert gw._classify("commit_code") == "YELLOW"
    assert gw._classify("research_papers") == "UNKNOWN",         "research_papers itself stays unregistered — only the folded identity search_arxiv is authorized"


@pytest.mark.asyncio
async def test_action_requests_mentioning_papers_are_not_taken_by_the_pre_route(isolated_episodic):
    text = "Email my advisor the latest papers on reinforcement learning"
    from core.security.anti_fabrication import paper_retrieval_topic
    assert paper_retrieval_topic(text) is None, "an action verb makes the request ambiguous -> fail closed"
    resp, clf, conv, dispatch = await _run(text, isolated_episodic, classifier="conversation")
    assert clf.chat.await_count == 1, "an action-shaped request is still judged by the classifier first"


# ── Correction pass (found by the POST-RGC2 regression suite, which caught the
#    pre-route amplifying a latent topic-extraction flaw): a vague anaphoric
#    reference ("this general subject") followed by a task clause ("and
#    summarize it for me") leaked the task verb "summarize" as the topic. A
#    named topic must be a real subject, never a verb from the trailing task. ──

@pytest.mark.parametrize("text", [
    "could you dig into some current research on this general subject and summarize it for me",
    "What's the latest research on that, and explain it to me?",
    "Any recent papers on this topic, please?",
])
def test_vague_anaphoric_reference_is_not_a_topic(text):
    from core.security.anti_fabrication import paper_retrieval_topic
    assert paper_retrieval_topic(text) is None
    assert (current_information_plan(text) or {}).get("mode") == "decline"


@pytest.mark.parametrize("text,topic", [
    ("Any recent papers on retrieval-augmented generation for code, and summarize them for me?",
     "retrieval-augmented generation code"),
    ("What's the latest research on protein folding and explain the main result?", "protein folding"),
    ("Any recent papers on mixture of experts and routing?", "mixture experts routing"),
])
def test_task_clause_is_not_part_of_the_topic(text, topic):
    from core.security.anti_fabrication import paper_retrieval_topic
    assert paper_retrieval_topic(text) == topic
