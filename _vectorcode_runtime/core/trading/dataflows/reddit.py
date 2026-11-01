"""Reddit search fetcher for ticker-specific discussion posts.

Uses Reddit's public JSON endpoints (``reddit.com/r/{sub}/search.json``)
which do not require an API key. Public throughput is ~10 requests per
minute per IP, well within budget for a single agent run that queries
a handful of finance subreddits per ticker.

Returns formatted plaintext blocks ready for prompt injection. Degrades
gracefully — returns a placeholder string rather than raising, so callers
never have to special-case missing data.
"""

from __future__ import annotations

__all__ = [
    "DEFAULT_SUBREDDITS",
    "fetch_reddit_posts",
    "logger",
]


import http.client
import json
import time
from typing import Iterable
from loguru import logger
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_API = "https://www.reddit.com/r/{sub}/search.json?{qs}"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/VectorTrading)"

# Default subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise; stocks /
# investing trend more measured. Caller can override.
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")


def _fetch_subreddit(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict] | None:
    """Return posts, or None when the fetch itself failed (distinct from [] = no posts)."""
    qs = urlencode({
        "q": ticker,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",  # last 7 days
        "limit": limit,
    })
    url = _API.format(sub=sub, qs=qs)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except (OSError, http.client.HTTPException, ValueError) as exc:
        logger.warning("[VECTOR][reddit] fetch failed for r/{} {}: {}", sub, ticker, type(exc).__name__)
        return None
    if not isinstance(payload, dict):
        logger.warning("[VECTOR][reddit] unexpected payload for r/{} {}", sub, ticker)
        return None
    children = (payload.get("data") or {}).get("children") or []
    return [c.get("data", {}) for c in children if isinstance(c, dict)]


def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int = 5,
    timeout: float = 10.0,
    inter_request_delay: float = 0.4,
) -> str:
    """Fetch recent Reddit posts mentioning ``ticker`` across finance
    subreddits and return them as a formatted plaintext block.

    ``inter_request_delay`` keeps us under Reddit's public rate limit
    (~10 req/min per IP) even if the caller queries many subreddits.
    """
    blocks = []
    total_posts = 0
    failed = 0
    subs = list(subreddits)
    for i, sub in enumerate(subs):
        if i > 0:
            time.sleep(inter_request_delay)
        posts = _fetch_subreddit(ticker, sub, limit_per_sub, timeout)
        if posts is None:
            failed += 1
            blocks.append(f"r/{sub}: <fetch FAILED - Reddit data unavailable, NOT evidence of no discussion>")
            continue
        total_posts += len(posts)
        if not posts:
            blocks.append(f"r/{sub}: <no posts found mentioning {ticker.upper()} in the past 7 days>")
            continue

        lines = [f"r/{sub} — {len(posts)} recent posts mentioning {ticker.upper()}:"]
        for p in posts:
            title = (p.get("title") or "").replace("\n", " ").strip()
            score = p.get("score", 0)
            comments = p.get("num_comments", 0)
            created = p.get("created_utc")
            created_str = (
                time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
            )
            selftext = (p.get("selftext") or "").replace("\n", " ").strip()
            if len(selftext) > 240:
                selftext = selftext[:240] + "…"
            lines.append(
                f"  [{created_str} · {score:>4}↑ · {comments:>3}c] {title}"
                + (f"\n    body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))

    if failed == len(subs) and subs:
        return f"<Reddit unavailable: all {failed} subreddit fetches failed for {ticker.upper()}; no sentiment data>"
    if total_posts == 0 and failed == 0:
        return (
            f"<no Reddit posts found mentioning {ticker.upper()} across "
            f"{', '.join(f'r/{s}' for s in subs)} in the past 7 days>"
        )
    return "\n\n".join(blocks)
