"""
OpenCLI tool for VectorCode — web research without API keys.

OpenCLI turns websites into deterministic CLI interfaces.
Install: npm install -g @jackwener/opencli

Falls back to DuckDuckGo + direct HN/GitHub APIs when opencli is absent.
No AgentBase dependency — pure standalone tool.
"""
import sys
import json
import shutil
import subprocess
import asyncio

from loguru import logger


def _opencli_available() -> bool:
    return shutil.which("opencli") is not None


def _run_opencli(args: list[str], timeout: float = 30.0) -> dict:
    """Run opencli subprocess and parse JSON. Returns {ok, data} or {ok, error}."""
    if not _opencli_available():
        return {"ok": False, "error": "opencli not installed"}
    try:
        proc = subprocess.run(
            ["opencli"] + args + ["--format", "json"],
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr.strip() or f"exit {proc.returncode}"}
        try:
            return {"ok": True, "data": json.loads(proc.stdout)}
        except json.JSONDecodeError:
            return {"ok": True, "data": proc.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "opencli timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class OpenCLITool:
    """
    VectorCode web research tool wrapping OpenCLI + fallback scrapers.

    Supports:
      search(query)           — DuckDuckGo web search (no API key)
      hn_top(limit)           — HackerNews top stories
      reddit_hot(sub, limit)  — Reddit hot posts
      github_trending(lang)   — GitHub trending repos
      twitter_trending(topic) — Twitter/X trending (opencli required)
    """

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self._available = _opencli_available()
        logger.debug(f"[VECTOR][opencli] available={self._available}")

    # ── Web search (DuckDuckGo — no API key) ─────────────────────────────────

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search the web via DuckDuckGo. Returns [{title, url, snippet}]."""
        # Try opencli web adapter first
        if self._available:
            result = _run_opencli(["search", query, "--limit", str(max_results)], self.timeout)
            if result["ok"]:
                data = result["data"]
                return data if isinstance(data, list) else []

        # Fallback: keyless search (ddgs, then DuckDuckGo HTML). Empty means "no results";
        # an error is returned as a visible "Search unavailable" row, never as invented results.
        try:
            from tools import web_keyless
            payload = web_keyless.search(query, max_results)
        except Exception as e:
            logger.warning(f"[VECTOR][opencli] keyless search failed: {e}")
            return [{"title": "Search unavailable", "url": "", "snippet": str(e)}]
        rows = [{"title": r["title"], "url": r["url"], "snippet": r["description"]}
                for r in payload["data"]["web"]]
        if rows or not payload.get("error"):
            return rows
        return [{"title": "Search unavailable", "url": "", "snippet": payload["error"]}]

    # ── HackerNews ────────────────────────────────────────────────────────────

    def hn_top(self, limit: int = 10) -> list[dict]:
        """Fetch HackerNews top stories. opencli first, then HN Firebase API."""
        if self._available:
            r = _run_opencli(["hn", "top", "--limit", str(limit)], self.timeout)
            if r["ok"] and isinstance(r["data"], list):
                return r["data"]

        # Fallback: HN Firebase API
        try:
            import httpx
            with httpx.Client(timeout=15) as client:
                ids = client.get("https://hacker-news.firebaseio.com/v0/topstories.json").json()
                items = []
                for sid in ids[:min(limit, 15)]:
                    item = client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json").json()
                    items.append({
                        "title": item.get("title", ""), "url": item.get("url", ""),
                        "score": item.get("score", 0), "by": item.get("by", ""),
                        "source": "hn_api",
                    })
                return items
        except Exception as e:
            logger.warning(f"[VECTOR][opencli] HN fallback failed: {e}")
            return []

    # ── Reddit ────────────────────────────────────────────────────────────────

    def reddit_hot(self, subreddit: str, limit: int = 10) -> list[dict]:
        """Fetch hot posts from a subreddit. opencli first, then Reddit JSON API."""
        if self._available:
            r = _run_opencli(["reddit", "hot", subreddit, "--limit", str(limit)], self.timeout)
            if r["ok"] and isinstance(r["data"], list):
                return r["data"]

        # Fallback: Reddit JSON API (old.reddit.com)
        try:
            import httpx
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
            resp = httpx.get(url, headers={"User-Agent": "VectorCode/0.1"}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            posts = []
            for child in data.get("data", {}).get("children", []):
                d = child.get("data", {})
                posts.append({
                    "title": d.get("title", ""), "url": d.get("url", ""),
                    "score": d.get("score", 0), "author": d.get("author", ""),
                    "subreddit": subreddit, "source": "reddit_api",
                })
            return posts
        except Exception as e:
            logger.warning(f"[VECTOR][opencli] Reddit fallback failed: {e}")
            return []

    # ── GitHub trending ───────────────────────────────────────────────────────

    def github_trending(self, language: str = "python", limit: int = 10) -> list[dict]:
        """Fetch GitHub trending repos. opencli first, then GitHub search API."""
        if self._available:
            r = _run_opencli(["github", "trending", "--lang", language,
                               "--limit", str(limit)], self.timeout)
            if r["ok"] and isinstance(r["data"], list):
                return r["data"]

        # Fallback: GitHub search API (no auth, rate limited)
        try:
            import httpx, datetime
            since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            url = (f"https://api.github.com/search/repositories"
                   f"?q=language:{language}+created:>{since}&sort=stars&order=desc&per_page={limit}")
            resp = httpx.get(url, headers={"Accept": "application/vnd.github+json",
                                           "User-Agent": "VectorCode/0.1"}, timeout=15)
            resp.raise_for_status()
            items = []
            for repo in resp.json().get("items", []):
                items.append({
                    "name": repo.get("full_name", ""),
                    "description": repo.get("description", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "url": repo.get("html_url", ""),
                    "source": "github_api",
                })
            return items
        except Exception as e:
            logger.warning(f"[VECTOR][opencli] GitHub trending fallback failed: {e}")
            return []

    # ── Twitter/X ────────────────────────────────────────────────────────────

    def twitter_trending(self, topic: str = "AI", limit: int = 10) -> list[dict]:
        """Fetch Twitter/X trending posts. Requires opencli with X adapter."""
        if not self._available:
            return [{"title": "X adapter requires opencli",
                     "url": "https://github.com/jackwener/opencli",
                     "snippet": "Install: npm install -g @jackwener/opencli"}]
        r = _run_opencli(["x", "search", topic, "--limit", str(limit)], self.timeout)
        return r["data"] if r["ok"] and isinstance(r["data"], list) else []

    # ── Health / diagnostics ──────────────────────────────────────────────────

    def check_health(self) -> dict:
        if not self._available:
            return {"available": False, "message": "npm install -g @jackwener/opencli"}
        r = _run_opencli(["doctor"], timeout=10.0)
        return {"available": True, "doctor": r.get("data", "ok")}

    # ── Formatting ────────────────────────────────────────────────────────────

    def format_results(self, results: list[dict]) -> str:
        if not results:
            return "No results found."
        lines = []
        for i, r in enumerate(results, 1):
            title   = r.get("title") or r.get("name", "?")
            url     = r.get("url", "")
            snippet = r.get("snippet") or r.get("description", "")
            score   = r.get("score") or r.get("stars")
            lines.append(f"{i}. {title}")
            if url:
                lines.append(f"   {url}")
            if score is not None:
                lines.append(f"   score/stars: {score}")
            if snippet:
                lines.append(f"   {snippet[:200]}")
            lines.append("")
        return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    tool = OpenCLITool(timeout=10)

    health = tool.check_health()
    print(f"  OpenCLI available: {health['available']}")

    # Search (always works via fallback)
    results = tool.search("Python async best practices", max_results=3)
    assert isinstance(results, list), f"Expected list, got {type(results)}"
    print(f"  search results: {len(results)} items")

    # HN top (always works via HN API fallback)
    hn = tool.hn_top(limit=3)
    assert isinstance(hn, list)
    print(f"  HN top (3): {len(hn)} items")
    if hn:
        print(f"    #1: {hn[0].get('title','?')[:60]}")

    # GitHub trending (always works via GitHub API fallback)
    gh = tool.github_trending("python", limit=3)
    assert isinstance(gh, list)
    print(f"  GitHub trending python: {len(gh)} items")

    # Format
    fmt = tool.format_results(results[:2])
    assert len(fmt) > 0
    print("  format OK")

    print("✅ opencli_tool.py OK")
