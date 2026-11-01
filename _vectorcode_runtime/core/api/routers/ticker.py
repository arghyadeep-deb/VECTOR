"""VECTOR ticker router - feeds the dashboard's top stock strip and bottom news strip.

Endpoints:
    GET /finance/ticker?symbols=AAPL,MSFT,SPY  -> latest quote per symbol
    GET /news/headlines?limit=20               -> rolling news headlines

Both endpoints are designed to be cheap and pollable every 30-60 seconds from
the dashboard. They wrap existing infrastructure rather than re-fetching:
- Finance: yfinance via core/trading/dataflows/y_finance.py if importable.
- News: districts/research/news_aggregator.py if importable.

Production rule: never return fake market prices or fake headlines as if they
were live data. If providers are unavailable, return an explicit unavailable
status with empty payloads.
"""
import asyncio

__all__ = [
    "finance_ticker",
    "news_headlines",
    "router",
]

import time
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from loguru import logger

router = APIRouter(tags=["ticker"])

# In-process cache: (timestamp, payload). Keeps API quotas low and keeps
# the marquee snappy.
_FINANCE_TTL_S = 30
_NEWS_TTL_S = 120
_finance_cache: dict[str, tuple[float, dict]] = {}
_news_cache: tuple[float, list[dict]] = (0.0, [])


# ---- Finance --------------------------------------------------------------

def _yfinance_quote(symbol: str) -> dict | None:
    """One-shot quote via yfinance. Synchronous, called inside asyncio.to_thread."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = getattr(t, "fast_info", None) or t.info
        last = float(info.get("last_price") or info.get("lastPrice") or info.get("regularMarketPrice") or 0)
        prev = float(info.get("previous_close") or info.get("previousClose") or info.get("regularMarketPreviousClose") or 0)
        if last and prev:
            change_pct = ((last - prev) / prev) * 100.0
        else:
            change_pct = 0.0
        return {
            "symbol": symbol.upper(),
            "price": round(last, 4),
            "change_pct": round(change_pct, 3),
            "currency": (info.get("currency") or "USD"),
        }
    except Exception as e:
        logger.warning(f"[VECTOR][ticker] yfinance {symbol} failed: {e}")
        return None


@router.get("/finance/ticker")
async def finance_ticker(
    symbols: str = Query(default="AAPL,MSFT,NVDA,GOOGL,TSLA,META,SPY,QQQ,BTC-USD,ETH-USD"),
):
    """Return latest quotes for a comma-separated symbol list."""
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        return JSONResponse({"quotes": [], "source": "none", "status": "empty_request"})

    now = time.time()
    out: list[dict] = []
    misses: list[str] = []

    for s in syms:
        cached = _finance_cache.get(s)
        if cached and (now - cached[0]) < _FINANCE_TTL_S:
            out.append(cached[1])
        else:
            misses.append(s)

    if misses:
        results = await asyncio.gather(
            *(asyncio.to_thread(_yfinance_quote, s) for s in misses),
            return_exceptions=True,
        )
        failures: list[str] = []
        for s, q in zip(misses, results):
            if isinstance(q, dict):
                _finance_cache[s] = (now, q)
                out.append(q)
            else:
                failures.append(s)
        status = "ok" if not failures else ("partial" if out else "unavailable")
        http_status = 200 if out else 503
        return JSONResponse(
            {
                "quotes": out,
                "source": "yfinance",
                "status": status,
                "failed_symbols": failures,
            },
            status_code=http_status,
        )

    return JSONResponse({"quotes": out, "source": "cache", "status": "ok"})


# ---- News -----------------------------------------------------------------

async def _aggregator_headlines(limit: int) -> list[dict] | None:
    """Pull headlines from districts/research/news_aggregator.py.

    The old version probed for get_headlines/fetch/headlines/latest — the
    aggregator has NONE of them (its real API is `async gather_news(...)`), so
    this always returned None and /news/headlines was a permanent 503; it also
    explicitly bailed on coroutines ("handled at call site" — it never was), and
    ran under asyncio.to_thread where awaiting was impossible anyway.
    Found by browser dogfood (2026-07-17).
    """
    try:
        from districts.research.news_aggregator import NewsAggregator  # type: ignore
    except Exception as e:
        logger.warning(f"[VECTOR][ticker] news_aggregator import failed: {e}")
        return None
    try:
        agg = NewsAggregator()
        items = await agg.gather_news(max_per_source=max(3, min(limit, 10)))
        if not isinstance(items, list) or not items:
            return None
        return [_norm_headline(it) for it in items][:limit]
    except Exception as e:
        logger.warning(f"[VECTOR][ticker] aggregator call failed: {e}")
        return None


def _norm_headline(it: Any) -> dict:
    if isinstance(it, dict):
        return {
            "title": it.get("title") or it.get("headline") or "",
            "source": it.get("source") or it.get("publisher") or "",
            "url": it.get("url") or it.get("link") or "",
            "ts": it.get("ts") or it.get("timestamp") or 0,
        }
    return {"title": str(it), "source": "", "url": "", "ts": 0}


@router.get("/news/headlines")
async def news_headlines(limit: int = Query(default=20, ge=1, le=100)):
    """Return rolling news headlines for the bottom marquee."""
    global _news_cache
    now = time.time()
    if _news_cache[1] and (now - _news_cache[0]) < _NEWS_TTL_S:
        return JSONResponse({"headlines": _news_cache[1][:limit], "source": "cache", "status": "ok"})

    items = await _aggregator_headlines(limit)
    if not items:
        return JSONResponse(
            {"headlines": [], "source": "aggregator", "status": "unavailable"},
            status_code=503,
        )

    _news_cache = (now, items)
    return JSONResponse({"headlines": items[:limit], "source": "aggregator", "status": "ok"})


if __name__ == "__main__":
    print("ticker.py OK")
