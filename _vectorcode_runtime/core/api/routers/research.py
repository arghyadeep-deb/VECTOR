"""Research router — /research/status."""


__all__ = [
    "research_news",
    "research_papers",
    "research_reddit",
    "research_search",
    "research_status",
    "router",
]


from fastapi import APIRouter
from loguru import logger
from core.api.cache import research_cache

router = APIRouter(prefix="/research", tags=["research"])

@router.get("/status")
async def research_status():
    """Report available research modes."""
    modes = []
    llm_available = False
    try:
        try:
            # 2026-09-24 (external review, Phase 1): core.loop.llm_interface
            # never existed -- llm_available was always False. The real,
            # actively-used inference entry point is provider_client.py.
            from core.inference.provider_client import get_client  # noqa: F401
            llm_available = True
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        try:
            from core.scraper.vector_scraper import VectorScraper
            modes.append("web_scrape")
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        try:
            from core.media.models import all_models
            if all_models():
                modes.append("media_generation")
        except ImportError:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        modes.append("basic_search")
    except Exception as e:
        logger.warning(f"[VECTOR][api][research] status failed: {e}")

    return {"modes": modes, "llm_available": llm_available}

@router.get("/search")
async def research_search(query: str, max_results: int = 5):
    """Search the web via VECTOR's WebScout agent using DuckDuckGo."""
    cache_key = f"search_{query[:50]}"
    cached = research_cache.get(cache_key)
    if cached:
        return cached
    try:
        from districts.research.web_scout import WebScout
        scout = WebScout()
        result = await scout.run({"type": "search", "params": {"query": query, "max_results": max_results}})
        research_cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.warning(f"[VECTOR][api][research] search failed: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/news")
async def research_news(query: str = "AI"):
    """Fetch recent news via VECTOR's NewsAggregator."""
    try:
        from districts.research.news_aggregator import NewsAggregator
        agg = NewsAggregator()
        result = await agg.run({"type": "fetch", "params": {"query": query}})
        return result
    except Exception as e:
        logger.warning(f"[VECTOR][api][research] news failed: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/papers")
async def research_papers(query: str, max_results: int = 5):
    """Search ArXiv for academic papers via VECTOR's PaperReader."""
    try:
        from districts.research.paper_reader import PaperReader
        reader = PaperReader()
        result = await reader.run({"type": "search", "params": {"query": query, "max_results": max_results}})
        return result
    except Exception as e:
        logger.warning(f"[VECTOR][api][research] papers failed: {e}")
        return {"status": "error", "error": str(e)}


@router.get("/reddit")
async def research_reddit(subreddit: str = "LocalLLaMA", limit: int = 10):
    """Mine hot posts from a subreddit via VECTOR's RedditMiner."""
    try:
        from districts.research.reddit_miner import RedditMiner
        miner = RedditMiner()
        result = await miner.run({"type": "hot_posts", "params": {"subreddit": subreddit, "limit": limit}})
        return result
    except Exception as e:
        logger.warning(f"[VECTOR][api][research] reddit failed: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    print("OK: research.py")
