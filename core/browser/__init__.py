"""
core.browser — Absorbed from auto-browser-main (2026-05-27).

Exposes:
  DOMPruner          — relevance-scored interactive element pruning (18k → ~500 tokens)
  PiiScrubber        — 17-pattern PII redaction + Pillow screenshot pixel-redaction
  BrowserAuthStore   — named Playwright storage-state profiles (login-once, reuse-later)
"""
from .dom_pruner import DOMPruner, get_dom_pruner
from .pii_scrub import PiiScrubber, ScrubResult, scrub_text, get_pii_scrubber
from .auth_profiles import BrowserAuthStore, get_auth_store

__all__ = [
    "DOMPruner",
    "get_dom_pruner",
    "PiiScrubber",
    "ScrubResult",
    "scrub_text",
    "get_pii_scrubber",
    "BrowserAuthStore",
    "get_auth_store",
]
