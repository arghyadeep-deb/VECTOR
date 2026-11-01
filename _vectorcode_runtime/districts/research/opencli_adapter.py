"""
OpenCLI adapter — Python wrapper around the OpenCLI npm tool.

OpenCLI turns websites into deterministic CLI interfaces with zero LLM cost.
It has pre-built adapters for HackerNews, Reddit, Twitter/X, Bilibili, Zhihu,
and 90+ other sites.

Install:
    npm install -g @jackwener/opencli
    opencli doctor          ← verify setup

If OpenCLI is not installed, falls back to VECTOR's native scrapers
(reddit_miner, news_aggregator).

RULE 11: never calls Claude/external LLM APIs.
"""
import sys
import json
import shutil
import asyncio
import subprocess


from loguru import logger
from core.city.agent_base import AgentBase
from core.config import CONFIG


def _opencli_available() -> bool:
    return shutil.which("opencli") is not None


def _run_opencli(args: list[str], timeout: float = 30.0) -> dict:
    """
    Run an opencli command and parse JSON output.
    Returns {"ok": True, "data": ...} or {"ok": False, "error": ...}.
    """
    if not _opencli_available():
        return {"ok": False, "error": "opencli not installed (npm install -g @jackwener/opencli)"}

    try:
        proc = subprocess.run(
            ["opencli"] + args + ["--format", "json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr.strip() or f"exit {proc.returncode}"}
        try:
            data = json.loads(proc.stdout)
            return {"ok": True, "data": data}
        except json.JSONDecodeError:
            # opencli returned non-JSON (some adapters return plain text)
            return {"ok": True, "data": proc.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "opencli timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class OpenCLIAdapter(AgentBase):
    """
    Wraps OpenCLI's 90+ pre-built site adapters.
    Falls back to VECTOR's native scrapers when opencli is unavailable.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        import uuid
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="OpenCLIAdapter",
            district="research",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)

        self._available = _opencli_available()
        logger.info(
            f"[VECTOR][opencli] ready available={self._available} gen={generation} hp={self.health_points}"
        )

    # ── HackerNews ────────────────────────────────────────────────────────────

    async def get_hn_top(self, limit: int = 20) -> list[dict]:
        """
        Fetch top HackerNews stories.
        Uses opencli if available, otherwise falls back to news_aggregator.
        """
        if self._available:
            result = await asyncio.get_event_loop().run_in_executor(
                None, _run_opencli, ["hn", "top", "--limit", str(limit)]
            )
            if result["ok"]:
                self.award_points(5, "opencli hn top")
                data = result["data"]
                return data if isinstance(data, list) else []
            logger.warning(f"[VECTOR][opencli] hn fallback: {result['error']}")

        # Fallback: news_aggregator
        return await self._fallback_hn(limit)

    async def _fallback_hn(self, limit: int) -> list[dict]:
        """Pull HN top stories via direct API (fallback when opencli absent)."""
        import httpx
        items = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
                ids = resp.json()[:limit]
                for story_id in ids[:10]:  # cap at 10 for speed
                    r = await client.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                    )
                    item = r.json()
                    items.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "score": item.get("score", 0),
                        "by": item.get("by", ""),
                        "source": "hn_api_fallback",
                    })
        except Exception as e:
            logger.warning(f"[VECTOR][opencli] HN fallback failed: {e}")
        return items

    # ── Reddit ────────────────────────────────────────────────────────────────

    async def get_reddit_hot(self, subreddit: str, limit: int = 10) -> list[dict]:
        """
        Fetch hot posts from a subreddit.
        opencli first, then reddit_miner fallback.
        """
        if self._available:
            result = await asyncio.get_event_loop().run_in_executor(
                None, _run_opencli, ["reddit", "hot", subreddit, "--limit", str(limit)]
            )
            if result["ok"]:
                self.award_points(5, f"opencli reddit {subreddit}")
                data = result["data"]
                return data if isinstance(data, list) else []
            logger.warning(f"[VECTOR][opencli] reddit fallback: {result['error']}")

        # Fallback: reddit_miner native scraper
        try:
            from districts.research.reddit_miner import RedditMiner
            miner = RedditMiner()
            return await miner.mine_subreddit(subreddit, limit=limit)
        except Exception as e:
            logger.warning(f"[VECTOR][opencli] reddit_miner fallback failed: {e}")
            return []

    # ── Twitter/X ─────────────────────────────────────────────────────────────

    async def get_twitter_trending(self, topic: str = "AI", limit: int = 10) -> list[dict]:
        """
        Fetch trending Twitter/X posts for a topic.
        Requires opencli with X adapter installed.
        """
        if not self._available:
            logger.warning("[VECTOR][opencli] opencli not installed — X adapter unavailable")
            return []

        result = await asyncio.get_event_loop().run_in_executor(
            None, _run_opencli, ["x", "search", topic, "--limit", str(limit)]
        )
        if result["ok"]:
            self.award_points(5, f"opencli x {topic}")
            data = result["data"]
            return data if isinstance(data, list) else []
        logger.warning(f"[VECTOR][opencli] x adapter: {result['error']}")
        return []

    # ── GitHub trending ───────────────────────────────────────────────────────

    async def get_github_trending(self, language: str = "python", limit: int = 10) -> list[dict]:
        """Fetch GitHub trending repos for a language."""
        if self._available:
            result = await asyncio.get_event_loop().run_in_executor(
                None, _run_opencli, ["github", "trending", "--lang", language, "--limit", str(limit)]
            )
            if result["ok"]:
                self.award_points(5, "opencli github trending")
                data = result["data"]
                return data if isinstance(data, list) else []
            logger.warning(f"[VECTOR][opencli] github trending fallback: {result['error']}")

        # Fallback: GitHub public trending API
        return await self._fallback_github_trending(language, limit)

    async def _fallback_github_trending(self, language: str, limit: int) -> list[dict]:
        import httpx, datetime
        items = []
        try:
            since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            url = (
                f"https://api.github.com/search/repositories"
                f"?q=language:{language}+created:>{since}&sort=stars&order=desc&per_page={limit}"
            )
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={"Accept": "application/vnd.github+json"})
                for repo in resp.json().get("items", []):
                    items.append({
                        "name": repo.get("full_name", ""),
                        "description": repo.get("description", ""),
                        "stars": repo.get("stargazers_count", 0),
                        "url": repo.get("html_url", ""),
                        "source": "github_api_fallback",
                    })
        except Exception as e:
            logger.warning(f"[VECTOR][opencli] GitHub fallback failed: {e}")
        return items

    # ── Diagnostic ────────────────────────────────────────────────────────────

    def check_health(self) -> dict:
        """Return OpenCLI availability and adapter status."""
        if not self._available:
            return {
                "available": False,
                "message": "Install: npm install -g @jackwener/opencli",
            }
        result = _run_opencli(["doctor"])
        return {"available": True, "doctor": result.get("data", "ok")}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        adapter = OpenCLIAdapter(generation=1)
        assert adapter.name == "OpenCLIAdapter"
        assert adapter.district == "research"

        health = adapter.check_health()
        print(f"  OpenCLI available: {health['available']}")

        # HN fetch — uses fallback if opencli absent
        hn = await adapter.get_hn_top(limit=3)
        assert isinstance(hn, list), f"Expected list, got {type(hn)}"
        print(f"  HN top (3): {len(hn)} items fetched")
        if hn:
            print(f"    #1: {hn[0].get('title', '?')[:60]}")

        # GitHub trending fallback
        gh = await adapter.get_github_trending("python", limit=3)
        assert isinstance(gh, list), f"Expected list, got {type(gh)}"
        print(f"  GitHub trending python (3): {len(gh)} items")

        print(f"✅ opencli_adapter.py OK  HP={adapter.health_points}")

    asyncio.run(_smoke())
