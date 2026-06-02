
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import sys
import time
import uuid
import json
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class _TTLCache:
    """Simple time-to-live cache to deduplicate repeated API calls."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: dict = {}
        self._ttl = ttl_seconds

    def get(self, key: str):
        entry = self._cache.get(key)
        if entry and time.time() - entry["ts"] < self._ttl:
            return entry["val"]
        return None

    def set(self, key: str, val) -> None:
        self._cache[key] = {"val": val, "ts": time.time()}


class StockAnalyst(AgentBase):
    """
    Provides stock analysis using yfinance for market data
    and Ollama for investment insights.
    """

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "StockAnalyst", "investment")
        if ghost:
            self.inherit_ghost(ghost)

        self._yfinance_available = self._check_yfinance()
        self._analysis_cache: dict[str, dict] = {}
        self._quote_cache = _TTLCache(300)
        logger.info(f"[VECTOR][stock_analyst] StockAnalyst initialized - yfinance: {self._yfinance_available}")

    def _check_yfinance(self) -> bool:
        """Check if yfinance is available and compatible with current Python version."""
        try:
            import yfinance
            return True
        except (ImportError, AttributeError, Exception) as e:
            logger.warning("[VECTOR][stock_analyst] yfinance unavailable: {} — using mock data", e)
            return False

    def get_quote(self, symbol: str) -> dict:
        """
        Get current stock quote for a symbol.
        Results are TTL-cached for 5 minutes to avoid redundant API calls.
        Falls back to get_nse_quote if yfinance returns an error.
        """
        symbol = symbol.upper().strip()

        cached = self._quote_cache.get(symbol)
        if cached is not None:
            return cached

        if self._yfinance_available:
            result = self._get_real_quote(symbol)
            # If yfinance returned an error, try NSE fallback
            if result.get("status") == "error":
                logger.warning(f"[VECTOR][stock_analyst] yfinance failed for {symbol}, trying NSE fallback")
                nse_result = self.get_nse_quote(symbol)
                if nse_result.get("status") == "success":
                    self._quote_cache.set(symbol, nse_result)
                    return nse_result
            if result.get("status") == "success":
                self._quote_cache.set(symbol, result)
            return result

        result = self._get_mock_quote(symbol)
        self._quote_cache.set(symbol, result)
        return result

    def _get_real_quote(self, symbol: str) -> dict:
        """Get real quote using yfinance."""
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "status": "success",
                "symbol": symbol,
                "price": info.get("currentPrice", info.get("regularMarketPrice")),
                "change": info.get("regularMarketChange", 0),
                "change_percent": info.get("regularMarketChangePercent", 0),
                "volume": info.get("averageVolume", 0),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "day_high": info.get("dayHigh"),
                "day_low": info.get("dayLow"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "source": "yfinance"
            }

        except Exception as e:
            logger.error(f"[VECTOR][stock_analyst] Failed to get quote for {symbol}: {e}")
            return {"symbol": symbol, "status": "error", "message": str(e)}

    def _get_mock_quote(self, symbol: str) -> dict:
        """Return mock quote data."""
        hash_val = sum(ord(c) for c in symbol)
        base_price = 100 + (hash_val % 400)
        change = ((hash_val % 20) - 10) / 2

        return {
            "status": "success",
            "symbol": symbol,
            "price": round(base_price, 2),
            "change": round(change, 2),
            "change_percent": round((change / base_price) * 100, 2),
            "volume": (hash_val * 10000) % 50000000,
            "market_cap": base_price * 1000000000,
            "pe_ratio": round(15 + (hash_val % 20), 1),
            "day_high": round(base_price * 1.02, 2),
            "day_low": round(base_price * 0.98, 2),
            "52w_high": round(base_price * 1.3, 2),
            "52w_low": round(base_price * 0.7, 2),
            "source": "mock"
        }

    def get_nse_quote(self, symbol: str) -> dict:
        """
        Get current quote for an NSE-listed stock via Yahoo Finance API.
        Automatically falls back to BSE (.BO) if NSE (.NS) fails.
        """
        symbol = symbol.upper().strip()
        suffixes = [(".NS", "NSE"), (".BO", "BSE")]

        import httpx

        for suffix, exchange in suffixes:
            ticker = f"{symbol}{suffix}"
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                f"?interval=1d&range=1d"
            )
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    response.raise_for_status()
                    data = response.json()

                result_obj = data.get("chart", {}).get("result", [])
                if not result_obj:
                    logger.warning(f"[VECTOR][stock_analyst] No chart result for {ticker}, trying next suffix")
                    continue

                meta = result_obj[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")

                change = round(price - prev_close, 4) if (price and prev_close) else None
                change_pct = round((change / prev_close) * 100, 4) if (change is not None and prev_close) else None

                self.award_points(5, f"nse_quote_{symbol}")
                logger.info(f"[VECTOR][stock_analyst] NSE quote fetched: {symbol} via {exchange} @ {price}")

                return {
                    "status": "success",
                    "symbol": symbol,
                    "price": price,
                    "change": change,
                    "change_pct": change_pct,
                    "volume": meta.get("regularMarketVolume"),
                    "high": meta.get("regularMarketDayHigh"),
                    "low": meta.get("regularMarketDayLow"),
                    "exchange": exchange,
                    "source": "yahoo_finance"
                }

            except Exception as e:
                logger.warning(f"[VECTOR][stock_analyst] Yahoo Finance failed for {ticker}: {e}")
                continue

        logger.error(f"[VECTOR][stock_analyst] NSE/BSE quote failed for {symbol} on all suffixes")
        return {"status": "error", "symbol": symbol, "error": f"Quote unavailable for {symbol} on NSE/BSE"}

    def get_crypto_quote(self, coin_id: str = "bitcoin") -> dict:
        """
        Get current crypto quote from CoinGecko (no auth required).
        Includes USD and INR prices.
        """
        coin_id = coin_id.lower().strip()
        url = (
            f"https://api.coingecko.com/api/v3/coins/{coin_id}"
            f"?localization=false&tickers=false&community_data=false"
        )

        try:
            import httpx

            inr_rate = CONFIG.get("usd_to_inr", 83.5)

            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers={"Accept": "application/json"})
                response.raise_for_status()
                data = response.json()

            market = data.get("market_data", {})
            price_usd = market.get("current_price", {}).get("usd")
            price_inr = round(price_usd * inr_rate, 2) if price_usd else None

            self.award_points(5, f"crypto_quote_{coin_id}")
            logger.info(f"[VECTOR][stock_analyst] Crypto quote fetched: {coin_id} @ ${price_usd}")

            return {
                "status": "success",
                "coin": data.get("id"),
                "symbol": data.get("symbol", "").upper(),
                "price_usd": price_usd,
                "price_inr": price_inr,
                "change_24h_pct": market.get("price_change_percentage_24h"),
                "market_cap": market.get("market_cap", {}).get("usd"),
                "volume_24h": market.get("total_volume", {}).get("usd"),
                "high_24h": market.get("high_24h", {}).get("usd"),
                "low_24h": market.get("low_24h", {}).get("usd"),
                "source": "coingecko"
            }

        except Exception as e:
            logger.error(f"[VECTOR][stock_analyst] CoinGecko quote failed for {coin_id}: {e}")
            return {"status": "error", "coin": coin_id, "error": str(e)}

    def get_top_cryptos(self, limit: int = 10) -> list[dict]:
        """
        Get top cryptocurrencies by market cap from CoinGecko (no auth required).
        """
        url = (
            f"https://api.coingecko.com/api/v3/coins/markets"
            f"?vs_currency=usd&order=market_cap_desc&per_page={limit}&sparkline=false"
        )

        try:
            import httpx

            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers={"Accept": "application/json"})
                response.raise_for_status()
                data = response.json()

            result = [
                {
                    "rank": item.get("market_cap_rank"),
                    "coin": item.get("id"),
                    "symbol": (item.get("symbol") or "").upper(),
                    "name": item.get("name"),
                    "price_usd": item.get("current_price"),
                    "change_24h_pct": item.get("price_change_percentage_24h"),
                    "market_cap": item.get("market_cap"),
                    "volume_24h": item.get("total_volume"),
                }
                for item in data
            ]

            logger.info(f"[VECTOR][stock_analyst] Top {limit} cryptos fetched from CoinGecko")
            return result

        except Exception as e:
            logger.error(f"[VECTOR][stock_analyst] CoinGecko top-cryptos failed: {e}")
            return [{"status": "error", "error": str(e)}]

    def analyze_sentiment(self, symbol: str) -> dict:
        """
        Analyze sentiment for a stock based on recent news and data.
        """
        symbol = symbol.upper()

        if symbol in self._analysis_cache:
            return self._analysis_cache[symbol]

        quote = self.get_quote(symbol)

        prompt = f"""Analyze the sentiment for {symbol} based on this market data:

Current Price: ${quote.get('price', 'N/A')}
Change: {quote.get('change', 'N/A')} ({quote.get('change_percent', 'N/A')}%)

Provide:
1. Overall Sentiment (bullish, bearish, neutral)
2. Confidence Level (high, medium, low)
3. Key Factors Driving Sentiment
4. Risk Factors
5. Investment Outlook (short-term, long-term)

Be balanced and provide specific reasoning.
"""

        try:
            import httpx

            ollama_host = CONFIG["ollama_host"]
            if not ollama_host.startswith("http"):
                ollama_host = "http://" + ollama_host

            model = CONFIG["models"]["focus"]

            response = httpx.post(
                f"{ollama_host}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            analysis = result.get("response", "").strip()

            sentiment_data = {
                "symbol": symbol,
                "sentiment": self._parse_sentiment(analysis),
                "analysis": analysis,
                "quote": quote,
                "timestamp": self._get_timestamp()
            }

            self._analysis_cache[symbol] = sentiment_data
            self.award_points(10, f"sentiment_analyzed_{symbol}")

            return sentiment_data

        except Exception as e:
            logger.error(f"[VECTOR][stock_analyst] Sentiment analysis failed: {e}")
            return {"symbol": symbol, "status": "error", "message": str(e)}

    def _parse_sentiment(self, analysis: str) -> str:
        """Parse sentiment from analysis text."""
        analysis_lower = analysis.lower()
        bullish_count = analysis_lower.count("bullish") + analysis_lower.count("positive") + analysis_lower.count("buy")
        bearish_count = analysis_lower.count("bearish") + analysis_lower.count("negative") + analysis_lower.count("sell")

        if bullish_count > bearish_count:
            return "bullish"
        elif bearish_count > bullish_count:
            return "bearish"
        return "neutral"

    def get_fundamentals(self, symbol: str) -> dict:
        """
        Get fundamental data for a stock.
        """
        symbol = symbol.upper()

        if self._yfinance_available:
            return self._get_real_fundamentals(symbol)
        return self._get_mock_fundamentals(symbol)

    def _get_real_fundamentals(self, symbol: str) -> dict:
        """Get real fundamentals using yfinance."""
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "status": "success",
                "symbol": symbol,
                "company_name": info.get("shortName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "eps": info.get("trailingEps"),
                "revenue": info.get("totalRevenue"),
                "revenue_growth": info.get("revenueGrowth"),
                "profit_margin": info.get("profitMargin"),
                "debt_to_equity": info.get("debtToEquity"),
                "return_on_equity": info.get("returnOnEquity"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "source": "yfinance"
            }

        except Exception as e:
            logger.error(f"[VECTOR][stock_analyst] Fundamentals fetch failed: {e}")
            return {"symbol": symbol, "status": "error", "message": str(e)}

    def _get_mock_fundamentals(self, symbol: str) -> dict:
        """Return mock fundamental data."""
        hash_val = sum(ord(c) for c in symbol)

        return {
            "status": "success",
            "symbol": symbol,
            "company_name": f"{symbol} Inc.",
            "sector": "Technology",
            "industry": "Software",
            "market_cap": 100000000000 * (hash_val % 10 + 1),
            "pe_ratio": round(15 + (hash_val % 25), 1),
            "forward_pe": round(12 + (hash_val % 20), 1),
            "peg_ratio": round(1 + (hash_val % 3), 1),
            "eps": round(2 + (hash_val % 10) / 10, 2),
            "revenue": 50000000000 * (hash_val % 5 + 1),
            "revenue_growth": round(5 + (hash_val % 20), 1),
            "profit_margin": round(10 + (hash_val % 30), 1),
            "debt_to_equity": round(30 + (hash_val % 100), 1),
            "return_on_equity": round(15 + (hash_val % 20), 1),
            "dividend_yield": round((hash_val % 5) / 10, 2),
            "beta": round(0.8 + (hash_val % 40) / 100, 2),
            "source": "mock"
        }

    def generate_insight(self, symbol: str) -> dict:
        """
        Generate AI-powered investment insight for a stock.
        """
        symbol = symbol.upper()

        quote = self.get_quote(symbol)
        fundamentals = self.get_fundamentals(symbol)

        prompt = f"""Generate an investment insight for {symbol} based on:

Market Data:
- Price: ${quote.get('price', 'N/A')}
- Change: {quote.get('change', 'N/A')} ({quote.get('change_percent', 'N/A')}%)
- Volume: {quote.get('volume', 'N/A'):,}

Fundamentals:
- Market Cap: ${(fundamentals.get('market_cap', 0) / 1000000000):.1f}B
- P/E Ratio: {fundamentals.get('pe_ratio', 'N/A')}
- Revenue Growth: {fundamentals.get('revenue_growth', 'N/A')}%
- Profit Margin: {fundamentals.get('profit_margin', 'N/A')}%
- ROE: {fundamentals.get('return_on_equity', 'N/A')}%

Provide:
1. Quick Take (2-3 sentences)
2. Investment Thesis (bull case)
3. Risk Factors (bear case)
4. Valuation Assessment
5. Recommendation (buy/hold/sell with rationale)

Be specific and balanced.
"""

        try:
            import httpx

            ollama_host = CONFIG["ollama_host"]
            if not ollama_host.startswith("http"):
                ollama_host = "http://" + ollama_host

            model = CONFIG["models"]["focus"]

            response = httpx.post(
                f"{ollama_host}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=60.0
            )
            response.raise_for_status()
            result = response.json()
            insight = result.get("response", "").strip()

            self.award_points(15, f"insight_generated_{symbol}")

            return {
                "status": "success",
                "symbol": symbol,
                "insight": insight,
                "quote": quote,
                "fundamentals": fundamentals,
                "timestamp": self._get_timestamp()
            }

        except Exception as e:
            logger.error(f"[VECTOR][stock_analyst] Insight generation failed: {e}")
            return {"symbol": symbol, "status": "error", "message": str(e)}

    def compare_stocks(self, symbols: list[str]) -> dict:
        """
        Compare multiple stocks side by side.
        """
        quotes = {sym: self.get_quote(sym.upper()) for sym in symbols}
        fundamentals = {sym: self.get_fundamentals(sym.upper()) for sym in symbols}

        comparison = {
            "status": "success",
            "symbols": symbols,
            "quotes": quotes,
            "fundamentals": fundamentals,
            "rankings": self._rank_stocks(quotes, fundamentals),
            "timestamp": self._get_timestamp()
        }

        self.award_points(10, "stocks_compared")
        return comparison

    def _rank_stocks(self, quotes: dict, fundamentals: dict) -> dict:
        """Rank stocks by various metrics."""
        rankings = {
            "by_price_momentum": [],
            "by_valuation": [],
            "by_growth": [],
            "by_market_cap": []
        }

        for sym in quotes:
            q = quotes[sym]
            f = fundamentals.get(sym, {})

            rankings["by_price_momentum"].append({
                "symbol": sym,
                "change_percent": q.get("change_percent", 0)
            })
            rankings["by_valuation"].append({
                "symbol": sym,
                "pe_ratio": f.get("pe_ratio", 999)
            })
            rankings["by_growth"].append({
                "symbol": sym,
                "revenue_growth": f.get("revenue_growth", 0)
            })
            rankings["by_market_cap"].append({
                "symbol": sym,
                "market_cap": f.get("market_cap", 0)
            })

        for key in rankings:
            if key == "by_valuation":
                rankings[key].sort(key=lambda x: x["pe_ratio"] if x["pe_ratio"] else 999)
            else:
                rankings[key].sort(key=lambda x: x.get(list(x.keys())[1], 0), reverse=True)

        return rankings

    def get_alpha_factors(self, symbol: str, limit: int = 20) -> list[str]:
        """Return a sample of alpha factor names from the Alpha Zoo (458 WorldQuant-style factors)."""
        try:
            from districts.investment.alpha_zoo import AlphaZooLoader
            loader = AlphaZooLoader()
            all_factors = loader.list_factors()
            # Deduplicate and return evenly-spaced sample across the zoo
            unique = list(dict.fromkeys(all_factors))  # preserve order, remove dups
            step = max(1, len(unique) // limit)
            sample = unique[::step][:limit]
            logger.debug("[VECTOR][stock_analyst] alpha_zoo: {} unique factors, returning {}", len(unique), len(sample))
            return sample
        except Exception as e:
            logger.debug("[VECTOR][stock_analyst] alpha_zoo unavailable: {}", e)
            return []

    async def screen_stocks(self, symbols: list[str], filters: dict) -> list[dict]:
        """Screen stocks by fundamental filters.

        Args:
            symbols: List of ticker symbols to evaluate.
            filters: Dict mapping field names to constraint dicts.
                     Example::

                         {
                             "pe_ratio":      {"max": 20},
                             "market_cap":    {"min": 1e9},
                             "profit_margin": {"min": 0.1},
                         }

                     Supported fields: any key returned by get_quote() or
                     get_fundamentals() (e.g. price, market_cap, pe_ratio,
                     forward_pe, revenue_growth, profit_margin, debt_to_equity,
                     return_on_equity, dividend_yield, beta).

        Returns:
            List of dicts for symbols that passed all filters, each with keys
            ``symbol``, ``data`` (merged quote+fundamentals), and ``passed=True``.
        """
        results = []
        for symbol in symbols:
            try:
                quote = self.get_quote(symbol)
                fundamentals = self.get_fundamentals(symbol)
                data = {**quote, **fundamentals}

                passes = True
                for field, constraints in filters.items():
                    val = data.get(field)
                    if val is None:
                        passes = False
                        break
                    if "min" in constraints and val < constraints["min"]:
                        passes = False
                        break
                    if "max" in constraints and val > constraints["max"]:
                        passes = False
                        break

                if passes:
                    results.append({"symbol": symbol, "data": data, "passed": True})
            except Exception as e:
                logger.debug("[VECTOR][screener] {} error: {}", symbol, e)

        self.award_points(len(results) * 2, "stock_screening")
        return results

    def get_equity_screener(
        self,
        exchange: str = "NSE",
        market_cap_min: float = 1e9,
        pe_max: float = 30.0,
        limit: int = 20,
    ) -> dict:
        """Screen equities with expanded filter set.

        Evaluates a built-in watchlist of top NSE/BSE and US large-caps and
        returns those passing market_cap_min and pe_max thresholds.

        Args:
            exchange:       Label for the result dict (informational only).
            market_cap_min: Minimum market capitalisation in USD (default 1 B).
            pe_max:         Maximum trailing P/E ratio (default 30).
            limit:          Maximum number of symbols to evaluate (default 20).

        Returns:
            Dict with keys ``exchange``, ``filters_applied``, and ``results``
            (list of dicts with symbol, price, market_cap, pe_ratio).
        """
        watchlist = [
            "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
            "BHARTIARTL", "ITC", "KOTAKBANK", "LT", "SBIN",
            "WIPRO", "HCLTECH", "SUNPHARMA", "MARUTI", "TITAN",
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
        ]
        results = []
        for sym in watchlist[:limit]:
            try:
                q = self.get_quote(sym)
                f = self.get_fundamentals(sym)
                mc = f.get("market_cap") or 0
                pe = f.get("pe_ratio") or 999
                if mc >= market_cap_min and pe <= pe_max:
                    results.append({
                        "symbol": sym,
                        "price": q.get("price"),
                        "market_cap": mc,
                        "pe_ratio": pe,
                    })
            except Exception:
                continue

        return {
            "exchange": exchange,
            "filters_applied": {
                "market_cap_min": market_cap_min,
                "pe_max": pe_max,
            },
            "results": results,
        }

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        symbol = p.get("symbol", "RELIANCE")
        result = self.get_quote(symbol)
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    analyst = StockAnalyst()

    quote = analyst.get_quote("AAPL")
    print(f"AAPL Price: ${quote.get('price', 'N/A')}")

    insight = analyst.generate_insight("MSFT")
    print(f"MSFT Insight: {insight.get('insight', 'N/A')[:100]}...")

    print("✅ stock_analyst.py OK")
