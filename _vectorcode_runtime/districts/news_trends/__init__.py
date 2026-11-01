"""
Module: agents/news_trends/__init__.py
District: news_trends | Focus: AI news, market trends, opportunity spotting
"""

from .ai_news_bot import AINewsBot
from .market_trends_bot import MarketTrendsBot
from .opportunity_spotter import OpportunitySpotter

__all__ = [
    "AINewsBot",
    "MarketTrendsBot",
    "OpportunitySpotter",
]