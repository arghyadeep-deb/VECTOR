"""
VECTOR SEO Engine
Data-driven SEO and marketing intelligence for autonomous site management.

Modules:
  gsc_client          — Google Search Console: clicks, impressions, CTR, position
  pagespeed_client    — Core Web Vitals and PageSpeed Insights
  broken_link_checker — Crawl and detect 4xx/5xx links
  cms_connector       — WordPress, Ghost, Contentful, Strapi content API
  portfolio           — Multi-site portfolio management and priority scoring
"""
__version__ = "1.0.0"

from core.seo.gsc_client import GSCClient
from core.seo.pagespeed_client import PageSpeedClient
from core.seo.broken_link_checker import BrokenLinkChecker
from core.seo.cms_connector import CMSConnector
from core.seo.portfolio import SEOPortfolio

__all__ = [
    "GSCClient",
    "PageSpeedClient",
    "BrokenLinkChecker",
    "CMSConnector",
    "SEOPortfolio",
]
