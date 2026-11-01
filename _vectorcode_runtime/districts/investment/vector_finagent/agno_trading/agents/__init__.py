"""
Specialized Trading Agents
Agent files are optional — import only what is available.
"""
try:
    from .market_analyst import MarketAnalystAgent
except ImportError:
    MarketAnalystAgent = None
try:
    from .trading_strategy import TradingStrategyAgent
except ImportError:
    TradingStrategyAgent = None
try:
    from .risk_manager import RiskManagerAgent
except ImportError:
    RiskManagerAgent = None
try:
    from .portfolio_manager import PortfolioManagerAgent
except ImportError:
    PortfolioManagerAgent = None
try:
    from .sentiment_analyst import SentimentAnalystAgent
except ImportError:
    SentimentAnalystAgent = None

__all__ = [x for x in [
    "MarketAnalystAgent", "TradingStrategyAgent", "RiskManagerAgent",
    "PortfolioManagerAgent", "SentimentAnalystAgent"
] if locals().get(x) is not None]
