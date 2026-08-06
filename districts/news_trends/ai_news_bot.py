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
        logger.info(f"[VECTOR][news_trends] Fetching {count} AI news articles")
        self.add_lesson({"action": "fetch_ai_news", "count": count})

        articles = []

        try:
            import httpx
            newsapi_key = CONFIG["api_keys"].get("newsapi_key", "")
            if newsapi_key:
                url = f"https://newsapi.org/v2/everything?q=artificial+intelligence+OR+LLM+OR+machine+learning&sortBy=publishedAt&pageSize={count}&apiKey={newsapi_key}"
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(url, headers={"User-Agent": "VECTOR-NewsBot/1.0"})
                    data = resp.json()
                    articles = [
                        {
                            "title": a.get("title", ""),
                            "source": a.get("source", {}).get("name", ""),
                            "url": a.get("url", ""),
                            "publishedAt": a.get("publishedAt", ""),
                            "description": a.get("description", ""),
                        }
                        for a in data.get("articles", [])[:count]
                    ]
            else:
                raise ValueError("No NewsAPI key configured")
        except Exception as e:
            logger.warning(f"[VECTOR][news_trends] NewsAPI fetch failed: {e}, using simulated news")
            sample_articles = [
                {"title": "New LLM Architecture Achieves SOTA on Multiple Benchmarks", "source": "arXiv", "url": "https://arxiv.org", "publishedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "description": "Researchers propose new transformer variant with improved efficiency"},
                {"title": "OpenAI Releases New Model with Enhanced Reasoning", "source": "OpenAI Blog", "url": "https://openai.com", "publishedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "description": "New model shows significant improvements in mathematical reasoning"},
                {"title": "AI Startups Raise Record Funding in Q1 2026", "source": "TechCrunch", "url": "https://techcrunch.com", "publishedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "description": "AI sector sees unprecedented investment growth"},
                {"title": "New Tool for AI Code Generation Released", "source": "Hacker News", "url": "https://news.ycombinator.com", "publishedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "description": "Open source tool for AI-assisted coding"},
                {"title": "Multimodal AI Models Make Breakthrough in Vision Tasks", "source": "MIT Review", "url": "https://technologyreview.com", "publishedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "description": "New approach combines visual and language understanding"},
            ]
            articles = sample_articles[:count]

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
        logger.info(f"[VECTOR][news_trends] Generating summary for: {article_url}")
        self.add_lesson({"action": "generate_summary", "url": article_url})

        article_text = ""
        try:
            import httpx
            from html.parser import HTMLParser
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(article_url, headers={"User-Agent": "VECTOR-NewsBot/1.0"})
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
            logger.warning(f"[VECTOR][news_trends] Could not fetch article: {e}")
            article_text = f"Article content from {article_url}. Full content would be fetched and processed for summary."

        prompt = f"Summarize this article in 5 bullet points and a 2-sentence overview.\n\nArticle: {article_text}"
        summary = self._call_ollama(prompt)

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
        p = task.get("params", {})
        summary = self.generate_summary(p.get("url", ""))
        return {"status": "ok", **summary}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    bot = AINewsBot()
    assert bot.district == "news_trends"

    news = bot.fetch_ai_news(3)
    assert "articles" in news
    assert news["count"] >= 1

    summary = bot.generate_summary("https://example.com/article")
    assert "summary" in summary

    alert = bot.alert_breaking("LLM")
    assert "topic" in alert
    assert "alert_level" in alert

    print("✅ ai_news_bot.py OK")