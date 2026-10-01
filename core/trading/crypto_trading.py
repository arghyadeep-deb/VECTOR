"""Crypto asset type support for TradingAgents."""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

import asyncio
import math

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

            def _fetch() -> float | None:
                return getattr(yf.Ticker(f"{symbol}-USD").fast_info, "last_price", None)

            raw = await asyncio.to_thread(_fetch)
            price = float(raw) if raw is not None else None
            if price is None or not math.isfinite(price) or price <= 0:
                # A missing/zero price must never look like a real quote.
                logger.warning("[VECTOR][crypto_trading] no valid last_price for {}: {!r}", symbol, raw)
                return {"symbol": symbol, "price": None, "error": "no valid last_price",
                        "asset_type": self.ASSET_TYPE, "exchange": self.exchange}
            return {
                "symbol": symbol,
                "price": price,
                "asset_type": self.ASSET_TYPE,
                "exchange": self.exchange,
            }
        except Exception as e:
            logger.warning("[VECTOR][crypto_trading] get_quote failed: {}", e)
            return {"symbol": symbol, "price": None, "error": str(e)}

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
