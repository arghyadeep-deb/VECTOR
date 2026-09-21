"""PRE-RG-D2 FINAL CLOSURE — Target B (real arXiv success path).

Background (V1_TRUST_ACTION_IDENTITY_PERMISSION_CLOSURE_REPORT.md §14 #2,
live CT2/A1): the owner-path retrieval branch was unreachable in
production. `ResearchHub.search_arxiv` called `http://export.arxiv.org/…`,
which now answers with an EMPTY 301 redirect (the HTTPS endpoint returns the
Atom feed; `PaperReader` already uses HTTPS). `ET.fromstring("")` raised,
was swallowed, and `[]` came back — so only the honest-failure branch of T1
was ever exercised.

Traced for this mission: a second, independent seam — `Governor.dispatch`
may pick either agent that declares `search_arxiv`; `PaperReader` returns
its evidence under `papers` (authors as a string) but `ResearchHub.run`
returns it under `results` (authors as a list, plus `published`). The
owner-path evidence renderer only read `papers`, so even with HTTPS fixed a
ResearchHub answer would have rendered as "no results". Both shapes must
render.

Invariant: retrieval succeeds -> the owner sees the ACTUAL retrieved
evidence; retrieval fails/empty/malformed -> honest inability, never an LLM
factual fallback.
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

ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2601.01234v1</id>
    <published>2026-01-05T09:00:00Z</published>
    <title>Sparse Mixture-of-Experts Routing at Scale</title>
    <summary>We study routing in sparse mixture-of-experts language models.</summary>
    <author><name>Ada Author</name></author>
    <author><name>Bo Author</name></author>
  </entry>
</feed>"""


class _FakeResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def _fake_async_client(*, text=None, exc=None, seen=None):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kwargs):
            if seen is not None:
                seen["url"] = url
                seen["params"] = kwargs.get("params")
            if exc:
                raise exc
            return _FakeResp(text)
    return _Client


@pytest.fixture()
def hub():
    from districts.research.research_hub import ResearchHub
    return ResearchHub()


# ── 1. HTTPS endpoint ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_research_hub_uses_https_arxiv_endpoint(hub):
    seen: dict = {}
    with patch("httpx.AsyncClient", _fake_async_client(text=ATOM_FEED, seen=seen)):
        await hub.search_arxiv("mixture-of-experts")
    assert seen["url"].startswith("https://export.arxiv.org/"), (
        f"the HTTP endpoint answers with an empty 301; got {seen['url']!r}"
    )


# ── 2/3. Valid feed parsed, evidence preserved ─────────────────────────────

@pytest.mark.asyncio
async def test_valid_feed_is_parsed_with_evidence_preserved(hub):
    with patch("httpx.AsyncClient", _fake_async_client(text=ATOM_FEED)):
        results = await hub.search_arxiv("mixture-of-experts")
    assert len(results) == 1
    r = results[0]
    assert r["title"] == "Sparse Mixture-of-Experts Routing at Scale"
    assert r["url"] == "http://arxiv.org/abs/2601.01234v1"
    assert r["authors"] == ["Ada Author", "Bo Author"]
    assert r["published"] == "2026-01-05"
    assert r["source"] == "arxiv"


# ── 5/6/7. Empty / network failure / malformed -> [] (honest upstream) ─────

@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["empty", "network", "malformed"])
async def test_failures_return_empty_never_invented_results(hub, kind):
    client = {
        "empty": _fake_async_client(text=""),
        "network": _fake_async_client(exc=ConnectionError("arxiv unreachable")),
        "malformed": _fake_async_client(text="<html><body>rate limited</body>"),
    }[kind]
    with patch("httpx.AsyncClient", client):
        assert await hub.search_arxiv("anything") == []


# ── 4. Owner response is grounded in the retrieved evidence (BOTH agents'
#       result shapes) ───────────────────────────────────────────────────────

def test_renderer_grounds_response_in_researchhub_shaped_result():
    result = {
        "status": "ok", "response": "ignored formatted text",
        "results": [{"title": "Sparse Mixture-of-Experts Routing at Scale", "url": "http://arxiv.org/abs/2601.01234v1",
                     "authors": ["Ada Author", "Bo Author"], "published": "2026-01-05", "source": "arxiv"}],
    }
    text = commands_router._render_readonly_evidence("search_arxiv", result)
    assert "Sparse Mixture-of-Experts Routing at Scale" in text
    assert "http://arxiv.org/abs/2601.01234v1" in text
    assert "Ada Author, Bo Author" in text and "[" not in text.split("—")[1], text
    assert "2026-01-05" in text


def test_renderer_still_grounds_response_in_paperreader_shaped_result():
    result = {"status": "ok", "papers": [{"title": "Graph Nets Survey", "authors": "A. B, C. D",
                                          "url": "http://arxiv.org/abs/2501.00001", "abstract": "x", "id": "2501.00001"}]}
    text = commands_router._render_readonly_evidence("search_arxiv", result)
    assert "Graph Nets Survey" in text and "http://arxiv.org/abs/2501.00001" in text


def test_renderer_empty_results_are_honest_for_both_shapes():
    for result in ({"status": "ok", "results": []}, {"status": "ok", "papers": []}, {"status": "ok"}):
        text = commands_router._render_readonly_evidence("search_arxiv", result)
        assert "couldn't retrieve" in text and "won't guess" in text, text


# ── End to end through the real /command path ─────────────────────────────

class _FakeContextEngine:
    def session_hydration_prompt(self, extra_context=None):
        return "TEST_HYDRATION_CONTEXT"


@pytest.fixture(autouse=True)
def _no_embedding_match():
    with patch.object(IntentMatcher, "match", new=AsyncMock(return_value=None)):
        yield


@pytest.fixture()
def isolated_episodic(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "pre_rgd2_b_test.db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_pre_rgd2_b")
    import core.memory.episodic as ep
    ep.close_db_connection()
    mem = ep.EpisodicMemory()
    yield mem
    ep.close_db_connection()


class _R:
    def __init__(self, content):
        self.content = content


async def _run_endpoint(text, dispatch_result, isolated_episodic, *, dispatch_exc=None):
    conv_chat = AsyncMock(return_value=_R("Synthesia 2.0 and Midjourney 5.0 are the latest."))

    class _PC:
        async def chat(self, *a, **k):
            return await conv_chat(*a, **k)

    classifier = AsyncMock()
    classifier.chat = AsyncMock(return_value=_R('{"is_action": false, "task_type": "", "district": "", "confidence": 0.0}'))
    dispatch = AsyncMock(return_value=dispatch_result, side_effect=dispatch_exc)
    with patch("core.inference.provider_client.get_client", return_value=classifier), \
         patch("core.inference.provider_client.ProviderClient", _PC), \
         patch.object(Governor, "dispatch", dispatch), \
         patch.object(PermissionGateway, "_notify", new=AsyncMock()):
        resp = await commands_router.command_endpoint(
            body=CommandRequest(text=text), ctx_engine=_FakeContextEngine(),
            decision_engine=DecisionEngine(), perm_gateway=PermissionGateway(),
            episodic_mem=isolated_episodic,
        )
    return resp, conv_chat


@pytest.mark.asyncio
async def test_endpoint_returns_retrieved_evidence_when_researchhub_answers(isolated_episodic):
    payload = {"status": "ok", "response": "x", "results": [
        {"title": "Sparse Mixture-of-Experts Routing at Scale", "url": "http://arxiv.org/abs/2601.01234v1",
         "authors": ["Ada Author"], "published": "2026-01-05", "source": "arxiv"}]}
    resp, conv = await _run_endpoint("Any recent papers on mixture-of-experts language models?", payload, isolated_episodic)
    assert "Sparse Mixture-of-Experts Routing at Scale" in resp.response
    assert resp.action_taken == "search_arxiv"
    assert conv.await_count == 0


# ── 8. No LLM factual fallback masquerading as retrieval ──────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("payload,exc", [
    ({"status": "ok", "results": []}, None),
    ({"status": "ok"}, None),
    (None, RuntimeError("arxiv unreachable")),
])
async def test_retrieval_failure_never_falls_back_to_llm_facts(isolated_episodic, payload, exc):
    resp, conv = await _run_endpoint(
        "Any recent papers on mixture-of-experts language models?", payload, isolated_episodic, dispatch_exc=exc
    )
    assert "Synthesia" not in resp.response and "Midjourney" not in resp.response
    assert conv.await_count == 0
    assert "couldn't retrieve" in resp.response and "won't guess" in resp.response


# ── Correction pass (found by the live in-process check, not the frozen
#    probes): the multi-word topic was sent as an unquoted `ti:X OR abs:X`, which
#    arXiv does not parse as a topic — real HTTPS retrieval worked but returned the
#    newest papers of ANY subject (physics papers for a RAG query). Real evidence
#    that is not about the topic is not grounding. Each content term must be an
#    explicit `all:` AND term. ───────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("topic,expected", [
    ("retrieval-augmented generation code", "all:retrieval AND all:augmented AND all:generation AND all:code"),
    ("state space models like Mamba", "all:state AND all:space AND all:models AND all:Mamba"),
    ("transformers", "all:transformers"),
])
async def test_topic_becomes_anded_all_field_terms(hub, topic, expected):
    seen: dict = {}
    with patch("httpx.AsyncClient", _fake_async_client(text=ATOM_FEED, seen=seen)):
        await hub.search_arxiv(topic)
    assert seen["params"]["search_query"] == expected


@pytest.mark.asyncio
async def test_category_still_composes_with_topic_terms(hub):
    seen: dict = {}
    with patch("httpx.AsyncClient", _fake_async_client(text=ATOM_FEED, seen=seen)):
        await hub.search_arxiv("large language model", category="cs.AI")
    assert seen["params"]["search_query"] == "cat:cs.AI AND (all:large AND all:language AND all:model)"


@pytest.mark.asyncio
async def test_query_operators_in_topic_text_cannot_inject_arxiv_syntax(hub):
    seen: dict = {}
    with patch("httpx.AsyncClient", _fake_async_client(text=ATOM_FEED, seen=seen)):
        await hub.search_arxiv('graphs OR all:secret ANDNOT cat:x "quoted"')
    q = seen["params"]["search_query"]
    assert " OR " not in q and "ANDNOT" not in q and '"' not in q and "cat:" not in q
    # operator/field words survive only as inert `all:<word>` terms — no field prefix of the caller's choosing
    assert q == "all:graphs AND all:all AND all:secret AND all:cat AND all:x AND all:quoted"
    assert all(part.startswith("all:") for part in q.split(" AND "))


@pytest.mark.asyncio
async def test_topic_with_no_content_terms_makes_no_request(hub):
    seen: dict = {}
    with patch("httpx.AsyncClient", _fake_async_client(text=ATOM_FEED, seen=seen)):
        assert await hub.search_arxiv("the of and") == []
    assert seen == {}, "an empty topic must not be sent to arXiv (it would return arbitrary newest papers)"
