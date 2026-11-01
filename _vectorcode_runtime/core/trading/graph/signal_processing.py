"""Extract the 5-tier portfolio rating from the Portfolio Manager's decision.

The Portfolio Manager produces a typed ``PortfolioDecision`` via structured
output and renders it to markdown that always carries a ``**Rating**: X``
header (see :func:`core.trading.agents.schemas.render_pm_decision`).  The
deterministic heuristic in :mod:`core.trading.agents.utils.rating` is more
than sufficient to extract that rating; no extra LLM call is needed.

This module exists for backwards compatibility with callers that expect a
``SignalProcessor.process_signal(text)`` interface.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from core.trading.agents.utils.rating import (
    _RATING_LABEL_RE,
    _RATING_SET,
    parse_rating,
)

_DEFAULT_RATING = "Hold"
_NEGATORS = frozenset({
    "not", "no", "never", "avoid", "neither", "nor", "without", "cannot",
    "don't", "dont", "doesn't", "doesnt", "won't", "wont", "wouldn't",
    "shouldn't", "can't", "isn't", "aren't", "against",
})
_STRIP = "*:.,;()[]\"'_"


def _fallback_rating_is_negated(text: str) -> bool:
    """True when the first bare rating word is negated ("not a Buy", "do NOT sell").

    Only relevant when there is no explicit ``Rating: X`` label; parse_rating's
    word-scan fallback would otherwise read a negated word as that rating.
    """
    for line in text.splitlines():
        words = [w.strip(_STRIP) for w in line.lower().split()]
        for i, word in enumerate(words):
            if word in _RATING_SET:
                return any(w in _NEGATORS for w in words[max(0, i - 3):i])
    return False


class SignalProcessor:
    """Read the 5-tier rating out of a Portfolio Manager decision."""

    def __init__(self, quick_thinking_llm: Any = None):
        # The LLM argument is accepted for backwards compatibility but no
        # longer used: the PM's structured output guarantees the rating is
        # parseable from the rendered markdown without a second LLM call.
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        """Return one of Buy / Overweight / Hold / Underweight / Sell."""
        if not isinstance(full_signal, str) or not full_signal.strip():
            logger.warning("[VECTOR][signal_processing] empty/non-text decision, defaulting to {}", _DEFAULT_RATING)
            return _DEFAULT_RATING
        has_label = any(
            (m := _RATING_LABEL_RE.search(line)) and m.group(1).lower() in _RATING_SET
            for line in full_signal.splitlines()
        )
        if not has_label and _fallback_rating_is_negated(full_signal):
            logger.warning("[VECTOR][signal_processing] negated rating word without a Rating label, defaulting to {}", _DEFAULT_RATING)
            return _DEFAULT_RATING
        return parse_rating(full_signal, default=_DEFAULT_RATING)
