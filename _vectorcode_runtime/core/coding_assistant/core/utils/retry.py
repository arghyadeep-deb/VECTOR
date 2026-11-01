from __future__ import annotations

__all__ = [
    "async_generator_retry",
    "async_retry",
]


import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
import functools

import httpx


def _is_retryable_http_error(e: Exception) -> bool:
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code in {408, 409, 425, 429, 500, 502, 503, 504, 529}
    return False


async def _backoff_or_raise(
    e: Exception,
    attempt: int,
    tries: int,
    delay_seconds: float,
    backoff_factor: float,
    is_retryable: Callable[[Exception], bool],
) -> None:
    """Shared retry decision: sleep before the next attempt, or re-raise when
    out of attempts / the error is not retryable. (Was duplicated verbatim in
    both decorators below — ponytail shrink, 2026-07-15.)"""
    if attempt < tries - 1 and is_retryable(e):
        await asyncio.sleep((delay_seconds * (backoff_factor**attempt)) + (0.05 * attempt))
        return
    raise e


def async_retry[T, **P](
    tries: int = 3,
    delay_seconds: float = 0.5,
    backoff_factor: float = 2.0,
    is_retryable: Callable[[Exception], bool] = _is_retryable_http_error,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Args:
        tries: Number of retry attempts
        delay_seconds: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay on each retry
        is_retryable: Function to determine if an exception should trigger a retry
                     (defaults to checking for retryable HTTP errors from both urllib and httpx)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exc = None
            for attempt in range(tries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    await _backoff_or_raise(
                        e, attempt, tries, delay_seconds, backoff_factor, is_retryable
                    )
            raise RuntimeError(
                f"Retries exhausted. Last error: {last_exc}"
            ) from last_exc

        return wrapper

    return decorator


def async_generator_retry[T, **P](
    tries: int = 3,
    delay_seconds: float = 0.5,
    backoff_factor: float = 2.0,
    is_retryable: Callable[[Exception], bool] = _is_retryable_http_error,
) -> Callable[[Callable[P, AsyncGenerator[T]]], Callable[P, AsyncGenerator[T]]]:
    """Retry decorator for async generators.

    Args:
        tries: Number of retry attempts
        delay_seconds: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay on each retry
        is_retryable: Function to determine if an exception should trigger a retry
                     (defaults to checking for retryable HTTP errors from both urllib and httpx)

    Returns:
        Decorated async generator function with retry logic
    """

    def decorator(
        func: Callable[P, AsyncGenerator[T]],
    ) -> Callable[P, AsyncGenerator[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[T]:
            last_exc = None
            for attempt in range(tries):
                try:
                    async for item in func(*args, **kwargs):
                        yield item
                    return
                except Exception as e:
                    last_exc = e
                    await _backoff_or_raise(
                        e, attempt, tries, delay_seconds, backoff_factor, is_retryable
                    )
            raise RuntimeError(
                f"Retries exhausted. Last error: {last_exc}"
            ) from last_exc

        return wrapper

    return decorator
