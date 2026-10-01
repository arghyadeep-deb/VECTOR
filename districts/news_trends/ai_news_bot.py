"""
Module: agents/news_trends/ai_news_bot.py
District: news_trends | Focus: AI news fetching, summaries, breaking alerts
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime
from typing import Optional


class AINewsBot(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="AINewsBot",
            district="news_trends",
            generation=1
        )
        self.capabilities = ["ai_news", "mine_social", "news", "news_trends", "venture_pipeline"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.news_cache = []
        self.alerts = []
        logger.info("[VECTOR][news_trends] AINewsBot ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def fetch_ai_news(self, count: int = 5) -> dict:
        logger.info("[VECTOR][news_trends] Fetching {} AI news articles", count)
        self.add_lesson({"action": "fetch_ai_news", "count": count})

        articles = []
        error = ""

        try:
            import httpx
            newsapi_key = str(CONFIG["api_keys"].get("newsapi_key", "") or "")
            if not newsapi_key:
                raise ValueError("No NewsAPI key configured")
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    "https://newsapi.org/v2/everything",
                    params={"q": "artificial intelligence OR LLM OR machine learning",
                            "sortBy": "publishedAt", "pageSize": count},
                    # key in a header, not the URL: httpx errors/logs embed the URL
                    headers={"User-Agent": "VECTOR-NewsBot/1.0", "X-Api-Key": newsapi_key},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") == "error":
                    raise RuntimeError(f"NewsAPI error: {data.get('code', data.get('message', 'unknown'))}")
                articles = [
                    {
                        "title": a.get("title", ""),
                        "source": (a.get("source") or {}).get("name", ""),
                        "url": a.get("url", ""),
                        "publishedAt": a.get("publishedAt", ""),
                        "description": a.get("description", ""),
                    }
                    for a in data.get("articles", [])[:count]
                ]
        except Exception as e:
            # Previously returned five canned "simulated" headlines as real news.
            error = f"{type(e).__name__}: {e}"
            logger.warning("[VECTOR][news_trends] NewsAPI fetch failed: {}", error)

        if error:
            return {"status": "error", "error": error, "articles": [], "count": 0,
                    "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}

        self.news_cache = articles

        result = {
            "articles": articles,
            "count": len(articles),
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="ai_news_fetched",
            content=f"Fetched {len(articles)} AI news articles",
            tags=["news", "AI", "trends"],
            context=result,
            source="AINewsBot"
        )

        return result

    def generate_summary(self, article_url: str) -> dict:
        logger.info("[VECTOR][news_trends] Generating summary for: {}", article_url)
        self.add_lesson({"action": "generate_summary", "url": article_url})

        def _err(msg: str) -> dict:
            return {"status": "error", "error": msg, "article_url": article_url, "summary": ""}

        if not article_url:
            return _err("no article url given")
        from core.security.ssrf_guard import get_ssrf_guard
        chk = get_ssrf_guard().check_url(article_url)
        if not chk.safe:
            logger.warning("[VECTOR][news_trends] SSRF blocked: {}", chk.reason)
            return _err(f"url blocked: {chk.reason}")

        try:
            import httpx
            from html.parser import HTMLParser
            with httpx.Client(timeout=30.0) as client:
                # no redirects: a 302 to an internal host would bypass the check above
                resp = client.get(article_url, headers={"User-Agent": "VECTOR-NewsBot/1.0"})
                resp.raise_for_status()
                class MLStripper(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.reset()
                        self.fed = []
                    def handle_data(self, d):
                        self.fed.append(d)
                    def get_data(self):
                        return ' '.join(self.fed)
                html = resp.text
                s = MLStripper()
                s.feed(html)
                article_text = s.get_data()[:3000]
        except Exception as e:
            # Previously fed a canned placeholder to the LLM and returned its
            # invented "summary" as a real one.
            logger.warning("[VECTOR][news_trends] Could not fetch article: {}", e)
            return _err(f"could not fetch article: {type(e).__name__}: {e}")
        if not article_text.strip():
            return _err("article had no extractable text")

        prompt = f"Summarize this article in 5 bullet points and a 2-sentence overview.\n\nArticle: {article_text}"
        summary = self._call_ollama(prompt)
        if not (summary or "").strip():
            return _err("LLM returned no summary")

        result = {
            "article_url": article_url,
            "summary": summary,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="article_summary_generated",
            content=f"Generated summary for article: {article_url[:50]}...",
            tags=["news", "summary", "AI"],
            context=result,
            source="AINewsBot"
        )

        return result

    def alert_breaking(self, topic: str) -> dict:
        logger.info(f"[VECTOR][news_trends] Checking for breaking news on: {topic}")
        self.add_lesson({"action": "alert_breaking", "topic": topic})

        news_result = self.fetch_ai_news(10)
        if news_result.get("status") == "error":
            # a failed fetch is not "nothing breaking"
            return {"status": "error", "error": news_result.get("error", "news fetch failed"),
                    "topic": topic, "is_breaking": False, "relevant_articles": 0,
                    "articles": [], "alert_level": "UNKNOWN",
                    "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        relevant = [
            a for a in news_result["articles"]
            if topic.lower() in a.get("title", "").lower() or topic.lower() in a.get("description", "").lower()
        ]

        is_breaking = len(relevant) > 0

        alert = {
            "topic": topic,
            "is_breaking": is_breaking,
            "relevant_articles": len(relevant),
            "articles": relevant if is_breaking else [],
            "alert_level": "HIGH" if len(relevant) >= 3 else "MEDIUM" if len(relevant) >= 1 else "LOW",
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        if is_breaking:
            self.alerts.append(alert)

        self.memory.store(
            event_type="breaking_alert",
            content=f"Breaking alert for '{topic}': {len(relevant)} relevant articles",
            tags=["news", "alert", "breaking", topic],
            context=alert,
            source="AINewsBot"
        )

        return alert


    async def run(self, task: dict) -> dict:
        p = task.get("params") or {}
        url = p.get("url", "")
        if not url:
            # governor routes plain "news"/"ai_news" tasks here with no url
            result = self.fetch_ai_news(int(p.get("count", 5) or 5))
        else:
            result = self.generate_summary(url)
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    bot = AINewsBot()
    assert bot.district == "news_trends"

    news = bot.fetch_ai_news(3)
    assert "articles" in news  # empty + status=error when no NewsAPI key/network

    summary = bot.generate_summary("https://example.com/article")
    assert "summary" in summary

    alert = bot.alert_breaking("LLM")
    assert "topic" in alert
    assert "alert_level" in alert

    print("✅ ai_news_bot.py OK")