from typing import TYPE_CHECKING, Any
from core.scraper.engines.toolbelt import ProxyRotator

if TYPE_CHECKING:
    from core.scraper.fetchers.requests import Fetcher, AsyncFetcher, FetcherSession
    from core.scraper.fetchers.chrome import DynamicFetcher, DynamicSession, AsyncDynamicSession
    from core.scraper.fetchers.stealth_chrome import StealthyFetcher, StealthySession, AsyncStealthySession


# Lazy import mapping
_LAZY_IMPORTS = {
    "Fetcher": ("core.scraper.fetchers.requests", "Fetcher"),
    "AsyncFetcher": ("core.scraper.fetchers.requests", "AsyncFetcher"),
    "FetcherSession": ("core.scraper.fetchers.requests", "FetcherSession"),
    "DynamicFetcher": ("core.scraper.fetchers.chrome", "DynamicFetcher"),
    "DynamicSession": ("core.scraper.fetchers.chrome", "DynamicSession"),
    "AsyncDynamicSession": ("core.scraper.fetchers.chrome", "AsyncDynamicSession"),
    "StealthyFetcher": ("core.scraper.fetchers.stealth_chrome", "StealthyFetcher"),
    "StealthySession": ("core.scraper.fetchers.stealth_chrome", "StealthySession"),
    "AsyncStealthySession": ("core.scraper.fetchers.stealth_chrome", "AsyncStealthySession"),
}

__all__ = [
    "Fetcher",
    "AsyncFetcher",
    "ProxyRotator",
    "FetcherSession",
    "DynamicFetcher",
    "DynamicSession",
    "AsyncDynamicSession",
    "StealthyFetcher",
    "StealthySession",
    "AsyncStealthySession",
]


def __getattr__(name: str) -> Any:
    if name in _LAZY_IMPORTS:
        module_path, class_name = _LAZY_IMPORTS[name]
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Support for dir() and autocomplete."""
    return sorted(list(_LAZY_IMPORTS.keys()))
