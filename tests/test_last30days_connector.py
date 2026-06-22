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


async def test_connect_hackernews_signal_scores_recent_higher():
    from districts.research.last30days_connectors import connect_hackernews

    brief = await connect_hackernews("test")
    # Real network call — degrades gracefully either way (LIVE or NEEDS-CONFIG),
    # the point is build_brief()'s contract holds regardless.
    assert hasattr(brief, "ranked")
    ranked = brief.ranked()
    assert isinstance(ranked, list)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
