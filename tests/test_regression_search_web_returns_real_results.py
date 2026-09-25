"""`search_web` must search, and the reply must show what it found.

Found 2026-09-25 driving the real /command endpoint: "Find the top 3 AI news stories"
routed correctly to the research district and `search_web` ran, but the reply was
"Done -- search web completed." with no news in it. Two causes:
  1. PermissionGateway._execute_action fetched https://duckduckgo.com/ (the HTML
     home page) with `format=json` and stored the first 500 characters of that page
     as the "response" -- it never returned a single search result. (DuckDuckGo's
     own endpoints now answer HTTP 202 to scripts; the maintained `ddgs` library works.)
  2. `_render_readonly_evidence` knew how to show real evidence for git/arXiv actions
     but had no `search_web` case, so an executed search fell through to the generic
     "Done -- X completed" stub.
"""
import sys
import types

import pytest

from core.api.routers.commands import _render_readonly_evidence
from core.loop.permission_gateway import Action, PermissionGateway

HITS = [
    {"title": "AI News | TechCrunch", "href": "https://techcrunch.com/ai", "body": "Latest AI stories."},
    {"title": "Reuters AI", "href": "https://reuters.com/ai", "body": "Reuters AI coverage."},
]


@pytest.fixture
def fake_ddgs(monkeypatch):
    calls = []

    class FakeDDGS:
        def text(self, query, max_results=5, **_k):
            calls.append((query, max_results))
            return HITS[:max_results]

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))
    return calls


async def test_gateway_search_web_returns_structured_results(fake_ddgs):
    res = await PermissionGateway().execute(Action("search_web", {"query": "ai news"}, "test_agent"))
    assert res.level == "GREEN" and res.executed
    results = res.result["results"]
    assert [r["url"] for r in results] == ["https://techcrunch.com/ai", "https://reuters.com/ai"]
    assert results[0] == {"title": "AI News | TechCrunch", "url": "https://techcrunch.com/ai",
                          "snippet": "Latest AI stories."}
    assert fake_ddgs[0][0] == "ai news"


async def test_gateway_search_web_survives_a_search_failure(monkeypatch):
    class Boom:
        def text(self, *_a, **_k):
            raise RuntimeError("search backend down")

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=Boom))
    res = await PermissionGateway().execute(Action("search_web", {"query": "ai news"}, "test_agent"))
    assert res.result["results"] == []
    assert "search backend down" in res.result["search_error"]


def test_reply_shows_the_real_results_not_a_stub():
    text = _render_readonly_evidence("search_web", {"results": [
        {"title": "AI News | TechCrunch", "url": "https://techcrunch.com/ai", "snippet": "Latest AI stories."}]})
    assert "AI News | TechCrunch" in text
    assert "https://techcrunch.com/ai" in text
    assert "completed" not in text


def test_reply_is_honest_when_nothing_came_back():
    text = _render_readonly_evidence("search_web", {"results": [], "search_error": "search backend down"})
    assert "couldn't" in text.lower() or "no results" in text.lower()
    assert "won't guess" in text.lower()
    assert "completed" not in text
