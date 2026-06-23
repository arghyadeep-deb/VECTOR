"""
First real connector for districts/research/last30days.py — was a pure
schema with zero live connectors (confirmed via grep before this session,
its own docstring says "live connectors can feed later after SkillSpector
quarantine" — SkillSpector now exists and is registered). HackerNews is a
first-party, already-used-elsewhere VECTOR data source (research_hub.py's
get_hn_top), not third-party skill/prompt text, so SkillSpector scanning
doesn't apply here — it's a plain public JSON API fetch.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_connect_hackernews_builds_brief_from_real_shape(monkeypatch):
    from districts.research.last30days_connectors import connect_hackernews

    async def _fake_get_hn_top(self, limit=20):
        return [
            {"title": "AI breakthrough", "url": "https://hn.example/1", "score": 500, "by": "alice", "comments": 100, "source": "hackernews"},
            {"title": "Old news", "url": "https://hn.example/2", "score": 5, "by": "bob", "comments": 1, "source": "hackernews"},
        ]

    from districts.research.research_hub import ResearchHub
    monkeypatch.setattr(ResearchHub, "get_hn_top", _fake_get_hn_top)

    brief = await connect_hackernews("AI", limit=10)
    assert brief.query == "AI"
    assert len(brief.signals) == 2
    assert all(s.source == "hackernews" for s in brief.signals)
    assert brief.degraded_sources == []


async def test_connect_hackernews_degrades_gracefully_on_failure(monkeypatch):
    from districts.research.last30days_connectors import connect_hackernews
    from districts.research.research_hub import ResearchHub

    async def _broken(self, limit=20):
        raise RuntimeError("network down")

    monkeypatch.setattr(ResearchHub, "get_hn_top", _broken)

    brief = await connect_hackernews("AI")
    assert brief.signals == []
    assert "hackernews" in brief.degraded_sources


async def test_connect_reddit_builds_brief_from_real_shape(monkeypatch):
    from districts.research.last30days_connectors import connect_reddit
    from districts.research.reddit_miner import RedditMiner

    async def _fake_fetch_hot(self, subreddit, limit=10):
        return [
            {"title": "New LLM release", "score": 800, "url": "https://reddit.com/r/x/1",
             "flair": "Discussion", "comments": 50, "subreddit": subreddit, "selftext": ""},
        ]

    monkeypatch.setattr(RedditMiner, "fetch_hot", _fake_fetch_hot)

    brief = await connect_reddit("LLM", subreddits=["MachineLearning"], limit=10)
    assert brief.query == "LLM"
    assert len(brief.signals) == 1
    assert brief.signals[0].source == "reddit"
    assert brief.degraded_sources == []


async def test_connect_reddit_degrades_gracefully_on_failure(monkeypatch):
    from districts.research.last30days_connectors import connect_reddit
    from districts.research.reddit_miner import RedditMiner

    async def _broken(self, subreddit, limit=10):
        raise RuntimeError("reddit unreachable")

    monkeypatch.setattr(RedditMiner, "fetch_hot", _broken)

    brief = await connect_reddit("LLM", subreddits=["MachineLearning"])
    assert brief.signals == []
    assert "reddit" in brief.degraded_sources


async def test_connect_github_builds_brief_from_real_shape(monkeypatch):
    from districts.research.last30days_connectors import connect_github
    from districts.research.research_hub import ResearchHub

    async def _fake_trending(self, language="python", since_days=7, limit=10):
        return [
            {"name": "owner/repo", "description": "cool project", "stars": 1200,
             "language": "python", "url": "https://github.com/owner/repo", "topics": ["ai"], "source": "github_trending"},
        ]

    monkeypatch.setattr(ResearchHub, "get_github_trending", _fake_trending)

    brief = await connect_github("AI tools", language="python", limit=10)
    assert brief.query == "AI tools"
    assert len(brief.signals) == 1
    assert brief.signals[0].source == "github"
    assert brief.degraded_sources == []


async def test_connect_github_degrades_gracefully_on_failure(monkeypatch):
    from districts.research.last30days_connectors import connect_github
    from districts.research.research_hub import ResearchHub

    async def _broken(self, language="python", since_days=7, limit=10):
        raise RuntimeError("github unreachable")

    monkeypatch.setattr(ResearchHub, "get_github_trending", _broken)

    brief = await connect_github("AI tools")
    assert brief.signals == []
    assert "github" in brief.degraded_sources


async def test_connect_all_fans_out_and_merges_sources(monkeypatch):
    """The doc's own 'source fanout' idea — one combined brief from all
    connectors, partial failures don't take down the whole brief."""
    from districts.research import last30days_connectors as mod

    async def _hn_ok(query, limit=20):
        return mod.build_brief(query, [mod.RecentSignal(source="hackernews", title="x", url="u", published_at="2026-06-23T00:00:00+00:00")])

    async def _reddit_broken(query, subreddits=None, limit=10):
        return mod.build_brief(query, [], degraded_sources=["reddit"])

    async def _github_ok(query, language="python", limit=10):
        return mod.build_brief(query, [mod.RecentSignal(source="github", title="y", url="u2", published_at="2026-06-23T00:00:00+00:00")])

    monkeypatch.setattr(mod, "connect_hackernews", _hn_ok)
    monkeypatch.setattr(mod, "connect_reddit", _reddit_broken)
    monkeypatch.setattr(mod, "connect_github", _github_ok)

    brief = await mod.connect_all("test query")
    assert brief.query == "test query"
    assert len(brief.signals) == 2
    assert {"hackernews", "github"} <= {s.source for s in brief.signals}
    assert "reddit" in brief.degraded_sources


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
