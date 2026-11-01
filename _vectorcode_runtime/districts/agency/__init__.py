"""
Module: agents/agency/__init__.py
V.E.C.T.O.R. Agency District - Client management and content strategy agents
"""

import sys

from loguru import logger

from .content_strategist import ContentStrategist
from .client_manager import ClientManager
from .performance_tracker import PerformanceTracker

__all__ = [
    "ContentStrategist",
    "ClientManager",
    "PerformanceTracker",
]

logger.info("[VECTOR][agency] Agency district loaded")


def get_agent(name: str):
    """Factory function to get agency district agents."""
    agents = {
        "ContentStrategist": ContentStrategist,
        "ClientManager": ClientManager,
        "PerformanceTracker": PerformanceTracker,
    }
    return agents.get(name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    strategist = ContentStrategist()
    print(f"ContentStrategist: {strategist.name}")

    manager = ClientManager()
    print(f"ClientManager: {manager.name}")

    tracker = PerformanceTracker()
    print(f"PerformanceTracker: {tracker.name}")

    print("✅ agency/__init__.py OK")
