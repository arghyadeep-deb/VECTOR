"""Research router — /research/status."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/research", tags=["research"])

@router.get("/status")
async def research_status():
    """Report available research modes."""
    modes = []
    llm_available = False
    try:
        try:
            from core.loop.llm_interface import LLMInterface
            llm_available = True
        except ImportError:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)

        try:
            from core.scraper.vector_scraper import VectorScraper
            modes.append("web_scrape")
        except ImportError:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)

        try:
            from core.media.models import all_models
            if all_models():
                modes.append("media_generation")
        except ImportError:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)

        modes.append("basic_search")
    except Exception as e:
        logger.warning(f"[VECTOR][api][research] status failed: {e}")

    return {"modes": modes, "llm_available": llm_available}

@router.get("/search")
async def research_search(query: str, max_results: int = 5):
    """Search the web via VECTOR's WebScout agent using DuckDuckGo."""
    try:
        from districts.research.web_scout import WebScout
        scout = WebScout()
        import asyncio
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(scout.run({"type": "search", "params": {"query": query, "max_results": max_results}}))
        loop.close()
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
        import asyncio
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(agg.run({"type": "fetch", "params": {"query": query}}))
        loop.close()
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
        import asyncio
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(reader.run({"type": "search", "params": {"query": query, "max_results": max_results}}))
        loop.close()
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
        import asyncio
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(miner.run({"type": "hot_posts", "params": {"subreddit": subreddit, "limit": limit}}))
        loop.close()
        return result
    except Exception as e:
        logger.warning(f"[VECTOR][api][research] reddit failed: {e}")
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    print("OK: research.py")
