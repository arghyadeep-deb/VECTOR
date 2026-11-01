"""
VECTOR Stealth Browser — Search Macros
Python port of core/stealth_browser/server/lib/macros.js

14 built-in search macros. Pass as the URL to navigate():
    client.navigate(tab_id, macro_url("google", "AI news 2026"))
    # → navigates to Google and searches for "AI news 2026"
"""
from __future__ import annotations

__all__ = [
    "list_engines",
    "macro_url",
]


import urllib.parse

# ── Macro definitions ─────────────────────────────────────────────────────────

SEARCH_MACROS: dict[str, str] = {
    "google":    "https://www.google.com/search?q={query}",
    "youtube":   "https://www.youtube.com/results?search_query={query}",
    "reddit":    "https://www.reddit.com/search/?q={query}",
    "amazon":    "https://www.amazon.com/s?k={query}",
    "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search={query}",
    "twitter":   "https://twitter.com/search?q={query}",
    "yelp":      "https://www.yelp.com/search?find_desc={query}",
    "spotify":   "https://open.spotify.com/search/{query}",
    "linkedin":  "https://www.linkedin.com/search/results/all/?keywords={query}",
    "instagram": "https://www.instagram.com/explore/tags/{query}/",
    "tiktok":    "https://www.tiktok.com/search?q={query}",
    "twitch":    "https://www.twitch.tv/search?term={query}",
    "netflix":   "https://www.netflix.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
}

# Server-side macro prefix (used by camofox server's macros.js)
SERVER_MACROS: dict[str, str] = {
    "google":    "@google_search",
    "youtube":   "@youtube_search",
    "reddit":    "@reddit_search",
    "amazon":    "@amazon_search",
    "wikipedia": "@wikipedia_search",
    "twitter":   "@twitter_search",
    "yelp":      "@yelp_search",
    "spotify":   "@spotify_search",
    "linkedin":  "@linkedin_search",
    "instagram": "@instagram_search",
    "tiktok":    "@tiktok_search",
    "twitch":    "@twitch_search",
    "netflix":   "@netflix_search",
    "duckduckgo": "@duckduckgo_search",
}


def macro_url(engine: str, query: str, use_server_macro: bool = True) -> str:
    """
    Build a search URL or server macro string for the given engine and query.

    Args:
        engine: search engine name (google, youtube, reddit, etc.)
        query: search terms
        use_server_macro: if True, return server-side macro format (@google_search:query)
                          if False, return direct URL

    Returns:
        Server macro string or direct URL
    """
    engine = engine.lower().strip()
    if use_server_macro and engine in SERVER_MACROS:
        return f"{SERVER_MACROS[engine]}:{query}"
    if engine in SEARCH_MACROS:
        return SEARCH_MACROS[engine].replace("{query}", urllib.parse.quote_plus(query))
    # Fallback: Google
    return SEARCH_MACROS["google"].replace("{query}", urllib.parse.quote_plus(query))


def list_engines() -> list[str]:
    return list(SEARCH_MACROS.keys())


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    tests = [
        ("google", "AI news 2026"),
        ("youtube", "VECTOR AI system"),
        ("reddit", "machine learning"),
        ("wikipedia", "large language models"),
        ("linkedin", "software engineer"),
    ]
    for engine, query in tests:
        server = macro_url(engine, query, use_server_macro=True)
        direct = macro_url(engine, query, use_server_macro=False)
        assert server.startswith("@"), f"{engine}: expected @ prefix"
        assert query.replace(" ", "+") in direct or query in direct, f"{engine}: query not in URL"
        print(f"  OK {engine}: {server}")

    assert len(list_engines()) >= 13
    print(f"OK macros.py — {len(list_engines())} search engines")
