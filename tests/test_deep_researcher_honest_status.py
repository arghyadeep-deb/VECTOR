"""DeepResearcher must not report a failed or empty research call as status "ok", and must accept the task types it
advertises (V1 handoff 2026-09-13, research workflow gaps; verified still open 2026-09-26).

Only the research_api functions (network + LLM) are stubbed; the agent's own dispatch and HP accounting run for real.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import districts.research.deep_researcher as dr


@pytest.fixture
def agent(isolated_vector_db, monkeypatch):
    a = dr.DeepResearcher()
    monkeypatch.setattr(a, "_get_memory", lambda: type("M", (), {"store": lambda *_a, **_k: None})())
    return a


def _task(kind, query="what is a bloom filter"):
    return {"type": kind, "params": {"query": query}}


@pytest.mark.asyncio
async def test_failed_research_is_an_error_not_ok(agent, monkeypatch):
    monkeypatch.setattr(dr, "quick_research", lambda q, save_to_brain=True: {
        "summary": "Research failed: provider down", "findings": [], "sources": [], "error": "provider down"})
    hp = agent.health_points
    out = await agent.run(_task("quick"))
    assert out["status"] == "error" and "provider down" in out["error"]
    assert agent.health_points < hp, "a failed research call must still cost HP"


@pytest.mark.asyncio
async def test_exception_inside_the_research_call_is_an_error(agent, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("engine crashed")
    monkeypatch.setattr(dr, "quick_research", boom)
    out = await agent.run(_task("quick"))
    assert out["status"] == "error" and "engine crashed" in out["error"]


@pytest.mark.asyncio
async def test_empty_result_is_not_ok(agent, monkeypatch):
    monkeypatch.setattr(dr, "research_news", lambda q, max_results=10: {"summary": "", "findings": [], "sources": []})
    out = await agent.run(_task("news"))
    assert out["status"] == "error" and "no content" in out["error"]


@pytest.mark.asyncio
async def test_failed_news_and_documents_no_longer_earn_hp(agent, monkeypatch):
    monkeypatch.setattr(dr, "research_news", lambda q, max_results=10: {
        "summary": "News research failed: x", "findings": [], "sources": [], "error": "x"})
    monkeypatch.setattr(dr, "analyze_documents", lambda q, c, m: {
        "summary": "Document analysis failed: y", "documents": [], "error": "y"})
    hp = agent.health_points
    assert (await agent.run(_task("news")))["status"] == "error"
    assert (await agent.run(_task("documents")))["status"] == "error"
    assert agent.health_points <= hp


@pytest.mark.asyncio
async def test_real_result_is_ok_and_carries_its_content(agent, monkeypatch):
    monkeypatch.setattr(dr, "quick_research", lambda q, save_to_brain=True: {
        "summary": "A bloom filter is a probabilistic set.", "findings": ["f"], "sources": ["https://x"]})
    out = await agent.run(_task("quick"))
    assert out["status"] == "ok" and out["sources"] == ["https://x"] and out["type"] == "quick"


@pytest.mark.asyncio
@pytest.mark.parametrize("advertised", ["deep_research", "research", "search"])
async def test_advertised_capability_names_are_accepted(agent, monkeypatch, advertised):
    monkeypatch.setattr(dr, "quick_research", lambda q, save_to_brain=True: {
        "summary": "ok text", "findings": [], "sources": ["s"]})
    out = await agent.run(_task(advertised))
    assert out["status"] == "ok", out


@pytest.mark.asyncio
async def test_genuinely_unknown_type_is_still_an_error(agent):
    out = await agent.run(_task("summon_dragons"))
    assert out["status"] == "error" and "Unknown task type" in out["error"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


@pytest.mark.asyncio
async def test_sourced_and_unsourced_answers_are_distinguished(agent, monkeypatch):
    monkeypatch.setattr(dr, "quick_research", lambda q, save_to_brain=True: {"summary": "A.", "findings": [], "sources": ["s1", "s2"]})
    sourced = await agent.run(_task("quick"))
    assert sourced["status"] == "ok" and sourced["evidence"] == {"sources": 2, "sourced": True}
    monkeypatch.setattr(dr, "quick_research", lambda q, save_to_brain=True: {"summary": "A bare claim.", "findings": [], "sources": []})
    bare = await agent.run(_task("quick"))
    assert bare["status"] == "ok" and bare["evidence"] == {"sources": 0, "sourced": False}


@pytest.mark.asyncio
async def test_an_unsourced_answer_earns_less_hp_than_a_sourced_one(agent, monkeypatch):
    async def gain(sources):
        monkeypatch.setattr(dr, "quick_research", lambda q, save_to_brain=True: {"summary": "text", "findings": [], "sources": sources})
        before = agent.health_points
        await agent.run(_task("quick"))
        return agent.health_points - before
    sourced = await gain(["https://x"])
    bare = await gain([])
    assert sourced > bare > 0, (sourced, bare)
