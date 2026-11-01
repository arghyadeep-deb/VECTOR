"""
Module: agents/investment/__init__.py
V.E.C.T.O.R. Investment District - Stock analysis and investment agents
"""

import sys

from loguru import logger

from .stock_analyst import StockAnalyst
from .fundamentals_bot import FundamentalsBot
from .technical_bot import TechnicalBot
from .sentiment_bot import SentimentBot
from .trading_conductor_agent import TradingConductorAgent
from .finagent_agent import FinAgentAgent
from .hedgebot_agent import HedgeBotAgent
from .backtest_agent import BacktestAgent
from .execution_engine import ExecutionEngine

__all__ = [
    "StockAnalyst",
    "FundamentalsBot",
    "TechnicalBot",
    "TradingConductorAgent",
    "FinAgentAgent",
    "HedgeBotAgent",
    "BacktestAgent",
    "SentimentBot",
    "ExecutionEngine",
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
