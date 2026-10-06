"""Jittered backoff — absorbed from reference agent/retry_utils.py.

Replaces fixed exponential backoff with jittered delays to prevent
thundering-herd retry spikes when multiple sessions hit the same
rate-limited provider concurrently.
"""
from loguru import logger
import sys
import random
import time


def jittered_backoff(
    attempt: int,
    *,
    base_delay: float = 5.0,
    max_delay: float = 120.0,
    jitter_ratio: float = 0.5,
) -> float:
    """Compute jittered exponential backoff. Returns delay in seconds.

    Args:
        attempt: 1-based retry attempt number.
        base_delay: Base delay for attempt 1.
        max_delay: Cap on computed delay.
        jitter_ratio: Fraction of delay to use as random jitter range.

    Decorrelates concurrent retries — different sessions won't all
    hammer the same provider endpoint at the same instant.
    """
    exponent = max(0, attempt - 1)
    if exponent >= 63 or base_delay <= 0:
        delay = max_delay
    else:
        delay = min(base_delay * (2 ** exponent), max_delay)

    jitter = random.uniform(0, jitter_ratio * delay)
    return delay + jitter


def retry_with_backoff(fn, max_attempts: int = 4, base_delay: float = 5.0,
                       retryable_errors: tuple = (Exception,)):
    """Call fn() up to max_attempts times, with jittered backoff between retries.

    Returns: result of fn() on success.
    Raises: last exception if all attempts exhausted.
    """
    from loguru import logger
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except retryable_errors as e:
            last_exc = e
            if attempt == max_attempts:
                break
            delay = jittered_backoff(attempt, base_delay=base_delay)
            logger.warning(f"[VECTOR][retry] attempt {attempt}/{max_attempts} failed: {e} — retry in {delay:.1f}s")
            time.sleep(delay)
    raise last_exc


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    # Backoff grows
    d1 = jittered_backoff(1, base_delay=5.0)
    d2 = jittered_backoff(2, base_delay=5.0)
    d3 = jittered_backoff(3, base_delay=5.0)
    assert d1 < d2 < d3, f"{d1:.1f} < {d2:.1f} < {d3:.1f}"
    # Cap respected
    d_big = jittered_backoff(100, base_delay=5.0, max_delay=120.0)
    assert d_big <= 120.0 * 1.5  # jitter can add up to 50%
    # Decorrelation: two calls with same attempt produce different values
    vals = {jittered_backoff(1) for _ in range(5)}
    assert len(vals) > 1, "jitter should produce different values"
    # retry_with_backoff: success on second try
    calls = []
    def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("not ready")
        return "ok"
    result = retry_with_backoff(flaky, max_attempts=3, base_delay=0.01)
    assert result == "ok" and len(calls) == 2
    print("retry.py OK")

