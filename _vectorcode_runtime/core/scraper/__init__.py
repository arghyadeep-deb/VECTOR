"""
VECTOR Web Scraper — adaptive, stealth-capable scraping engine.

Three fetcher tiers:
  Fetcher        : HTTP with TLS fingerprint impersonation (fastest)
  DynamicFetcher : Full Playwright browser automation (JS-heavy sites)
  StealthyFetcher: Anti-bot bypass (Cloudflare Turnstile, fingerprint spoofing)

Spider framework:
  Spider         : Base class for crawlers (Scrapy-like, with checkpoints)
  CrawlerEngine  : Concurrent crawling, domain throttling, robots.txt

MCP server:
  VectorScraperMCPServer: Exposes all fetchers as MCP tools for VECTOR agents

Usage:
    from core.scraper import Fetcher, StealthyFetcher, DynamicFetcher
    from core.scraper.spiders.spider import Spider
    from core.scraper.spiders.engine import CrawlerEngine
"""
__version__ = "0.4.8"

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.scraper.parser import Selector, Selectors
    from core.scraper.core.custom_types import AttributesHandler, TextHandler
    from core.scraper.fetchers import Fetcher, AsyncFetcher, StealthyFetcher, DynamicFetcher


# Lazy import mapping
_LAZY_IMPORTS = {
    "Fetcher": ("core.scraper.fetchers", "Fetcher"),
    "Selector": ("core.scraper.parser", "Selector"),
    "Selectors": ("core.scraper.parser", "Selectors"),
    "AttributesHandler": ("core.scraper.core.custom_types", "AttributesHandler"),
    "TextHandler": ("core.scraper.core.custom_types", "TextHandler"),
    "AsyncFetcher": ("core.scraper.fetchers", "AsyncFetcher"),
    "StealthyFetcher": ("core.scraper.fetchers", "StealthyFetcher"),
    "DynamicFetcher": ("core.scraper.fetchers", "DynamicFetcher"),
}
__all__ = ["Selector", "Fetcher", "AsyncFetcher", "StealthyFetcher", "DynamicFetcher"]


def __getattr__(name: str) -> Any:
    if name in _LAZY_IMPORTS:
        module_path, class_name = _LAZY_IMPORTS[name]
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Support for dir() and autocomplete."""
    return sorted(__all__ + ["fetchers", "parser", "cli", "core", "__author__", "__version__", "__copyright__"])
