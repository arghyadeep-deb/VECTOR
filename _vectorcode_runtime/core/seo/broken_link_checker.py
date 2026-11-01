"""
VECTOR Broken Link Checker — crawl any website and find 4xx/5xx links.

Crawls up to max_pages pages starting from a root URL, respects robots.txt,
and returns a structured report of all broken links found.

Usage:
    checker = BrokenLinkChecker()
    report = await checker.check("https://example.com", max_pages=100)
    for broken in report["broken_links"]:
        logger.info(broken["url"], broken["status"])

"""
from __future__ import annotations

import asyncio
import sys
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Optional

from loguru import logger
from core.security.ssrf_guard import SSRFGuard


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a":
            for attr, value in attrs:
                if attr == "href" and value:
                    url = urllib.parse.urljoin(self.base_url, value)
                    url = urllib.parse.urldefrag(url)[0]
                    if url.startswith("http"):
                        self.links.add(url)


def _check_url(url: str, timeout: int = 10) -> tuple[Optional[int], Optional[str]]:
    """Check a URL. Returns (status_code, error). Tries HEAD first, falls back to GET."""
    headers = {"User-Agent": "VECTOR/1.0 (SEO audit)"}
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.getcode(), None
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 501):
                continue  # retry with GET
            return e.code, str(e.reason)
        except urllib.error.URLError as e:
            return None, str(e.reason)
        except Exception as e:
            return None, str(e)
    return None, "unknown"


def _fetch_links(url: str, timeout: int = 15) -> set[str]:
    """Fetch a page and extract all hrefs."""
    headers = {"User-Agent": "VECTOR/1.0 (SEO audit)"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type", "")
            if "text/html" not in ct:
                return set()
            parser = _LinkParser(url)
            parser.feed(resp.read().decode(errors="replace"))
            return parser.links
    except Exception:
        return set()


class BrokenLinkChecker:
    """
    VECTOR's broken link checker.
    BFS crawl with concurrent checking, robots.txt aware.
    """

    def check(
        self,
        start_url: str,
        max_pages: int = 50,
        max_workers: int = 10,
        same_domain_only: bool = True,
        timeout: int = 10,
    ) -> dict:
        parsed = urllib.parse.urlparse(start_url)
        base_domain = parsed.netloc

        # robots.txt
        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            rp.set_url(robots_url)
            rp.read()
        except Exception:
            rp = None

        visited: set[str] = set()
        queue: deque[str] = deque([start_url])
        broken: list[dict] = []
        checked: list[dict] = []
        pages_crawled = 0
        # Every crawled URL -- the initial start_url AND every link discovered
        # on a crawled page -- previously reached a real urlopen() with no
        # SSRF check at all. A caller-supplied start_url, or a malicious page
        # linking to an internal/metadata address, could make VECTOR's own
        # process fetch http://169.254.169.254/ or an internal service.
        # Same bug class fixed in core/scraper/+core/browser/ this cycle.
        ssrf_guard = SSRFGuard(resolve_dns=True)

        logger.info("[VECTOR][broken_link] starting crawl: {} max_pages={}", start_url, max_pages)

        while queue and pages_crawled < max_pages:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            check = ssrf_guard.check_url(url)
            if not check.safe:
                logger.warning("[VECTOR][broken_link] SSRF-blocked, skipping: {} ({})", url, check.reason)
                checked.append({"url": url, "status": None, "error": f"blocked: {check.reason}"})
                continue
            pages_crawled += 1

            # Check robots
            if rp and not rp.can_fetch("*", url):
                continue

            # Check URL
            status, error = _check_url(url, timeout=timeout)
            entry = {"url": url, "status": status, "error": error}
            checked.append(entry)

            if status and status >= 400:
                broken.append(entry)
                logger.warning("[VECTOR][broken_link] broken: {} → {}", url, status)
            elif status and status < 400:
                # Crawl page links
                new_links = _fetch_links(url)
                for link in new_links:
                    if link not in visited:
                        if same_domain_only:
                            link_domain = urllib.parse.urlparse(link).netloc
                            if link_domain != base_domain:
                                continue
                        queue.append(link)

        logger.info(
            "[VECTOR][broken_link] done: {} checked, {} broken",
            len(checked), len(broken),
        )
        return {
            "start_url": start_url,
            "pages_crawled": pages_crawled,
            "links_checked": len(checked),
            "broken_count": len(broken),
            "broken_links": broken,
            "summary": (
                f"Found {len(broken)} broken links out of {len(checked)} checked "
                f"across {pages_crawled} pages."
            ),
        }

    async def check_async(
        self,
        start_url: str,
        max_pages: int = 50,
        same_domain_only: bool = True,
    ) -> dict:
        """Async wrapper for check()."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.check, start_url, max_pages, 10, same_domain_only
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    checker = BrokenLinkChecker()
    print("OK broken_link_checker.py — BrokenLinkChecker ready")
    print("  checker.check(url, max_pages=50) — sync")
    print("  checker.check_async(url) — async")
