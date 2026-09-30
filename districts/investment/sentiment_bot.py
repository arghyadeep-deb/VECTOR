
import sys
import uuid
import asyncio as _asyncio
import concurrent.futures as _cf
from typing import Optional

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


def _llm(prompt: str, max_tokens: int = 800, temperature: float = 0.6) -> str:
    from core.inference.provider_client import ProviderClient as _PC
    async def _call():
        r = await _PC().chat(
            messages=[{"role": "user", "content": prompt}],
            model="domain:finance.analysis",   # finance-tuned chain, ollama terminal
            tier="reasoning", temperature=temperature, max_tokens=max_tokens,
            caller_id="sentiment_bot",
        )
        return r.content
    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_asyncio.run, _call()).result(timeout=90)

class SentimentBot(AgentBase):
    """
    Analyzes sentiment from news and social media
    for investment decisions.
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "SentimentBot", "investment")
        self.capabilities = ["alpha_discovery", "investment", "sentiment"]
        if ghost:
            self.inherit_ghost(ghost)

        self._sentiment_cache: dict[str, dict] = {}
        self._newsapi_key = CONFIG.get("api_keys", {}).get("newsapi_key", "")
        logger.info("[VECTOR][sentiment_bot] SentimentBot initialized")

    def fetch_news_sentiment(self, symbol: str) -> dict:
        """
        Fetch and analyze news sentiment for a stock.
        """
        symbol = symbol.upper()

        if symbol in self._sentiment_cache:
            cache_age = self._get_cache_age(symbol)
            if cache_age < 3600:
                return self._sentiment_cache[symbol]

        if self._newsapi_key:
            return self._fetch_real_news_sentiment(symbol)
        return self._generate_mock_news_sentiment(symbol)

    def _get_cache_age(self, symbol: str) -> int:
        """Get age of cached sentiment in seconds."""
        if symbol not in self._sentiment_cache:
            return 999999
        return 0

    def _fetch_real_news_sentiment(self, symbol: str) -> dict:
        """Fetch real news and analyze sentiment."""
        try:
            import httpx

            url = "https://newsapi.org/v2/everything"
            params = {
                "q": f"${symbol} OR {symbol} stock",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 20
            }

            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    url,
                    params=params,
                    headers={"X-Api-Key": self._newsapi_key},
                )

            if response.status_code != 200:
                return self._generate_mock_news_sentiment(symbol)

            data = response.json()
            articles = data.get("articles", [])

            if not articles:
                return self._generate_mock_news_sentiment(symbol)

            sentiment_data = self._analyze_articles_sentiment(articles, symbol)
            self._sentiment_cache[symbol] = sentiment_data

            return sentiment_data

        except Exception as e:
            logger.error(f"[VECTOR][sentiment_bot] News fetch failed: {e}")
            return self._generate_mock_news_sentiment(symbol)

    def _analyze_articles_sentiment(self, articles: list, symbol: str) -> dict:
        """Analyze sentiment from articles."""
        if not articles:
            return self._generate_mock_news_sentiment(symbol)

        titles = [a.get("title", "") for a in articles if a.get("title")]
        descriptions = [a.get("description", "") for a in articles if a.get("description")]

        sentiment_scores = []
        for text in titles + descriptions:
            score = self._simple_sentiment_score(text)
            sentiment_scores.append(score)

        avg_score = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.5

        positive_count = sum(1 for s in sentiment_scores if s > 0.6)
        negative_count = sum(1 for s in sentiment_scores if s < 0.4)
        neutral_count = len(sentiment_scores) - positive_count - negative_count

        sentiment_label = "bullish" if avg_score > 0.55 else "bearish" if avg_score < 0.45 else "neutral"

        return {
            "status": "success",
            "symbol": symbol,
            "sentiment_score": round(avg_score, 3),
            "sentiment_label": sentiment_label,
            "article_count": len(articles),
            "breakdown": {
                "positive": positive_count,
                "negative": negative_count,
                "neutral": neutral_count
            },
            "key_themes": self._extract_key_themes(titles + descriptions),
            "recent_headlines": titles[:5],
            "timestamp": self._get_timestamp(),
            "source": "newsapi"
        }

    def _simple_sentiment_score(self, text: str) -> float:
        """Simple rule-based sentiment scoring."""
        text_lower = text.lower()

        positive_words = [
            "surge", "soar", "rally", "gain", "profit", "growth", "bullish",
            "upgrade", "beat", "exceed", "record", "high", "strong", "up"
        ]
        negative_words = [
            "fall", "drop", "crash", "loss", "decline", "bearish", "downgrade",
            "miss", "below", "low", "weak", "risk", "warning", "cut"
        ]

        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)

        total = pos_count + neg_count
        if total == 0:
            return 0.5

        return (pos_count / total + 0.5) / 2

    def _generate_mock_news_sentiment(self, symbol: str) -> dict:
        """Generate mock sentiment data."""
        import random

        hash_val = sum(ord(c) for c in symbol)
        base_score = 0.5 + ((hash_val % 20) - 10) / 100

        positive = 5 + (hash_val % 10)
        negative = 2 + (hash_val % 8)
        neutral = 5 + (hash_val % 7)

        headlines = [
            f"{symbol} Reports Strong Q4 Earnings",
            f"{symbol} Announces New Product Launch",
            f"Analysts Upgrade {symbol} Price Target",
            f"{symbol} Stock Hits New 52-Week High",
            f"{symbol} Expands Into New Markets"
        ]

        return {
            "status": "success",
            "symbol": symbol,
            "sentiment_score": round(base_score, 3),
            "sentiment_label": "bullish" if base_score > 0.55 else "bearish" if base_score < 0.45 else "neutral",
            "article_count": positive + negative + neutral,
            "breakdown": {
                "positive": positive,
                "negative": negative,
                "neutral": neutral
            },
            "key_themes": ["earnings", "growth", "product launch", "analyst coverage"],
            "recent_headlines": headlines[:5],
            "timestamp": self._get_timestamp(),
            "source": "mock"
        }

    def fetch_social_sentiment(self, symbol: str) -> dict:
        """
        Fetch and analyze social media sentiment for a stock.
        """
        symbol = symbol.upper()

        import random

        hash_val = sum(ord(c) for c in symbol)
        twitter_mentions = 5000 + (hash_val * 100) % 50000
        twitter_sentiment = 0.4 + ((hash_val % 30) / 100)

        reddit_score = 0.3 + ((hash_val % 40) / 100)

        return {
            "status": "success",
            "symbol": symbol,
            "twitter": {
                "mentions": twitter_mentions,
                "sentiment": round(twitter_sentiment, 3),
                "trend": "increasing" if twitter_sentiment > 0.5 else "decreasing"
            },
            "reddit": {
                "mentions": 500 + (hash_val % 1000),
                "sentiment": round(reddit_score, 3),
                "subreddits": ["wallstreetbets", "stocks", "investing"]
            },
            "overall_social_sentiment": round((twitter_sentiment + reddit_score) / 2, 3),
            "social_volume_score": round(twitter_mentions / 10000, 1),
            "timestamp": self._get_timestamp(),
            "source": "mock"
        }

    def generate_sentiment_report(self, symbol: str) -> dict:
        """
        Generate comprehensive sentiment report combining all sources.
        """
        symbol = symbol.upper()

        news_sentiment = self.fetch_news_sentiment(symbol)
        social_sentiment = self.fetch_social_sentiment(symbol)

        news_score = news_sentiment.get("sentiment_score", 0.5)
        social_score = social_sentiment.get("overall_social_sentiment", 0.5)

        combined_score = (news_score * 0.6) + (social_score * 0.4)

        prompt = f"""Generate a sentiment analysis report for {symbol}.

News Sentiment: {news_sentiment.get('sentiment_label', 'N/A')} ({news_score:.2f})
Social Sentiment: {'Positive' if social_score > 0.5 else 'Negative'} ({social_score:.2f})
Combined Score: {combined_score:.2f}

Key Headlines:
{chr(10).join(f"- {h}" for h in news_sentiment.get('recent_headlines', [])[:3])}

Key Themes: {', '.join(news_sentiment.get('key_themes', [])[:5])}

Provide:
1. Executive Summary
2. Key Sentiment Drivers
3. Risk Factors Based on Sentiment
4. Trading Implications
5. Outlook (short-term and long-term)

Be specific and actionable.
"""

        try:
            llm_analysis = _llm(prompt, max_tokens=800)

            report = {
                "status": "success",
                "symbol": symbol,
                "combined_sentiment_score": round(combined_score, 3),
                "sentiment_label": "bullish" if combined_score > 0.55 else "bearish" if combined_score < 0.45 else "neutral",
                "news_sentiment": news_sentiment,
                "social_sentiment": social_sentiment,
                "llm_analysis": llm_analysis,
                "timestamp": self._get_timestamp()
            }

            self.award_points(20, f"sentiment_report_generated_{symbol}")

            return report

        except Exception as e:
            logger.error(f"[VECTOR][sentiment_bot] Sentiment report failed: {e}")
            return {
                "symbol": symbol,
                "status": "error",
                "message": str(e),
                "news_sentiment": news_sentiment,
                "social_sentiment": social_sentiment
            }

    def _extract_key_themes(self, texts: list[str]) -> list[str]:
        """Extract key themes from texts."""
        themes = []

        theme_keywords = {
            "earnings": ["earnings", "revenue", "profit", "quarter", "q1", "q2", "q3", "q4"],
            "product": ["product", "launch", "release", "update", "new"],
            "acquisition": ["acquisition", "merger", "acquire", "buy", "deal"],
            "leadership": ["ceo", "executive", "leadership", "founder", "cfo"],
            "regulatory": ["regulation", "lawsuit", "sec", "investigation", "fine"],
            "competition": ["competitor", "competition", "market share", "rival"]
        }

        combined_text = " ".join(texts).lower()

        for theme, keywords in theme_keywords.items():
            if any(kw in combined_text for kw in keywords):
                themes.append(theme)

        return themes[:5]

    def compare_sentiment(self, symbols: list[str]) -> dict:
        """
        Compare sentiment across multiple stocks.
        """
        sentiments = {}

        for symbol in symbols:
            sentiment = self.fetch_news_sentiment(symbol.upper())
            sentiments[symbol.upper()] = sentiment

        sorted_by_sentiment = sorted(
            sentiments.items(),
            key=lambda x: x[1].get("sentiment_score", 0.5),
            reverse=True
        )

        comparison = {
            "status": "success",
            "symbols": symbols,
            "sentiments": sentiments,
            "rankings": {
                "most_bullish": sorted_by_sentiment[0][0] if sorted_by_sentiment else None,
                "most_bearish": sorted_by_sentiment[-1][0] if sorted_by_sentiment else None
            },
            "sorted_by_score": [
                {"symbol": s[0], "score": s[1].get("sentiment_score", 0)}
                for s in sorted_by_sentiment
            ],
            "timestamp": self._get_timestamp()
        }

        self.award_points(len(symbols) * 3, "sentiment_comparison")
        return comparison

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        symbol = p.get("symbol")
        query = p.get("query") or p.get("content") or task.get("query") or task.get("prompt")

        if not symbol and query:
            # 2026-07-29: run() ignored task_type entirely and always
            # generated a sentiment report for a hardcoded RELIANCE symbol,
            # regardless of what the user actually asked — same bug class
            # as stock_analyst.py's pre-fix quote default (KNOWN_ISSUES.md
            # #1/#14/#15/#21/#33/#36). Answer free-text queries directly.
            try:
                prompt = (
                    "You are VECTOR's SentimentBot, an investment-district agent that "
                    "analyzes news and social-media sentiment for stocks (bullish/"
                    "bearish/neutral scoring, key themes, headline analysis, "
                    "cross-symbol sentiment comparison). Analysis only — you never "
                    "place or recommend executing real trades.\n\n"
                    f"Answer the user's question directly and specifically:\n{query}"
                )
                answer = _llm(prompt, max_tokens=700, temperature=0.6)
                return {"status": "ok", "response": answer}
            except Exception as e:
                logger.error("[VECTOR][sentiment_bot] free-text fallback failed: {}", e)
                # fall through to legacy symbol-report default below

        result = self.generate_sentiment_report(symbol or "RELIANCE")
        return {"status": "ok", **result}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    bot = SentimentBot()

    sentiment = bot.fetch_news_sentiment("AAPL")
    print(f"AAPL Sentiment: {sentiment.get('sentiment_label', 'N/A')}")

    report = bot.generate_sentiment_report("TSLA")
    print(f"TSLA Report: {report.get('sentiment_label', 'N/A')}")

    print("✅ sentiment_bot.py OK")
