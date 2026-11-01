"""AkShare fetcher — A-share chip distribution and capital/money flow data."""

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

class AkShareFetcher:
    """Fetch A-share market data: chip distribution, capital flow, market breadth."""

    def get_chip_distribution(self, symbol: str) -> dict:
        """Get chip distribution data (cost basis of current shareholders)."""
        try:
            import akshare as ak
            df = ak.stock_cyq_em(symbol=symbol, adjust="")
            return {"symbol": symbol, "data": df.to_dict("records")[:10] if not df.empty else []}
        except ImportError:
            logger.warning("[VECTOR][akshare] akshare not installed: pip install akshare")
            return {"symbol": symbol, "data": [], "error": "akshare not installed"}
        except Exception as e:
            logger.warning("[VECTOR][akshare] chip_distribution error: {}", e)
            return {"symbol": symbol, "data": [], "error": str(e)}

    def get_capital_flow(self, symbol: str, period: str = "daily") -> dict:
        """Get capital/money flow data (institutional vs retail)."""
        try:
            import akshare as ak
            df = ak.stock_individual_fund_flow(stock=symbol, market="sh")
            return {"symbol": symbol, "period": period, "data": df.to_dict("records")[:10] if not df.empty else []}
        except ImportError:
            return {"symbol": symbol, "data": [], "error": "akshare not installed"}
        except Exception as e:
            return {"symbol": symbol, "data": [], "error": str(e)}

if __name__ == "__main__":
    f = AkShareFetcher()
    print("✅ akshare_fetcher OK:", type(f).__name__)
