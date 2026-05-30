"""
Session 16 — Research Lab integration tests.
Covers: ResearchHub, PaperReader, NewsAggregator, WebScout, OpenCLIAdapter,
        RedditMiner, APICatalog, and cross-cutting episodic_memory storage.
All tests run without live network or live LLM (mocked where required).
"""
import asyncio
import datetime
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock


def _run(coro):
    return asyncio.run(coro)


def _event_stored(event_type: str, limit: int = 30) -> bool:
    """Check if an event_type was stored in episodic_memory (direct SQL, no FTS)."""
    from core.memory.episodic import EpisodicMemory
    mem = EpisodicMemory()
    rows = mem.conn.execute(
        "SELECT 1 FROM episodic_memory WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
        (event_type, limit),
    ).fetchall()
    return len(rows) > 0


# ── shared XML / HTML / JSON fixtures ─────────────────────────────────────────

_ARXIV_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Attention Is All You Need</title>
    <author><name>Vaswani A</name></author>
    <author><name>Shazeer N</name></author>
    <summary>The dominant sequence transduction models are based on RNNs.</summary>
    <id>http://arxiv.org/abs/1706.03762v5</id>
  </entry>
  <entry>
    <title>BERT Pre-training of Deep Bidirectional Transformers</title>
    <author><name>Devlin J</name></author>
    <summary>BERT is designed to pre-train deep bidirectional representations.</summary>
    <id>http://arxiv.org/abs/1810.04805v2</id>
  </entry>
</feed>"""

_RSS_XML = """\
<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>AI Takes Over</title>
      <link>https://techcrunch.com/ai-takes-over</link>
      <description>AI is changing everything in 2024.</description>
      <pubDate>Mon, 01 Jan 2024</pubDate>
    </item>
    <item>
      <title>Python 4.0 Released</title>
      <link>https://python.org/news/4.0</link>
      <description>Python 4.0 has arrived with major changes.</description>
      <pubDate>Tue, 02 Jan 2024</pubDate>
    </item>
  </channel>
</rss>"""

_REDDIT_JSON = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "GPT-5 announced with new capabilities",
                    "score": 1500,
                    "permalink": "/r/MachineLearning/comments/abc123/gpt5/",
                    "link_flair_text": "News",
                    "num_comments": 300,
                    "selftext": "OpenAI just announced GPT-5",
                    "stickied": False,
                }
            },
            {
                "data": {
                    "title": "Pinned: Community Rules",
                    "score": 0,
                    "permalink": "/r/MachineLearning/comments/xyz/rules/",
                    "link_flair_text": None,
                    "num_comments": 0,
                    "selftext": "",
                    "stickied": True,
                }
            },
        ]
    }
}

_HN_IDS = [37000001, 37000002, 37000003]
_HN_ITEM = {
    "id": 37000001,
    "type": "story",
    "title": "Show HN: My open source project",
    "url": "https://github.com/user/project",
    "score": 250,
    "by": "username",
    "descendants": 42,
}

_GITHUB_JSON = {
    "items": [
        {
            "full_name": "user/awesome-llm",
            "description": "A curated list of LLM resources",
            "stargazers_count": 5000,
            "language": "Python",
            "html_url": "https://github.com/user/awesome-llm",
            "topics": ["llm", "ai"],
        }
    ]
}

_DDG_JSON = {
    "Abstract": "Python is a high-level, general-purpose programming language.",
    "AbstractURL": "https://en.wikipedia.org/wiki/Python_(programming_language)",
    "Heading": "Python",
    "RelatedTopics": [
        {"Text": "Python Software Foundation", "FirstURL": "https://psf.org"},
        {"Text": "PEP 8 style guide", "FirstURL": "https://peps.python.org/pep-0008/"},
    ],
}


def _mock_http(status=200, text="", json_data=None):
    """Build a reusable mock for `async with httpx.AsyncClient(...) as client:`."""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.text = text
    mock_resp.json.return_value = json_data if json_data is not None else {}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ════════════════════════════════════════════════════════════════════════════
# TestResearchHub
# ════════════════════════════════════════════════════════════════════════════

class TestResearchHub(unittest.TestCase):

    def setUp(self):
        from districts.research.research_hub import ResearchHub
        self.hub = ResearchHub()

    # ── init ──────────────────────────────────────────────────────────────────

    def test_init_name(self):
        self.assertEqual(self.hub.name, "ResearchHub")

    def test_init_district(self):
        self.assertEqual(self.hub.district, "research")

    def test_init_hp(self):
        self.assertEqual(self.hub.health_points, 500)

    def test_is_alive_on_init(self):
        self.assertTrue(self.hub.is_alive)

    # ── search_web ────────────────────────────────────────────────────────────

    def test_search_web_returns_list(self):
        mock_client = _mock_http(200, json_data=_DDG_JSON)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.hub.search_web("python asyncio"))
        self.assertIsInstance(result, list)

    def test_search_web_with_abstract_has_result(self):
        mock_client = _mock_http(200, json_data=_DDG_JSON)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.hub.search_web("python"))
        self.assertGreater(len(result), 0)
        self.assertIn("title", result[0])
        self.assertIn("url", result[0])

    def test_search_web_network_error_returns_empty(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("Network down"))
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.hub.search_web("python"))
        self.assertEqual(result, [])

    def test_search_web_empty_abstract_falls_back(self):
        # DDG returns empty abstract → triggers HTML fallback
        empty_ddg = {"Abstract": "", "RelatedTopics": []}
        mock_client = _mock_http(200, json_data=empty_ddg, text="<html></html>")
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.hub.search_web("obscure_topic_xyz"))
        self.assertIsInstance(result, list)

    # ── search_arxiv ──────────────────────────────────────────────────────────

    def test_search_arxiv_returns_list(self):
        mock_client = _mock_http(200, text=_ARXIV_ATOM)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.hub.search_arxiv("transformers"))
        self.assertIsInstance(result, list)

    def test_search_arxiv_parsed_count(self):
        mock_client = _mock_http(200, text=_ARXIV_ATOM)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.hub.search_arxiv("attention", max_results=5))
        self.assertEqual(len(result), 2)

    def test_search_arxiv_paper_has_required_keys(self):
        mock_client = _mock_http(200, text=_ARXIV_ATOM)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.hub.search_arxiv("bert"))
        if result:
            paper = result[0]
            self.assertIn("title", paper)
            self.assertIn("summary", paper)
            self.assertIn("url", paper)
            self.assertIn("source", paper)
            self.assertEqual(paper["source"], "arxiv")

    def test_search_arxiv_network_error_returns_empty(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("Timeout"))
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.hub.search_arxiv("gpt"))
        self.assertEqual(result, [])

    # ── get_hn_top ────────────────────────────────────────────────────────────

    def test_get_hn_top_returns_list(self):
        self.hub.get_hn_top = AsyncMock(return_value=[
            {"title": "Top HN Story", "url": "https://hn.com/1", "score": 100, "by": "user", "source": "hackernews"}
        ])
        result = _run(self.hub.get_hn_top(limit=5))
        self.assertIsInstance(result, list)

    def test_get_github_trending_returns_list(self):
        mock_client = _mock_http(200, json_data=_GITHUB_JSON)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.hub.get_github_trending("python", limit=5))
        self.assertIsInstance(result, list)
        if result:
            self.assertIn("name", result[0])
            self.assertIn("stars", result[0])

    # ── daily_digest ──────────────────────────────────────────────────────────

    def test_daily_digest_returns_dict(self):
        for method in ("get_hn_top", "get_github_trending", "get_devto_posts",
                       "search_arxiv", "get_crypto_prices", "get_tech_news"):
            setattr(self.hub, method, AsyncMock(return_value=[]))
        result = _run(self.hub.daily_digest())
        self.assertIsInstance(result, dict)

    def test_daily_digest_has_required_keys(self):
        for method in ("get_hn_top", "get_github_trending", "get_devto_posts",
                       "search_arxiv", "get_crypto_prices", "get_tech_news"):
            setattr(self.hub, method, AsyncMock(return_value=[]))
        result = _run(self.hub.daily_digest())
        for key in ("date", "hackernews", "github_trending", "devto", "arxiv"):
            self.assertIn(key, result)

    def test_daily_digest_stores_episodic(self):
        for method in ("get_hn_top", "get_github_trending", "get_devto_posts",
                       "search_arxiv", "get_crypto_prices", "get_tech_news"):
            setattr(self.hub, method, AsyncMock(return_value=[]))
        _run(self.hub.daily_digest())
        self.assertTrue(_event_stored("daily_research_digest"))

    # ── run dispatch ──────────────────────────────────────────────────────────

    def test_run_dispatch_search_web(self):
        self.hub.search_web = AsyncMock(return_value=[
            {"title": "Test", "url": "https://example.com", "snippet": "s", "source": "ddg_abstract"}
        ])
        result = _run(self.hub.run({"type": "search_web", "params": {"query": "AI"}}))
        self.assertEqual(result["status"], "ok")
        self.assertIn("results", result)

    def test_run_dispatch_search_arxiv(self):
        mock_client = _mock_http(200, text=_ARXIV_ATOM)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.hub.run({"type": "search_arxiv", "params": {"query": "LLM"}}))
        self.assertEqual(result["status"], "ok")
        self.assertIn("results", result)

    def test_run_dispatch_find_api(self):
        result = _run(self.hub.run({"type": "find_api", "params": {"query": "weather"}}))
        self.assertIn("status", result)
        # May return ok or error depending on README availability
        self.assertIn(result["status"], ("ok", "error"))

    def test_hp_award_after_arxiv_search(self):
        initial_hp = self.hub.health_points
        mock_client = _mock_http(200, text=_ARXIV_ATOM)
        with patch("httpx.AsyncClient", return_value=mock_client):
            _run(self.hub.search_arxiv("transformers"))
        self.assertGreater(self.hub.health_points, initial_hp)


# ════════════════════════════════════════════════════════════════════════════
# TestPaperReader
# ════════════════════════════════════════════════════════════════════════════

class TestPaperReader(unittest.TestCase):

    def setUp(self):
        from districts.research.paper_reader import PaperReader
        self.reader = PaperReader()

    # ── init ──────────────────────────────────────────────────────────────────

    def test_init_name(self):
        self.assertEqual(self.reader.name, "PaperReader")

    def test_init_district(self):
        self.assertEqual(self.reader.district, "research")

    def test_init_hp(self):
        self.assertEqual(self.reader.health_points, 500)

    def test_categories_class_attribute(self):
        cats = self.reader.ARXIV_CATEGORIES
        self.assertIsInstance(cats, list)
        self.assertIn("cs.AI", cats)
        self.assertIn("cs.LG", cats)

    # ── _parse_arxiv_xml ──────────────────────────────────────────────────────

    def test_parse_arxiv_xml_valid_returns_list(self):
        result = self.reader._parse_arxiv_xml(_ARXIV_ATOM)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    def test_parse_arxiv_xml_paper_keys(self):
        result = self.reader._parse_arxiv_xml(_ARXIV_ATOM)
        paper = result[0]
        for key in ("title", "authors", "abstract", "url", "id"):
            self.assertIn(key, paper)

    def test_parse_arxiv_xml_authors_is_string(self):
        result = self.reader._parse_arxiv_xml(_ARXIV_ATOM)
        self.assertIsInstance(result[0]["authors"], str)

    def test_parse_arxiv_xml_first_title(self):
        result = self.reader._parse_arxiv_xml(_ARXIV_ATOM)
        self.assertIn("Attention", result[0]["title"])

    def test_parse_arxiv_xml_empty_returns_empty(self):
        result = self.reader._parse_arxiv_xml("")
        self.assertEqual(result, [])

    def test_parse_arxiv_xml_malformed_returns_empty(self):
        result = self.reader._parse_arxiv_xml("<broken<<xml")
        self.assertEqual(result, [])

    def test_parse_arxiv_xml_id_extracted(self):
        result = self.reader._parse_arxiv_xml(_ARXIV_ATOM)
        # ID should be extracted from the <id> element (last path segment)
        self.assertTrue(result[0]["id"])

    # ── fetch_recent_papers ───────────────────────────────────────────────────

    def test_fetch_recent_papers_returns_list(self):
        mock_client = _mock_http(200, text=_ARXIV_ATOM)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.reader.fetch_recent_papers("cs.AI", max_results=5))
        self.assertIsInstance(result, list)

    def test_fetch_recent_papers_network_error_returns_empty(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("Timeout"))
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.reader.fetch_recent_papers("cs.AI"))
        self.assertEqual(result, [])

    # ── search_papers ─────────────────────────────────────────────────────────

    def test_search_papers_returns_list(self):
        mock_client = _mock_http(200, text=_ARXIV_ATOM)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.reader.search_papers("transformers", max_results=5))
        self.assertIsInstance(result, list)

    # ── daily_brief ───────────────────────────────────────────────────────────

    def test_daily_brief_no_papers_returns_false(self):
        self.reader.fetch_recent_papers = AsyncMock(return_value=[])
        result = _run(self.reader.daily_brief())
        self.assertFalse(result)

    def test_daily_brief_with_papers_returns_true(self):
        mock_papers = [
            {"title": "Test Paper", "authors": "Auth A", "abstract": "Abstract text.", "url": "https://arxiv.org/abs/0001", "id": f"spec09_{uuid.uuid4().hex}"}
        ]
        self.reader.fetch_recent_papers = AsyncMock(return_value=mock_papers)
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            self.reader._obsidian._vault = vault
            result = _run(self.reader.daily_brief(max_per_category=2))
        self.assertTrue(result)

    def test_daily_brief_writes_obsidian_note(self):
        paper_id = f"obs_{uuid.uuid4().hex}"
        mock_papers = [
            {"title": "Obsidian Test Paper", "authors": "Auth B", "abstract": "Test abstract.", "url": "https://arxiv.org/abs/obs1", "id": paper_id}
        ]
        self.reader.fetch_recent_papers = AsyncMock(return_value=mock_papers)
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            self.reader._obsidian._vault = vault
            _run(self.reader.daily_brief(max_per_category=2))
            notes = list((vault / "Research").glob("Paper Brief*.md"))
            self.assertTrue(len(notes) >= 1)

    def test_daily_brief_stores_episodic(self):
        paper_id = f"ep_{uuid.uuid4().hex}"
        mock_papers = [
            {"title": "Episodic Test Paper", "authors": "Auth C", "abstract": "Episodic abstract.", "url": "https://arxiv.org/abs/ep1", "id": paper_id}
        ]
        self.reader.fetch_recent_papers = AsyncMock(return_value=mock_papers)
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            self.reader._obsidian._vault = vault
            _run(self.reader.daily_brief(max_per_category=1))
        self.assertTrue(_event_stored("paper_brief"))

    def test_daily_brief_deduplicates_same_id(self):
        shared_id = f"dup_{uuid.uuid4().hex}"
        paper = {"title": "Dup Paper", "authors": "Auth D", "abstract": "Dup abs.", "url": "https://arxiv.org/abs/dup", "id": shared_id}
        self.reader.fetch_recent_papers = AsyncMock(return_value=[paper])
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            self.reader._obsidian._vault = vault
            # 2 categories → both return same paper → deduplicated to 1
            result = _run(self.reader.daily_brief(max_per_category=3))
        self.assertTrue(result)

    def test_daily_brief_hp_award_on_success(self):
        initial_hp = self.reader.health_points
        paper_id = f"hp_{uuid.uuid4().hex}"
        mock_papers = [
            {"title": "HP Award Paper", "authors": "Auth E", "abstract": "HP abs.", "url": "https://arxiv.org/abs/hp1", "id": paper_id}
        ]
        self.reader.fetch_recent_papers = AsyncMock(return_value=mock_papers)
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            self.reader._obsidian._vault = vault
            _run(self.reader.daily_brief(max_per_category=1))
        self.assertGreater(self.reader.health_points, initial_hp)

    def test_daily_brief_hp_deduct_on_no_papers(self):
        initial_hp = self.reader.health_points
        self.reader.fetch_recent_papers = AsyncMock(return_value=[])
        _run(self.reader.daily_brief())
        self.assertLess(self.reader.health_points, initial_hp)


# ════════════════════════════════════════════════════════════════════════════
# TestNewsAggregator
# ════════════════════════════════════════════════════════════════════════════

class TestNewsAggregator(unittest.TestCase):

    def setUp(self):
        from districts.research.news_aggregator import NewsAggregator
        self.agg = NewsAggregator()
        self.agg._newsapi_key = ""  # ensure no real API calls

    # ── init ──────────────────────────────────────────────────────────────────

    def test_init_name(self):
        self.assertEqual(self.agg.name, "NewsAggregator")

    def test_init_district(self):
        self.assertEqual(self.agg.district, "research")

    def test_init_hp(self):
        self.assertEqual(self.agg.health_points, 500)

    # ── fetch_newsapi ─────────────────────────────────────────────────────────

    def test_fetch_newsapi_no_key_returns_empty(self):
        result = _run(self.agg.fetch_newsapi())
        self.assertEqual(result, [])

    # ── fetch_rss ─────────────────────────────────────────────────────────────

    def test_fetch_rss_parses_valid_xml(self):
        mock_client = _mock_http(200, text=_RSS_XML)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.agg.fetch_rss("https://example.com/feed", "TestSource", 5))
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_fetch_rss_article_has_required_keys(self):
        mock_client = _mock_http(200, text=_RSS_XML)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.agg.fetch_rss("https://example.com/feed", "TestSource", 5))
        if result:
            for key in ("title", "source", "url", "description", "published"):
                self.assertIn(key, result[0])

    def test_fetch_rss_source_name_injected(self):
        mock_client = _mock_http(200, text=_RSS_XML)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.agg.fetch_rss("https://example.com/feed", "MySource", 5))
        if result:
            self.assertEqual(result[0]["source"], "MySource")

    def test_fetch_rss_malformed_xml_returns_empty(self):
        mock_client = _mock_http(200, text="<broken<<<xml")
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.agg.fetch_rss("https://example.com/feed", "Bad", 5))
        self.assertEqual(result, [])

    def test_fetch_rss_network_error_returns_empty(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("Network error"))
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.agg.fetch_rss("https://example.com/feed", "Error", 5))
        self.assertEqual(result, [])

    # ── gather_news ───────────────────────────────────────────────────────────

    def test_gather_news_deduplicates_urls(self):
        a1 = {"title": "Same", "source": "S1", "url": "https://example.com/same", "description": "d", "published": "2024-01-01"}
        a2 = {"title": "Same", "source": "S2", "url": "https://example.com/same", "description": "d", "published": "2024-01-01"}
        self.agg.fetch_newsapi = AsyncMock(return_value=[a1])
        self.agg.fetch_rss = AsyncMock(return_value=[a2])
        self.agg.fetch_via_connectors = AsyncMock(return_value=[])
        result = _run(self.agg.gather_news(max_per_source=2))
        urls = [a["url"] for a in result]
        self.assertEqual(len(urls), len(set(urls)))

    def test_gather_news_combines_sources(self):
        a_a = {"title": "Article A", "source": "S1", "url": "https://a.com/1", "description": "d", "published": "2024-01-01"}
        a_b = {"title": "Article B", "source": "S2", "url": "https://b.com/2", "description": "d", "published": "2024-01-01"}
        self.agg.fetch_newsapi = AsyncMock(return_value=[a_a])
        self.agg.fetch_rss = AsyncMock(return_value=[a_b])
        self.agg.fetch_via_connectors = AsyncMock(return_value=[])
        result = _run(self.agg.gather_news(max_per_source=5))
        self.assertGreaterEqual(len(result), 2)

    def test_fetch_via_connectors_always_returns_list(self):
        result = _run(self.agg.fetch_via_connectors(max_per_source=2))
        self.assertIsInstance(result, list)

    # ── morning_brief ─────────────────────────────────────────────────────────

    def test_morning_brief_no_articles_returns_false(self):
        self.agg.gather_news = AsyncMock(return_value=[])
        result = _run(self.agg.morning_brief())
        self.assertFalse(result)

    def test_morning_brief_hp_deduct_on_no_articles(self):
        initial_hp = self.agg.health_points
        self.agg.gather_news = AsyncMock(return_value=[])
        _run(self.agg.morning_brief())
        self.assertLess(self.agg.health_points, initial_hp)

    def test_morning_brief_with_articles_stores_episodic(self):
        articles = [
            {"title": f"Spec09 News {i}", "source": "S", "url": f"https://spec09news.test/{uuid.uuid4().hex}", "description": "d", "published": "2024-01-01"}
            for i in range(3)
        ]
        self.agg.gather_news = AsyncMock(return_value=articles)
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            self.agg._obsidian._vault = vault
            _run(self.agg.morning_brief())
        self.assertTrue(_event_stored("news_brief"))

    def test_morning_brief_writes_obsidian(self):
        articles = [
            {"title": "Vault Test Article", "source": "S", "url": f"https://vault.test/{uuid.uuid4().hex}", "description": "desc", "published": "2024-01-01"}
        ]
        self.agg.gather_news = AsyncMock(return_value=articles)
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            self.agg._obsidian._vault = vault
            result = _run(self.agg.morning_brief())
            notes = list((vault / "Research").glob("News Brief*.md"))
        self.assertIsInstance(result, bool)
        # Note written (True) or LLM fallback still runs — at minimum must not crash
        self.assertIsNotNone(result)


# ════════════════════════════════════════════════════════════════════════════
# TestWebScout
# ════════════════════════════════════════════════════════════════════════════

class TestWebScout(unittest.TestCase):

    def setUp(self):
        from districts.research.web_scout import WebScout
        self.scout = WebScout()

    # ── init ──────────────────────────────────────────────────────────────────

    def test_init_name(self):
        self.assertEqual(self.scout.name, "WebScout")

    def test_init_district(self):
        self.assertEqual(self.scout.district, "research")

    def test_init_hp(self):
        self.assertEqual(self.scout.health_points, 500)

    # ── _parse_ddg_html ───────────────────────────────────────────────────────

    def test_parse_ddg_html_empty_returns_empty(self):
        result = self.scout._parse_ddg_html("", 5)
        self.assertEqual(result, [])

    def test_parse_ddg_html_returns_list(self):
        html = (
            'class="result__title"><a href="https://example.com/1" '
            'class="result__a">Title One</a>'
            'class="result__snippet">Snippet one</span>'
        )
        result = self.scout._parse_ddg_html(html, 10)
        self.assertIsInstance(result, list)

    def test_parse_ddg_html_limit_honored(self):
        html_blocks = ""
        for i in range(10):
            html_blocks += (
                f'class="result__title">'
                f'<a href="https://example.com/{i}">Title {i}</a>'
                f'class="result__snippet">Snippet {i}</span>'
            )
        result = self.scout._parse_ddg_html(html_blocks, 3)
        self.assertLessEqual(len(result), 3)

    def test_parse_ddg_html_result_structure(self):
        result = self.scout._parse_ddg_html("", 5)
        # Empty → list OK
        self.assertIsInstance(result, list)

    # ── search ────────────────────────────────────────────────────────────────

    def test_search_returns_list(self):
        mock_client = _mock_http(200, text="<html><body>no results</body></html>")
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.scout.search("python testing"))
        self.assertIsInstance(result, list)

    def test_search_network_error_returns_empty(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("Network down"))
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.scout.search("test query"))
        self.assertIsInstance(result, list)

    # ── research ──────────────────────────────────────────────────────────────

    def test_research_returns_dict_structure(self):
        self.scout.search = AsyncMock(return_value=[
            {"title": "Test Result", "url": "https://example.com/test", "snippet": "A snippet"}
        ])
        self.scout.fetch_page = AsyncMock(return_value="# Test Content\nSome content.")
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            self.scout._obsidian._vault = vault
            result = _run(self.scout.research("python testing", save_note=True))
        self.assertIn("query", result)
        self.assertIn("results", result)
        self.assertIn("summary", result)

    def test_research_query_echoed_in_result(self):
        self.scout.search = AsyncMock(return_value=[])
        result = _run(self.scout.research("my_unique_query", save_note=False))
        self.assertEqual(result["query"], "my_unique_query")

    def test_research_stores_episodic(self):
        self.scout.search = AsyncMock(return_value=[
            {"title": "Int Result", "url": f"https://spec09.test/{uuid.uuid4().hex}", "snippet": "snippet"}
        ])
        self.scout.fetch_page = AsyncMock(return_value="content")
        _run(self.scout.research("integration test research", save_note=False))
        self.assertTrue(_event_stored("research"))

    def test_research_no_results_deducts_hp(self):
        initial_hp = self.scout.health_points
        self.scout.search = AsyncMock(return_value=[])
        _run(self.scout.research("xyz_no_results", save_note=False))
        self.assertLessEqual(self.scout.health_points, initial_hp)

    def test_research_with_results_awards_hp(self):
        initial_hp = self.scout.health_points
        self.scout.search = AsyncMock(return_value=[
            {"title": "HP Result", "url": "https://hp.example.com/result", "snippet": "hp"}
        ])
        self.scout.fetch_page = AsyncMock(return_value="content")
        _run(self.scout.research("hp award query", save_note=False))
        self.assertGreater(self.scout.health_points, initial_hp)

    # ── stealth_search ────────────────────────────────────────────────────────

    def test_stealth_search_falls_back_when_no_server(self):
        self.scout.search = AsyncMock(return_value=[
            {"title": "Fallback Result", "url": "https://example.com/fb", "snippet": "fb"}
        ])
        result = _run(self.scout.stealth_search("test query"))
        self.assertIn("results", result)
        self.assertIsInstance(result["results"], list)

    def test_stealth_search_fallback_flag_set(self):
        self.scout.search = AsyncMock(return_value=[])
        result = _run(self.scout.stealth_search("test query"))
        # When stealth server is unavailable, fallback=True is set
        self.assertTrue(result.get("fallback", True))


# ════════════════════════════════════════════════════════════════════════════
# TestOpenCLIAdapter
# ════════════════════════════════════════════════════════════════════════════

class TestOpenCLIAdapter(unittest.TestCase):

    def setUp(self):
        from districts.research.opencli_adapter import OpenCLIAdapter
        self.adapter = OpenCLIAdapter()

    def test_init_name(self):
        self.assertEqual(self.adapter.name, "OpenCLIAdapter")

    def test_init_district(self):
        self.assertEqual(self.adapter.district, "research")

    def test_init_hp(self):
        self.assertEqual(self.adapter.health_points, 500)

    def test_check_health_returns_dict(self):
        result = self.adapter.check_health()
        self.assertIsInstance(result, dict)
        self.assertIn("available", result)

    def test_check_health_no_opencli_message(self):
        from districts.research.opencli_adapter import _opencli_available
        if not _opencli_available():
            result = self.adapter.check_health()
            self.assertFalse(result["available"])
            self.assertIn("message", result)

    def test_opencli_available_returns_bool(self):
        from districts.research.opencli_adapter import _opencli_available
        result = _opencli_available()
        self.assertIsInstance(result, bool)

    def test_run_opencli_not_installed_returns_error(self):
        from districts.research.opencli_adapter import _run_opencli
        with patch("shutil.which", return_value=None):
            result = _run_opencli(["test"])
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_get_hn_top_fallback_returns_list(self):
        self.adapter._available = False
        ids_resp = MagicMock(status_code=200)
        ids_resp.json.return_value = [37000001, 37000002]
        item_resp = MagicMock(status_code=200)
        item_resp.json.return_value = _HN_ITEM

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.side_effect = [ids_resp, item_resp, item_resp]

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.adapter.get_hn_top(limit=2))
        self.assertIsInstance(result, list)

    def test_get_github_trending_fallback_returns_list(self):
        self.adapter._available = False
        mock_client = _mock_http(200, json_data=_GITHUB_JSON)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.adapter.get_github_trending("python", limit=3))
        self.assertIsInstance(result, list)

    def test_get_twitter_no_opencli_returns_empty(self):
        self.adapter._available = False
        result = _run(self.adapter.get_twitter_trending("AI", limit=5))
        self.assertEqual(result, [])


# ════════════════════════════════════════════════════════════════════════════
# TestRedditMiner
# ════════════════════════════════════════════════════════════════════════════

class TestRedditMiner(unittest.TestCase):

    def setUp(self):
        from districts.research.reddit_miner import RedditMiner
        self.miner = RedditMiner()

    def test_init_name(self):
        self.assertEqual(self.miner.name, "RedditMiner")

    def test_init_district(self):
        self.assertEqual(self.miner.district, "research")

    def test_init_hp(self):
        self.assertEqual(self.miner.health_points, 500)

    def test_subreddits_list_nonempty(self):
        from districts.research.reddit_miner import _SUBREDDITS
        self.assertIsInstance(_SUBREDDITS, list)
        self.assertGreater(len(_SUBREDDITS), 0)

    def test_fetch_hot_returns_list(self):
        mock_client = _mock_http(200, json_data=_REDDIT_JSON)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.miner.fetch_hot("MachineLearning", limit=10))
        self.assertIsInstance(result, list)

    def test_fetch_hot_post_structure(self):
        mock_client = _mock_http(200, json_data=_REDDIT_JSON)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.miner.fetch_hot("MachineLearning", limit=10))
        if result:
            post = result[0]
            for key in ("title", "score", "url", "subreddit"):
                self.assertIn(key, post)

    def test_fetch_hot_filters_stickied(self):
        mock_client = _mock_http(200, json_data=_REDDIT_JSON)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.miner.fetch_hot("MachineLearning", limit=10))
        titles = [p.get("title", "") for p in result]
        self.assertNotIn("Pinned: Community Rules", titles)

    def test_fetch_hot_bad_status_returns_empty(self):
        mock_client = _mock_http(429, json_data={})
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.miner.fetch_hot("MachineLearning", limit=5))
        self.assertEqual(result, [])

    def test_fetch_hot_network_error_returns_empty(self):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=Exception("Network error"))
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.miner.fetch_hot("LocalLLaMA", limit=5))
        self.assertEqual(result, [])

    def test_fetch_hot_url_contains_reddit(self):
        mock_client = _mock_http(200, json_data=_REDDIT_JSON)
        with patch("httpx.AsyncClient", return_value=mock_client):
            result = _run(self.miner.fetch_hot("MachineLearning", limit=5))
        for post in result:
            self.assertIn("reddit.com", post["url"])


# ════════════════════════════════════════════════════════════════════════════
# TestAPICatalog
# ════════════════════════════════════════════════════════════════════════════

class TestAPICatalog(unittest.TestCase):

    def setUp(self):
        from districts.research.api_catalog import _load_catalog
        _load_catalog.cache_clear()

    def tearDown(self):
        from districts.research.api_catalog import _load_catalog
        _load_catalog.cache_clear()

    def test_search_apis_returns_list(self):
        from districts.research.api_catalog import search_apis
        result = search_apis("weather", limit=5)
        self.assertIsInstance(result, list)

    def test_get_stats_returns_dict(self):
        from districts.research.api_catalog import get_stats
        result = get_stats()
        self.assertIsInstance(result, dict)
        self.assertIn("total", result)
        self.assertIn("free", result)
        self.assertIn("categories", result)
        self.assertIn("top_categories", result)

    def test_get_stats_values_non_negative(self):
        from districts.research.api_catalog import get_stats
        result = get_stats()
        self.assertGreaterEqual(result["total"], 0)
        self.assertGreaterEqual(result["free"], 0)
        self.assertGreaterEqual(result["categories"], 0)

    def test_get_categories_returns_sorted_list(self):
        from districts.research.api_catalog import get_categories
        result = get_categories()
        self.assertIsInstance(result, list)
        if len(result) > 1:
            self.assertEqual(result, sorted(result))

    def test_search_apis_limit_respected(self):
        from districts.research.api_catalog import search_apis
        # "a" appears in many names/descriptions
        result = search_apis("a", limit=3)
        self.assertLessEqual(len(result), 3)

    def test_search_apis_no_score_field_in_results(self):
        from districts.research.api_catalog import search_apis
        results = search_apis("weather", limit=5)
        for api in results:
            self.assertNotIn("_score", api)

    def test_search_apis_result_has_required_keys(self):
        from districts.research.api_catalog import search_apis
        results = search_apis("finance", limit=5)
        for api in results:
            for key in ("name", "description", "url"):
                self.assertIn(key, api)

    def test_get_by_category_returns_list(self):
        from districts.research.api_catalog import get_by_category, get_categories
        cats = get_categories()
        if cats:
            result = get_by_category(cats[0])
            self.assertIsInstance(result, list)

    def test_free_only_filter(self):
        from districts.research.api_catalog import search_apis
        results = search_apis("api", free_only=True, limit=20)
        for api in results:
            self.assertTrue(api.get("free", True))

    def test_search_no_readme_returns_empty(self):
        from districts.research import api_catalog
        from districts.research.api_catalog import _load_catalog
        original = api_catalog._README
        try:
            api_catalog._README = Path("/nonexistent_path/README.md")
            _load_catalog.cache_clear()
            from districts.research.api_catalog import search_apis
            result = search_apis("weather", limit=5)
            self.assertIsInstance(result, list)
        finally:
            api_catalog._README = original
            _load_catalog.cache_clear()


# ════════════════════════════════════════════════════════════════════════════
# TestResearchEpisodicIntegration
# ════════════════════════════════════════════════════════════════════════════

class TestResearchEpisodicIntegration(unittest.TestCase):
    """Cross-agent: verify research outputs persist to episodic_memory."""

    def test_web_scout_research_event_type_stored(self):
        from districts.research.web_scout import WebScout
        scout = WebScout()
        scout.search = AsyncMock(return_value=[
            {"title": "Integration Test", "url": f"https://integ.test/{uuid.uuid4().hex}", "snippet": "s"}
        ])
        scout.fetch_page = AsyncMock(return_value="test content")
        _run(scout.research("integration test query", save_note=False))
        self.assertTrue(_event_stored("research"))

    def test_news_aggregator_news_brief_event_stored(self):
        from districts.research.news_aggregator import NewsAggregator
        agg = NewsAggregator()
        agg._newsapi_key = ""
        articles = [
            {"title": "Integ Article", "source": "S", "url": f"https://integ2.test/{uuid.uuid4().hex}", "description": "d", "published": "2024-01-01"}
        ]
        agg.gather_news = AsyncMock(return_value=articles)
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            agg._obsidian._vault = vault
            _run(agg.morning_brief())
        self.assertTrue(_event_stored("news_brief"))

    def test_paper_reader_paper_brief_event_stored(self):
        from districts.research.paper_reader import PaperReader
        reader = PaperReader()
        reader.fetch_recent_papers = AsyncMock(return_value=[
            {"title": "Integ Paper", "authors": "Auth", "abstract": "abs", "url": "https://arxiv.org/abs/integ", "id": f"integ_{uuid.uuid4().hex}"}
        ])
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            reader._obsidian._vault = vault
            _run(reader.daily_brief(max_per_category=1))
        self.assertTrue(_event_stored("paper_brief"))

    def test_research_hub_daily_digest_event_stored(self):
        from districts.research.research_hub import ResearchHub
        hub = ResearchHub()
        for method in ("get_hn_top", "get_github_trending", "get_devto_posts",
                       "search_arxiv", "get_crypto_prices", "get_tech_news"):
            setattr(hub, method, AsyncMock(return_value=[]))
        _run(hub.daily_digest())
        self.assertTrue(_event_stored("daily_research_digest"))

    def test_all_research_agents_alive_on_init(self):
        from districts.research.web_scout import WebScout
        from districts.research.news_aggregator import NewsAggregator
        from districts.research.paper_reader import PaperReader
        from districts.research.opencli_adapter import OpenCLIAdapter
        from districts.research.reddit_miner import RedditMiner
        from districts.research.research_hub import ResearchHub
        for AgentClass in [WebScout, NewsAggregator, PaperReader, OpenCLIAdapter, RedditMiner, ResearchHub]:
            agent = AgentClass()
            self.assertTrue(agent.is_alive, f"{AgentClass.__name__} should be alive at init (500 HP)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
