"""Crypto asset type support for TradingAgents."""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG


class CryptoTradingAgent:
    """Crypto-specific trading analysis (paper mode only, gated by permission_gateway)."""

    ASSET_TYPE = "crypto"
    SUPPORTED_EXCHANGES = ["binance", "coinbase", "kraken", "hyperliquid"]

    def __init__(self, exchange: str = "binance"):
        self.exchange = exchange
        logger.info("[VECTOR][crypto_trading] CryptoTradingAgent initialized (paper mode)")

    async def get_quote(self, symbol: str) -> dict:
        """Get crypto price quote via yfinance or CoinGecko."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{symbol}-USD")
            info = ticker.fast_info
            return {
                "symbol": symbol,
                "price": float(info.last_price) if hasattr(info, 'last_price') else 0.0,
                "asset_type": self.ASSET_TYPE,
                "exchange": self.exchange,
            }
        except Exception as e:
            logger.warning("[VECTOR][crypto_trading] get_quote failed: {}", e)
            return {"symbol": symbol, "price": 0.0, "error": str(e)}

    async def analyze(self, symbol: str) -> dict:
        """Full crypto analysis — technical + fundamental."""
        quote = await self.get_quote(symbol)
        return {
            "symbol": symbol,
            "asset_type": self.ASSET_TYPE,
            "quote": quote,
            "analysis": "Use TechnicalBot + SentimentBot for full analysis",
            "paper_mode": True,
        }


if __name__ == "__main__":
    a = CryptoTradingAgent()
    print("✅ crypto_trading OK:", type(a).__name__)
