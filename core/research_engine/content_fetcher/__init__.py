"""
Content Fetcher Module.

Provides unified content fetching from various sources:
- Academic papers (arXiv, PubMed, Semantic Scholar, bioRxiv)
- Web pages (HTML)
- Direct PDF links

Usage:
    from core.research_engine.content_fetcher import ContentFetcher

    fetcher = ContentFetcher()
    result = fetcher.fetch("https://arxiv.org/abs/2301.12345")
    logger.info(result["content"])

"""

from .fetcher import ContentFetcher
from .url_classifier import URLClassifier, URLType

__all__ = ["ContentFetcher", "URLClassifier", "URLType"]
