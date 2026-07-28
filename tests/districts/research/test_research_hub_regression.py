"""Regression coverage for KNOWN_ISSUES.md #1's stub-output bug in
ResearchHub.run() — all six task branches (search_web, daily_digest,
search_arxiv, get_hn, get_india_stocks, find_api) returned real results
under plural keys (results/apis) that
avatar/avatar_voice.py::_extract_text() doesn't check (it only checks
the 6 singular keys). Fixed 2026-07-22 (live-verified at the time) but
never got an automated test.
"""
from __future__ import annotations

import asyncio

import districts.research.api_catalog as api_catalog
from districts.research.research_hub import ResearchHub

_NARRATIVE_KEYS = ("response", "result", "content", "message", "text", "output")


def _assert_not_a_stub(result: dict) -> None:
    assert any(result.get(k) for k in _NARRATIVE_KEYS), (
        f"run() returned no narrative key from {_NARRATIVE_KEYS} — "
        f"this would render as the generic stub. Got: {result}"
    )
    assert result["status"] == "ok"
    assert len(result["response"]) > 0


class TestResearchHubRunNotAStub:
    def test_search_web_branch(self, monkeypatch):
        hub = ResearchHub()
        monkeypatch.setattr(hub, "search_web", lambda q: _async_return([{"title": "Result A"}]))
        result = asyncio.run(hub.run({"type": "search_web", "params": {"query": "test"}}))
        _assert_not_a_stub(result)
        assert result["results"] == [{"title": "Result A"}]

    def test_daily_digest_branch(self, monkeypatch):
        hub = ResearchHub()
        monkeypatch.setattr(hub, "daily_digest", lambda: _async_return({"summary": "digest"}))
        result = asyncio.run(hub.run({"type": "daily_digest", "params": {}}))
        _assert_not_a_stub(result)
        assert result["summary"] == "digest"

    def test_search_arxiv_branch(self, monkeypatch):
        hub = ResearchHub()
        monkeypatch.setattr(hub, "search_arxiv", lambda q: _async_return([{"title": "Paper A"}]))
        result = asyncio.run(hub.run({"type": "search_arxiv", "params": {"query": "test"}}))
        _assert_not_a_stub(result)
        assert result["results"] == [{"title": "Paper A"}]

    def test_get_hn_branch(self, monkeypatch):
        hub = ResearchHub()
        monkeypatch.setattr(hub, "get_hn_top", lambda limit=10: _async_return([{"title": "HN story"}]))
        result = asyncio.run(hub.run({"type": "get_hn", "params": {}}))
        _assert_not_a_stub(result)
        assert result["results"] == [{"title": "HN story"}]

    def test_get_india_stocks_branch(self, monkeypatch):
        hub = ResearchHub()
        monkeypatch.setattr(hub, "get_india_stocks", lambda syms: _async_return([{"symbol": "RELIANCE"}]))
        result = asyncio.run(hub.run({"type": "get_india_stocks", "params": {}}))
        _assert_not_a_stub(result)
        assert result["results"] == [{"symbol": "RELIANCE"}]

    def test_find_api_branch(self, monkeypatch):
        hub = ResearchHub()
        monkeypatch.setattr(api_catalog, "search_apis", lambda q, c, limit=10: [{"name": "SomeAPI"}])
        result = asyncio.run(hub.run({"type": "find_api", "params": {"query": "weather"}}))
        _assert_not_a_stub(result)
        assert result["apis"] == [{"name": "SomeAPI"}]
        assert result["count"] == 1

    def test_unknown_type_falls_back_to_digest_not_a_stub(self, monkeypatch):
        hub = ResearchHub()
        monkeypatch.setattr(hub, "daily_digest", lambda: _async_return({"summary": "fallback digest"}))
        result = asyncio.run(hub.run({"type": "some_unrecognized_type", "params": {}}))
        _assert_not_a_stub(result)


async def _async_return(value):
    return value


if __name__ == "__main__":
    async def _smoke():
        hub = ResearchHub()
        hub.get_hn_top = lambda limit=10: _async_return([{"title": "smoke test story"}])
        r = await hub.run({"type": "get_hn", "params": {}})
        assert r.get("response"), "research_hub get_hn stub regression!"
        print("response:", r["response"][:100])

    asyncio.run(_smoke())
    print("test_research_hub_regression.py OK")
