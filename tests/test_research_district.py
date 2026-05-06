import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import asyncio
import tempfile
from unittest.mock import patch, AsyncMock


# ── WebScout ──────────────────────────────────────────────────────────────────

def test_web_scout_init():
    from agents.districts.research.web_scout import WebScout
    bot = WebScout()
    assert bot.health_points == 500
    assert bot.name == "WebScout"
    assert bot.district == "research"


def test_web_scout_inherits_ghost():
    from agents.districts.research.web_scout import WebScout
    ghost = {"lessons_learned": ["verify sources"], "best_decisions": [], "personality_traits": {}, "generation": 1}
    bot = WebScout(generation=2, ghost=ghost)
    assert "verify sources" in bot.lessons


def test_web_scout_parse_ddg_html_extracts_results():
    from agents.districts.research.web_scout import WebScout
    bot = WebScout()
    # Minimal HTML with DDG result structure
    html = '''
    <div class="result__title">
      <a class="result__a" href="https://example.com">Example Title</a>
    </div>
    <span class="result__snippet">Example snippet text</span>
    '''
    # Parse should not crash even on malformed HTML
    results = bot._parse_ddg_html(html, limit=5)
    assert isinstance(results, list)


def test_web_scout_research_returns_dict():
    from agents.districts.research.web_scout import WebScout
    bot = WebScout()

    async def fake_search(q, max_results=5):
        return [{"title": "Test", "url": "https://example.com", "snippet": "test snippet"}]

    async def fake_fetch(url):
        return "Test page content about Python asyncio"

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Research").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "search", side_effect=fake_search):
            with patch.object(bot, "fetch_page", side_effect=fake_fetch):
                result = asyncio.run(bot.research("asyncio best practices", save_note=True))

    assert isinstance(result, dict)
    assert "query" in result
    assert "results" in result
    assert "summary" in result
    assert result["query"] == "asyncio best practices"


def test_web_scout_research_no_results_deducts_hp():
    from agents.districts.research.web_scout import WebScout
    bot = WebScout()
    initial_hp = bot.health_points

    async def empty_search(q, max_results=5):
        return []

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Research").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "search", side_effect=empty_search):
            asyncio.run(bot.research("nonexistent topic xyz", save_note=False))

    assert bot.health_points < initial_hp


# ── PaperReader ───────────────────────────────────────────────────────────────

def test_paper_reader_init():
    from agents.districts.research.paper_reader import PaperReader
    bot = PaperReader()
    assert bot.health_points == 500
    assert bot.name == "PaperReader"
    assert bot.district == "research"


def test_paper_reader_parse_arxiv_xml():
    from agents.districts.research.paper_reader import PaperReader
    bot = PaperReader()
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2501.00001v1</id>
    <title>Test Paper: Advances in Neural Networks</title>
    <summary>This paper presents advances in neural network architecture.</summary>
    <author><name>Author One</name></author>
    <author><name>Author Two</name></author>
  </entry>
</feed>"""
    papers = bot._parse_arxiv_xml(sample_xml)
    assert len(papers) == 1
    assert "Test Paper" in papers[0]["title"]
    assert "Author One" in papers[0]["authors"]
    assert papers[0]["abstract"] != ""


def test_paper_reader_daily_brief_with_mock():
    from agents.districts.research.paper_reader import PaperReader
    bot = PaperReader()

    fake_papers = [
        {"title": "Test Paper 1", "authors": "Author A", "abstract": "Abstract 1", "url": "https://arxiv.org/abs/1", "id": "1"},
        {"title": "Test Paper 2", "authors": "Author B", "abstract": "Abstract 2", "url": "https://arxiv.org/abs/2", "id": "2"},
    ]

    async def fake_fetch(*args, **kwargs):
        return fake_papers

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Research").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "fetch_recent_papers", side_effect=fake_fetch):
            ok = asyncio.run(bot.daily_brief(max_per_category=2))

    assert ok is True
    assert bot.health_points > 500


def test_paper_reader_search_papers_with_mock():
    from agents.districts.research.paper_reader import PaperReader
    bot = PaperReader()
    fake_papers = [{"title": "Search Result", "authors": "X", "abstract": "Y", "url": "z", "id": "1"}]

    async def fake_fetch(*args, **kwargs):
        return fake_papers

    with patch.object(bot, "_parse_arxiv_xml", return_value=fake_papers):
        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = AsyncMock()
            mock_resp.text = "<xml/>"
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client.return_value)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value.get = AsyncMock(return_value=mock_resp)
            result = asyncio.run(bot.search_papers("transformers", max_results=3))
    assert isinstance(result, list)


# ── NewsAggregator ────────────────────────────────────────────────────────────

def test_news_aggregator_init():
    from agents.districts.research.news_aggregator import NewsAggregator
    bot = NewsAggregator()
    assert bot.health_points == 500
    assert bot.name == "NewsAggregator"
    assert bot.district == "research"


def test_news_aggregator_morning_brief_with_mock():
    from agents.districts.research.news_aggregator import NewsAggregator
    bot = NewsAggregator()

    fake_articles = [
        {"title": f"Article {i}", "source": "Test", "url": f"https://test.com/{i}",
         "description": "desc", "published": "2026-05-07"}
        for i in range(5)
    ]

    async def fake_gather(*args, **kwargs):
        return fake_articles

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Research").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "gather_news", side_effect=fake_gather):
            ok = asyncio.run(bot.morning_brief())

    assert isinstance(ok, bool)


def test_news_aggregator_no_articles_deducts_hp():
    from agents.districts.research.news_aggregator import NewsAggregator
    bot = NewsAggregator()
    initial_hp = bot.health_points

    async def empty_gather(*args, **kwargs):
        return []

    with patch.object(bot, "gather_news", side_effect=empty_gather):
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            bot._obsidian._vault = vault
            asyncio.run(bot.morning_brief())

    assert bot.health_points < initial_hp


# ── RedditMiner ───────────────────────────────────────────────────────────────

def test_reddit_miner_init():
    from agents.districts.research.reddit_miner import RedditMiner
    bot = RedditMiner()
    assert bot.health_points == 500
    assert bot.name == "RedditMiner"
    assert bot.district == "research"


def test_reddit_miner_intelligence_report_with_mock():
    from agents.districts.research.reddit_miner import RedditMiner
    bot = RedditMiner()

    fake_posts = [
        {"title": f"Post {i}", "score": 100 - i, "url": f"https://reddit.com/{i}",
         "flair": "", "comments": 10, "subreddit": "MachineLearning", "selftext": ""}
        for i in range(10)
    ]

    async def fake_mine(*args, **kwargs):
        return fake_posts

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Research").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "mine_all", side_effect=fake_mine):
            ok = asyncio.run(bot.intelligence_report())

    assert ok is True
    assert bot.health_points > 500


def test_reddit_miner_no_posts_deducts_hp():
    from agents.districts.research.reddit_miner import RedditMiner
    bot = RedditMiner()
    initial_hp = bot.health_points

    async def empty_mine(*args, **kwargs):
        return []

    with patch.object(bot, "mine_all", side_effect=empty_mine):
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            bot._obsidian._vault = vault
            asyncio.run(bot.intelligence_report())

    assert bot.health_points < initial_hp


def test_reddit_miner_stores_opportunities():
    from agents.districts.research.reddit_miner import RedditMiner
    bot = RedditMiner()

    fake_posts = [
        {"title": f"Opp {i}", "score": 50, "url": "https://r.com", "flair": "",
         "comments": 5, "subreddit": "entrepreneur", "selftext": ""}
        for i in range(10)
    ]

    async def fake_mine(*args, **kwargs):
        return fake_posts

    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        (vault / "Research").mkdir()
        bot._obsidian._vault = vault

        with patch.object(bot, "mine_all", side_effect=fake_mine):
            asyncio.run(bot.intelligence_report())

    import datetime
    key = f"reddit_opportunities:{datetime.date.today().isoformat()}"
    fact = bot._memory.recall_fact(key)
    assert fact is not None
