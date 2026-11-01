"""
Module: agents/time_calendar/__init__.py
V.E.C.T.O.R. Time & Calendar District - Time management and scheduling agents
"""

import sys

from loguru import logger

from .time_blocker import TimeBlocker
from .deadline_manager import DeadlineManager
from .kiit_scraper import KIITScraper

__all__ = [
    "TimeBlocker",
    "DeadlineManager",
    "KIITScraper",
]

logger.info("[VECTOR][time_calendar] Time & Calendar district loaded")


def get_agent(name: str):
    """Factory function to get time_calendar district agents."""
    agents = {
        "TimeBlocker": TimeBlocker,
        "DeadlineManager": DeadlineManager,
        "KIITScraper": KIITScraper,
    }
    return agents.get(name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    from .time_blocker import TimeBlocker
    blocker = TimeBlocker()
    print(f"TimeBlocker: {blocker.name}")

    try:
        from .deadline_manager import DeadlineManager
        dm = DeadlineManager()
        print(f"DeadlineManager: {dm.name}")
    except Exception as e:
        print(f"DeadlineManager: {e}")

    try:
        from .kiit_scraper import KIITScraper
        scraper = KIITScraper()
        print(f"KIITScraper: {scraper.name}")
    except Exception as e:
        print(f"KIITScraper: {e}")

    print("✅ time_calendar/__init__.py OK")
