"""Repo integration (docs/repo_analysis/youtube-automation-agent.md):
trending harvest + competitor analysis. No YOUTUBE_DATA_API_KEY is
configured in this environment — these tests verify the pure
extract_keywords() function and the graceful {"status": "simulated"}
degradation path, mirroring uploader.py's existing fallback pattern.
"""
import asyncio

from districts.content.youtube_trends import YouTubeTrendScout, extract_keywords


def test_extract_keywords_drops_stopwords():
    kws = extract_keywords(["The Best Python Tutorial for Beginners"])
    words = [w for w, _ in kws]
    assert "the" not in words
    assert "for" not in words
    assert "python" in words


def test_extract_keywords_ranks_by_frequency():
    kws = extract_keywords([
        "Python Tricks for Beginners",
        "Python Tips and Tricks",
        "Advanced Python Tricks",
    ])
    assert kws[0][0] == "python" or kws[0][1] >= 2


def test_extract_keywords_empty_input():
    assert extract_keywords([]) == []


def test_extract_keywords_respects_top_n():
    titles = [f"Unique Word Number {i} Here" for i in range(30)]
    kws = extract_keywords(titles, top_n=5)
    assert len(kws) <= 5


def test_scout_fetch_trending_simulated_without_api_key():
    scout = YouTubeTrendScout()
    result = scout.fetch_trending(region="US")
    assert result["status"] == "simulated"
    assert result["videos"] == []
    assert "note" in result


def test_scout_analyze_competitor_simulated_without_api_key():
    scout = YouTubeTrendScout()
    result = scout.analyze_competitor("UC_some_channel")
    assert result["status"] == "simulated"
    assert result["videos"] == []


def test_scout_analyze_competitor_requires_channel_id_via_run():
    scout = YouTubeTrendScout()
    result = asyncio.run(scout.run({"type": "youtube_competitor", "params": {}}))
    assert result["status"] == "error"
    assert "channel_id" in result["error"]


def test_scout_run_dispatches_trending_type():
    scout = YouTubeTrendScout()
    result = asyncio.run(scout.run({"type": "youtube_trending", "params": {"region": "GB"}}))
    assert result["status"] == "simulated"
    assert result["region"] == "GB"


def test_scout_run_dispatches_competitor_type():
    scout = YouTubeTrendScout()
    result = asyncio.run(scout.run({"type": "youtube_competitor", "params": {"channel_id": "UCabc"}}))
    assert result["status"] == "simulated"
    assert result["channel_id"] == "UCabc"


def test_scout_run_unknown_type_returns_error_not_fake_success():
    scout = YouTubeTrendScout()
    result = asyncio.run(scout.run({"type": "totally_unknown", "params": {}}))
    assert result["status"] == "error"
    assert "supported" in result


def test_scout_never_raises_without_credentials():
    """Mirrors uploader.py's contract: missing creds degrades, never raises."""
    scout = YouTubeTrendScout()
    scout.fetch_trending()
    scout.analyze_competitor("any_channel")
