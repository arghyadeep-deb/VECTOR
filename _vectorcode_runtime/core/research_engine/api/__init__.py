# src/vector_research_engine/api/__init__.py
"""
API module for programmatic access to VECTOR Research Engine functionality.
"""

from .research_functions import (
    analyze_documents,
    detailed_research,
    generate_report,
    quick_summary,
)
from .settings_utils import (
    create_settings_snapshot,
    get_default_settings_snapshot,
    extract_setting_value,
)
from .client import (
    LDRClient,
    quick_query,
)

try:
    from ..news import (
        get_news_feed,
        research_news_item,
        save_news_preferences,
        get_news_categories,
    )
except ImportError as _news_err:  # the news scheduler/web pieces were not vendored
    # Importing this package must not fail just because the optional news feature is
    # missing: districts/research/research_api.py needs quick_summary/generate_report/etc.
    _NEWS_UNAVAILABLE = str(_news_err)

    def _news_unavailable(*_a, **_k):
        raise RuntimeError(f"news features are not available in this build ({_NEWS_UNAVAILABLE})")

    get_news_feed = research_news_item = save_news_preferences = get_news_categories = _news_unavailable

__all__ = [
    # Research functions
    "analyze_documents",
    "detailed_research",
    "generate_report",
    "quick_summary",
    # Settings utilities
    "create_settings_snapshot",
    "get_default_settings_snapshot",
    "extract_setting_value",
    # HTTP Client
    "LDRClient",
    "quick_query",
    # News functions
    "get_news_feed",
    "research_news_item",
    "save_news_preferences",
    "get_news_categories",
]
