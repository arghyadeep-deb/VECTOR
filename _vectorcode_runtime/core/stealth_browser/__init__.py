"""
VECTOR Stealth Browser
Anti-detection Firefox browser for web scraping and research on bot-protected sites.

Components:
  server/          — Node.js server (Camoufox + Express REST API)
  server_manager   — Python subprocess manager (start/stop/crash-detect)
  client           — Python HTTP client (all REST endpoints)
  macros           — 14 built-in search macros (Google, YouTube, Reddit, ...)
  transcripts      — YouTube transcript extraction (yt-dlp + browser fallback)

Quick start:
    from core.stealth_browser import StealthBrowserClient, StealthBrowserServer

    # Start server (once per VECTOR session)
    await StealthBrowserServer().ensure_running()

    # Scrape a bot-protected page
    async with StealthBrowserClient() as client:
        result = await client.scrape_page("https://linkedin.com/in/someone")
        logger.info(result["snapshot"])   # token-efficient accessibility tree


    # Search without getting blocked
        result = await client.search("AI startups 2026", engine="google")
"""
__version__ = "1.0.0"

from core.stealth_browser.client import StealthBrowserClient
from core.stealth_browser.server_manager import StealthBrowserServer, get_server
from core.stealth_browser.macros import macro_url, SEARCH_MACROS, list_engines
from core.stealth_browser.transcripts import get_youtube_transcript

__all__ = [
    "StealthBrowserClient",
    "StealthBrowserServer",
    "get_server",
    "macro_url",
    "SEARCH_MACROS",
    "list_engines",
    "get_youtube_transcript",
]
