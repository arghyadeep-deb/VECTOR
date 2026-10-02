"""Regression: GCRARateLimiter.check()'s allowed-path tokens_remaining used
a naive `burst - cost` approximation, ignoring any PRIOR consumption by the
same caller -- while _GCRAState.check_and_update() computed the real
remaining-token figure internally and simply discarded it. A caller with
most of its burst already spent would be told it had nearly the full burst
remaining.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.metering.rate_limiter import GCRARateLimiter


def test_tokens_remaining_reflects_prior_consumption():
    limiter = GCRARateLimiter(tokens_per_minute=600, burst=600)  # 10 tokens/sec
    # Spend 500 of 600 tokens via one big "agent_spawn" (cost 50) x 10.
    for _ in range(10):
        result = limiter.check("agent_001", "agent_spawn")
        assert result.allowed

    # Naive (buggy) calc would report burst - cost = 600 - 1 = 599 for this
    # cheap "health" (cost 1) check. The real remaining is nowhere near that.
    result = limiter.check("agent_001", "health")
    assert result.allowed
    assert result.tokens_remaining < 150, (
        f"tokens_remaining={result.tokens_remaining} ignores prior consumption"
    )


def test_fresh_caller_tokens_remaining_near_full_burst():
    limiter = GCRARateLimiter(tokens_per_minute=600, burst=600)
    result = limiter.check("fresh_agent", "health")
    assert result.allowed
    assert result.tokens_remaining > 590


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
