"""
APScheduler-based task scheduler for timed VECTOR jobs.
All jobs run at fixed times; each is independently fault-isolated.

Schedule (IST = UTC+5:30):
  07:00 — news_aggregator.morning_brief()
  07:05 — reddit_miner.intelligence_report()
  07:10 — paper_reader.daily_brief()
  02:00 — consolidation_bot.write_daily_reflection()
  02:30 — pattern_finder.find_patterns(window_hours=48)
"""
import sys
import asyncio

from loguru import logger


def _run_async(coro) -> None:
    """Run an async function from a sync APScheduler job."""
    try:
        asyncio.run(coro)
    except Exception as e:
        logger.error(f"[VECTOR][scheduler] job failed: {e}")


def build_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("[VECTOR][scheduler] apscheduler not installed — scheduler disabled")
        return None

    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    scheduler.add_job(
        lambda: _run_async(_news_brief()),
        CronTrigger(hour=7, minute=0),
        id="news_brief",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_async(_reddit_intel()),
        CronTrigger(hour=7, minute=5),
        id="reddit_intel",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_async(_paper_brief()),
        CronTrigger(hour=7, minute=10),
        id="paper_brief",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_async(_daily_reflection()),
        CronTrigger(hour=2, minute=0),
        id="daily_reflection",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_async(_pattern_scan()),
        CronTrigger(hour=2, minute=30),
        id="pattern_scan",
        replace_existing=True,
    )

    return scheduler


async def _news_brief():
    from districts.research.news_aggregator import NewsAggregator
    await NewsAggregator().morning_brief()


async def _reddit_intel():
    from districts.research.reddit_miner import RedditMiner
    await RedditMiner().intelligence_report()


async def _paper_brief():
    from districts.research.paper_reader import PaperReader
    await PaperReader().daily_brief()


async def _daily_reflection():
    from districts.memory_curator.consolidation_bot import ConsolidationBot
    await ConsolidationBot().write_daily_reflection()


async def _pattern_scan():
    from districts.memory_curator.pattern_finder import PatternFinder
    await PatternFinder().find_patterns(window_hours=48)


if __name__ == "__main__":
    import time
    sys.stdout.reconfigure(encoding="utf-8")

    sched = build_scheduler()
    if sched:
        sched.start()
        logger.info("[VECTOR][scheduler] started — 5 jobs scheduled")
        jobs = sched.get_jobs()
        for j in jobs:
            logger.info(f"  {j.id}: next run = {j.next_run_time}")
        print(f"✅ scheduler.py OK — {len(jobs)} jobs")
        sched.shutdown()
    else:
        print("⚠️  scheduler.py — apscheduler not available, skipped")
