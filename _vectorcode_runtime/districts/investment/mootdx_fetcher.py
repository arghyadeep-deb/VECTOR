"""mootdx A-share market data fetcher (Chinese stocks via mootdx protocol)."""

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

class MootdxFetcher:
    """Fetch A-share (SSE/SZSE) market data using mootdx protocol."""

    def get_realtime_quote(self, symbol: str, market: str = "sh") -> dict:
        """Get real-time A-share quote. market='sh' (Shanghai) or 'sz' (Shenzhen)."""
        try:
            from mootdx.quotes import Quotes
            client = Quotes.factory(market='std')
            df = client.quotes(symbol=[symbol])
            if df is not None and not df.empty:
                row = df.iloc[0]
                return {
                    "symbol": symbol,
                    "price": float(row.get("price", 0)),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "volume": float(row.get("vol", 0)),
                    "source": "mootdx",
                }
        except ImportError:
            logger.warning("[VECTOR][mootdx] mootdx not installed: pip install mootdx")
        except Exception as e:
            logger.warning("[VECTOR][mootdx] get_realtime_quote error: {}", e)
        return {"symbol": symbol, "price": 0.0, "error": "mootdx unavailable"}

    def get_history(self, symbol: str, start: str, end: str) -> list[dict]:
        """Get A-share historical OHLCV data."""
        try:
            from mootdx.reader import Reader
            reader = Reader.factory(market="std")
            df = reader.daily(symbol=symbol, start=start, end=end)
            if df is not None and not df.empty:
                return df.reset_index().to_dict("records")
        except ImportError:
            logger.warning("[VECTOR][mootdx] mootdx not installed")
        except Exception as e:
            logger.warning("[VECTOR][mootdx] get_history error: {}", e)
        return []

if __name__ == "__main__":
    f = MootdxFetcher()
    print("✅ mootdx_fetcher OK:", type(f).__name__)
