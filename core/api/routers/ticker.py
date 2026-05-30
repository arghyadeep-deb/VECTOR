"""VECTOR ticker router Ã¢â‚¬— feeds the dashboard's top stock strip and bottom news strip.

Endpoints:
    GET /finance/ticker?symbols=AAPL,MSFT,SPY  -> latest quote per symbol
    GET /news/headlines?limit=20               -> rolling news headlines

Both endpoints are designed to be cheap and pollable every 30-60 seconds from
the dashboard. They wrap existing infrastructure rather than re-fetching:
- Finance: yfinance via core/trading/dataflows/y_finance.py if importable,
  else a hard-coded mock so the marquee always demos.
- News: districts/research/news_aggregator.py if importable, else a fallback.
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

_FALLBACK_QUOTES = [
    {"symbol": "AAPL", "price": 234.07, "change_pct": +0.42, "currency": "USD"},
    {"symbol": "MSFT", "price": 428.13, "change_pct": -0.18, "currency": "USD"},
    {"symbol": "NVDA", "price": 1182.50, "change_pct": +1.24, "currency": "USD"},
    {"symbol": "GOOGL", "price": 178.94, "change_pct": +0.31, "currency": "USD"},
    {"symbol": "TSLA", "price": 248.63, "change_pct": -1.07, "currency": "USD"},
    {"symbol": "META", "price": 502.39, "change_pct": +0.65, "currency": "USD"},
    {"symbol": "SPY", "price": 545.18, "change_pct": +0.12, "currency": "USD"},
    {"symbol": "QQQ", "price": 471.24, "change_pct": +0.27, "currency": "USD"},
    {"symbol": "BTC-USD", "price": 67342.10, "change_pct": +2.18, "currency": "USD"},
    {"symbol": "ETH-USD", "price": 2456.71, "change_pct": +1.43, "currency": "USD"},
]


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
        return JSONResponse({"quotes": _FALLBACK_QUOTES, "source": "fallback"})

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
        used_fallback = False
        for s, q in zip(misses, results):
            if isinstance(q, dict):
                _finance_cache[s] = (now, q)
                out.append(q)
            else:
                used_fallback = True
                fb = next((x for x in _FALLBACK_QUOTES if x["symbol"] == s), None)
                if fb:
                    out.append(fb)
        return JSONResponse({"quotes": out, "source": "yfinance" if not used_fallback else "mixed"})

    return JSONResponse({"quotes": out, "source": "cache"})


# ---- News -----------------------------------------------------------------

_FALLBACK_NEWS = [
    {"title": "BREAKING: VECTOR autonomous loop online", "source": "VECTOR", "ts": 0},
    {"title": "Markets mixed as central banks signal caution", "source": "Reuters", "ts": 0},
    {"title": "AI agents cross 1B daily decisions globally", "source": "TechCrunch", "ts": 0},
    {"title": "Defense talks resume in Geneva", "source": "AP", "ts": 0},
    {"title": "New satellite constellation reaches LEO", "source": "Spaceflight Now", "ts": 0},
    {"title": "Energy markets stabilize after volatile week", "source": "Bloomberg", "ts": 0},
]


def _aggregator_headlines(limit: int) -> list[dict] | None:
    """Use districts/research/news_aggregator.py if importable."""
    try:
        from districts.research.news_aggregator import NewsAggregator  # type: ignore
    except Exception as e:
        logger.warning(f"[VECTOR][ticker] news_aggregator import failed: {e}")
        return None
    try:
        agg = NewsAggregator()
        # Common signatures: get_headlines(limit) or fetch(limit)
        for fn in ("get_headlines", "fetch", "headlines", "latest"):
            if hasattr(agg, fn):
                items: Any = getattr(agg, fn)(limit) if callable(getattr(agg, fn)) else None
                if asyncio.iscoroutine(items):
                    return None  # async path Ã¢â‚¬— handled at call site
                if isinstance(items, list):
                    return [_norm_headline(it) for it in items][:limit]
        return None
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
        return JSONResponse({"headlines": _news_cache[1][:limit], "source": "cache"})

    items = await asyncio.to_thread(_aggregator_headlines, limit)
    if not items:
        items = list(_FALLBACK_NEWS)

    _news_cache = (now, items)
    return JSONResponse({"headlines": items[:limit], "source": "aggregator" if items != _FALLBACK_NEWS else "fallback"})


if __name__ == "__main__":
    print("ticker.py OK")
