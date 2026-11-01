"""
Agent worker manager — starts and supervises all district agent loops.
Each district agent runs its own run_forever() coroutine.
RULE 2: if any coroutine crashes, it is restarted with back-off.
"""
import sys
import asyncio

from core.config import CONFIG
from loguru import logger


async def _guarded(coro_factory, name: str, backoff_sec: int = 30) -> None:
    """RULE 2 wrapper — restarts a coroutine on any exception."""
    while True:
        try:
            logger.info(f"[VECTOR][workers] starting {name}")
            await coro_factory()
        except Exception as e:
            logger.error(f"[VECTOR][workers] {name} crashed: {e} — restarting in {backoff_sec}s")
            await asyncio.sleep(backoff_sec)


async def run_research_workers() -> None:
    from districts.research.web_scout import WebScout
    from districts.research.paper_reader import PaperReader
    from districts.research.news_aggregator import NewsAggregator
    from districts.research.reddit_miner import RedditMiner

    await asyncio.gather(
        _guarded(lambda: WebScout().run_forever(), "WebScout"),
        _guarded(lambda: PaperReader().run_forever(), "PaperReader"),
        _guarded(lambda: NewsAggregator().run_forever(), "NewsAggregator"),
        _guarded(lambda: RedditMiner().run_forever(), "RedditMiner"),
    )


async def run_memory_workers() -> None:
    from districts.memory_curator.consolidation_bot import ConsolidationBot
    from districts.memory_curator.pattern_finder import PatternFinder

    await asyncio.gather(
        _guarded(lambda: ConsolidationBot().run_forever(), "ConsolidationBot"),
        _guarded(lambda: PatternFinder().run_forever(), "PatternFinder"),
    )


async def run_governance_workers() -> None:
    from districts.governance.llm_council import LLMCouncil
    await _guarded(lambda: LLMCouncil().run_forever(), "LLMCouncil")


async def run_all() -> None:
    """Start all district worker groups concurrently."""
    logger.info("[VECTOR][workers] all workers starting")
    await asyncio.gather(
        run_research_workers(),
        run_memory_workers(),
        run_governance_workers(),
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run_all())
