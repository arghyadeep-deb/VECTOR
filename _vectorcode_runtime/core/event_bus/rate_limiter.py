from __future__ import annotations

import time
from typing import Any

__all__ = [
    "RateLimiter",
]



class RateLimiter:
    """Token bucket rate limiter per subscriber."""

    def __init__(self, name: str, max_rate: float = 100.0, time_window: float = 1.0):
        self.name = name
        self.max_rate = max_rate
        self.time_window = time_window
        self._tokens = max_rate
        self._last_refill = time.time()
        self._total_allowed = 0
        self._total_denied = 0

    def allow(self) -> bool:
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(self.max_rate, self._tokens + elapsed * (self.max_rate / self.time_window))
        self._last_refill = now
        if self._tokens >= 1:
            self._tokens -= 1
            self._total_allowed += 1
            return True
        self._total_denied += 1
        return False

    def get_stats(self) -> dict[str, Any]:
        return {
            "tokens": round(self._tokens, 1),
            "max_rate": self.max_rate,
            "total_allowed": self._total_allowed,
            "total_denied": self._total_denied,
        }
