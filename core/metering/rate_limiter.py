"""
VECTOR GCRA Rate Limiter — Generic Cell Rate Algorithm token-bucket per caller.

Limits API/tool operations to prevent abuse and runaway agent loops.
Operation costs mirror real computational expense:
  health check   :  1 token
  memory query   :  5 tokens
  tool execution : 10 tokens
  LLM message    : 30 tokens
  agent spawn    : 50 tokens
  web scrape     : 20 tokens

Default: 500 tokens/minute per caller (agent_id or IP).

Ported from the agent OS API rate_limiter.rs (GCRA algorithm).
"""
from __future__ import annotations

__all__ = [
    "GCRARateLimiter",
    "get_rate_limiter",
    "operation_cost",
    "OperationType",
    "RateLimitResult",
]


import time
from dataclasses import dataclass
from threading import Lock
from typing import Literal

from loguru import logger

# ── Operation cost table (ported from rate_limiter.rs) ────────────────────────

OperationType = Literal[
    "health", "status", "memory_read", "memory_write",
    "tool_call", "llm_message", "agent_spawn", "agent_list",
    "skill_run", "skill_install", "web_fetch", "web_search",
    "audit_read", "budget_check", "channel_send", "default",
]

_COSTS: dict[str, int] = {
    "health":        1,
    "status":        1,
    "audit_read":    2,
    "budget_check":  2,
    "memory_read":   5,
    "agent_list":    5,
    "skill_run":    10,
    "tool_call":    10,
    "web_fetch":    20,
    "web_search":   20,
    "memory_write": 15,
    "channel_send": 15,
    "llm_message":  30,
    "skill_install":50,
    "agent_spawn":  50,
    "default":      10,
}


def operation_cost(op: str) -> int:
    """Return the token cost for an operation type."""
    return _COSTS.get(op, _COSTS["default"])


@dataclass
class RateLimitResult:
    allowed: bool
    tokens_remaining: int
    retry_after_secs: float = 0.0
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


# ── GCRA state per caller ─────────────────────────────────────────────────────

@dataclass
class _GCRAState:
    """
    GCRA (Generic Cell Rate Algorithm) state for one caller.

    tat = Theoretical Arrival Time — the time by which the bucket
    would be full again if no more requests come in.
    """
    tat: float = 0.0     # theoretical arrival time

    def check_and_update(self, now: float, cost: int, rate: float, burst: int) -> tuple[bool, float, int]:
        """
        Returns (allowed, retry_after_secs, tokens_remaining).
        rate  = tokens per second (burst / window_secs)
        burst = maximum tokens
        """
        emission_interval = cost / rate          # time to emit `cost` tokens
        increment = emission_interval
        new_tat = max(self.tat, now) + increment
        allow_at = new_tat - (burst / rate)      # earliest time this would be allowed

        if allow_at > now:
            # Rate limited
            return False, allow_at - now, 0

        self.tat = new_tat
        tokens_used = new_tat - now
        tokens_remaining = max(0, int((burst / rate - tokens_used) * rate))
        return True, 0.0, tokens_remaining


# ── GCRARateLimiter ───────────────────────────────────────────────────────────

class GCRARateLimiter:
    """
    Per-caller GCRA rate limiter.

    Usage:
        limiter = GCRARateLimiter(tokens_per_minute=500, burst=500)
        result = limiter.check("agent_001", "llm_message")
        if not result:
            await asyncio.sleep(result.retry_after_secs)
            raise RateLimitError(result.reason)
    """

    def __init__(
        self,
        tokens_per_minute: int = 500,
        burst: int = 500,
    ) -> None:
        self._rate = tokens_per_minute / 60.0    # tokens per second
        self._burst = burst
        self._states: dict[str, _GCRAState] = {}
        self._lock = Lock()

    def check(self, caller_id: str, operation: str = "default") -> RateLimitResult:
        """
        Check if a caller can perform an operation.

        Args:
            caller_id: Agent ID, IP address, or any unique identifier
            operation: Operation type from OperationType literal

        Returns:
            RateLimitResult — bool(result) is True if allowed
        """
        cost = operation_cost(operation)
        now = time.monotonic()

        with self._lock:
            if caller_id not in self._states:
                self._states[caller_id] = _GCRAState()
            state = self._states[caller_id]
            allowed, retry_after, remaining = state.check_and_update(now, cost, self._rate, self._burst)

        if not allowed:
            logger.warning(
                "[VECTOR][rate_limiter] caller={} op={} BLOCKED (retry in {:.1f}s)",
                caller_id, operation, retry_after,
            )
            return RateLimitResult(
                allowed=False,
                tokens_remaining=0,
                retry_after_secs=retry_after,
                reason=f"Rate limit exceeded for {operation} (retry in {retry_after:.1f}s)",
            )

        return RateLimitResult(allowed=True, tokens_remaining=remaining)

    def reset(self, caller_id: str) -> None:
        with self._lock:
            self._states.pop(caller_id, None)

    def reset_all(self) -> None:
        with self._lock:
            self._states.clear()

    def active_callers(self) -> int:
        with self._lock:
            return len(self._states)


# Singleton
_limiter: GCRARateLimiter | None = None


def get_rate_limiter() -> GCRARateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = GCRARateLimiter()
    return _limiter


if __name__ == "__main__":
    limiter = GCRARateLimiter(tokens_per_minute=100, burst=100)

    # health check costs 1 token — should pass many times
    for _ in range(5):
        result = limiter.check("agent_001", "health")
        assert result.allowed, f"health should be allowed: {result}"

    # Exhaust with expensive operations
    for _ in range(4):
        limiter.check("agent_001", "agent_spawn")  # 50 tokens each = 200 total

    # Next should be blocked
    result = limiter.check("agent_001", "agent_spawn")
    assert not result.allowed
    assert result.retry_after_secs > 0

    # Different caller unaffected
    result2 = limiter.check("agent_002", "llm_message")
    assert result2.allowed

    # Cost table
    assert operation_cost("health") == 1
    assert operation_cost("agent_spawn") == 50
    assert operation_cost("llm_message") == 30

    print("OK rate_limiter.py — GCRA per-caller limiting, cost table verified")
