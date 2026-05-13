"""Web tools for VectorCode — web_search, web_fetch.

Risk level: safe (read-only, no side effects).
"""

import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

from loguru import logger


class WebTools:
    """
    Web search and fetch tools for VectorCode agents.
    Uses httpx for fetching; DuckDuckGo Lite for search (no API key required).
    """

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout

    # ── web_fetch ─────────────────────────────────────────────────────────────

    def web_fetch(self, url: str, raw: bool = False) -> str:
        """
        Fetch the content of a URL and return readable text.
        Strips HTML tags by default. Returns raw HTML if raw=True.
        """
        try:
            import httpx
            headers = {
                "User-Agent": "Mozilla/5.0 (VectorCode/0.1; +https://github.com/vector-ai)"
            }
            resp = httpx.get(url, headers=headers, timeout=self.timeout, follow_redirects=True)
            resp.raise_for_status()
            content = resp.text

            if raw:
                return content

            # Strip HTML → readable text
            return self._strip_html(content, url=url)

        except Exception as e:
            logger.warning(f"[VECTOR][web] fetch failed for {url}: {e}")
            return f"[web_fetch error: {e}]"

    # ── web_search ────────────────────────────────────────────────────────────

    def web_search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Search the web using DuckDuckGo Lite (no API key needed).
        Returns list of {title, url, snippet} dicts.
        """
        try:
            # Try duckduckgo_search library first (fast, structured)
            return self._ddg_search(query, max_results)
        except ImportError:
            pass

        # Fallback: scrape DDG Lite HTML
        try:
            return self._ddg_lite_search(query, max_results)
        except Exception as e:
            logger.warning(f"[VECTOR][web] search failed for '{query}': {e}")
            return [{"title": "Search unavailable", "url": "", "snippet": str(e)}]

    def _ddg_search(self, query: str, max_results: int) -> list[dict]:
        from duckduckgo_search import DDGS  # type: ignore
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title":   r.get("title", ""),
                    "url":     r.get("href", ""),
                    "snippet": r.get("body", "")[:300],
                })
        return results

    def _ddg_lite_search(self, query: str, max_results: int) -> list[dict]:
        import httpx
        url = "https://lite.duckduckgo.com/lite/"
        params = {"q": query}
        headers = {"User-Agent": "Mozilla/5.0 (VectorCode/0.1)"}
        resp = httpx.post(url, data=params, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        html = resp.text

        results = []
        # Extract result links and snippets from DDG Lite HTML
        link_pattern = re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]{5,120})</a>', re.I)
        snippet_pattern = re.compile(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', re.I | re.S)

        links  = link_pattern.findall(html)
        snippets = [re.sub(r"<[^>]+>", "", s) for s in snippet_pattern.findall(html)]

        for i, (url_r, title) in enumerate(links[:max_results]):
            snippet = snippets[i].strip() if i < len(snippets) else ""
            results.append({"title": title.strip(), "url": url_r, "snippet": snippet[:300]})

        return results or [{"title": "No results", "url": "", "snippet": ""}]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _strip_html(html: str, url: str = "") -> str:
        """Minimal HTML → plain text conversion."""
        # Remove scripts, styles, nav
        for tag in ("script", "style", "nav", "footer", "header"):
            html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", " ", html, flags=re.I | re.S)
        # Remove remaining tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Collapse whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()
        if url:
            text = f"[Source: {url}]\n\n" + text
        return text[:8000]  # cap at 8K chars to avoid context explosion

    def format_search_results(self, results: list[dict]) -> str:
        """Format search results for LLM consumption."""
        if not results:
            return "No results found."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}")
            if r.get("url"):
                lines.append(f"   {r['url']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet']}")
            lines.append("")
        return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    wt = WebTools(timeout=10)

    # Test web_fetch
    result = wt.web_fetch("https://example.com")
    assert "example" in result.lower() or "error" in result.lower()

    # Test format
    fake_results = [
        {"title": "Python docs", "url": "https://docs.python.org", "snippet": "Official Python docs"},
    ]
    fmt = wt.format_search_results(fake_results)
    assert "Python docs" in fmt

    print("web_tools.py OK")



