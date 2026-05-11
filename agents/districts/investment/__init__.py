"""
Module: agents/districts/investment/__init__.py
V.E.C.T.O.R. Investment District - Stock analysis and investment agents
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger

from .stock_analyst import StockAnalyst
from .fundamentals_bot import FundamentalsBot
from .technical_bot import TechnicalBot
from .sentiment_bot import SentimentBot

__all__ = [
    "StockAnalyst",
    "FundamentalsBot",
    "TechnicalBot",
    "SentimentBot",
]

logger.info("[VECTOR][investment] Investment district loaded")


def get_agent(name: str):
    """Factory function to get investment district agents."""
    agents = {
        "StockAnalyst": StockAnalyst,
        "FundamentalsBot": FundamentalsBot,
        "TechnicalBot": TechnicalBot,
        "SentimentBot": SentimentBot,
    }
    return agents.get(name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    stock = StockAnalyst()
    print(f"StockAnalyst: {stock.name}")

    fundamentals = FundamentalsBot()
    print(f"FundamentalsBot: {fundamentals.name}")

    technical = TechnicalBot()
    print(f"TechnicalBot: {technical.name}")

    sentiment = SentimentBot()
    print(f"SentimentBot: {sentiment.name}")

    print("✅ investment/__init__.py OK")
