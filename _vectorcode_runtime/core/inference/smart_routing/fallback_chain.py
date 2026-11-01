"""
VECTOR Smart Routing — Structured Fallback Chain
Python port of ClawRouter/src/retry.ts

Tries primary model, then up to 5 fallbacks on failure/timeout.
Applies per-model timeouts: 60s for normal models, 180s for reasoning models.

Usage:
    result = await execute_with_fallback(
        primary="google/gemini-2.5-flash",
        fallbacks=["anthropic/claude-haiku-4.5", "openai/gpt-4o-mini"],
        call_fn=lambda model: call_llm(model, messages),
    )
"""
from __future__ import annotations

__all__ = [
    "execute_with_fallback",
    "FallbackChainExecutor",
]


import asyncio
import sys
from typing import Callable, Optional

from loguru import logger

_TIMEOUT_REASONING = 180.0   # 3 min for reasoning models
_TIMEOUT_DEFAULT   =  60.0   # 1 min for normal models
_MAX_ATTEMPTS      =   5

_REASONING_MODEL_PATTERNS = ["o1", "o3", "r1", "reasoning", "think", "opus"]


def _is_reasoning_model(model_id: str) -> bool:
    lower = model_id.lower()
    return any(p in lower for p in _REASONING_MODEL_PATTERNS)


def _timeout_for(model_id: str) -> float:
    return _TIMEOUT_REASONING if _is_reasoning_model(model_id) else _TIMEOUT_DEFAULT


_RETRYABLE_ERRORS = {
    "rate_limit", "overloaded", "timeout", "503", "502", "529",
    "context_length_exceeded", "internal_server_error",
}

_NON_RETRYABLE_ERRORS = {
    "invalid_api_key", "authentication", "unauthorized", "401", "403",
    "invalid_request", "400", "content_policy",
}


def _should_retry(error: Exception) -> bool:
    msg = str(error).lower()
    if any(e in msg for e in _NON_RETRYABLE_ERRORS):
        return False
    if any(e in msg for e in _RETRYABLE_ERRORS):
        return True
    return False  # unknown errors: don't retry (safe default)


async def execute_with_fallback(
    primary_model: str,
    fallback_models: list[str],
    call_fn: Callable,             # async (model: str) → dict
    max_attempts: int = _MAX_ATTEMPTS,
) -> dict:
    """
    Try primary model, then fallback chain on failure or timeout.

    Args:
        primary_model: first model to try
        fallback_models: ordered list of fallbacks
        call_fn: async callable(model_id: str) → response dict
        max_attempts: max models to try (including primary)

    Returns:
        First successful response dict.
    Raises:
        RuntimeError if all models in chain fail.
    """
    chain = [primary_model] + fallback_models
    chain = chain[:max_attempts]
    last_error: Exception | None = None

    for i, model_id in enumerate(chain):
        timeout = _timeout_for(model_id)
        attempt_label = f"primary" if i == 0 else f"fallback[{i}]"
        logger.debug("[VECTOR][fallback] trying {} ({}) timeout={}s", model_id, attempt_label, timeout)

        try:
            result = await asyncio.wait_for(call_fn(model_id), timeout=timeout)
            if i > 0:
                logger.info("[VECTOR][fallback] succeeded with fallback model: {}", model_id)
            return result

        except asyncio.TimeoutError as e:
            last_error = e
            logger.warning("[VECTOR][fallback] {} timed out after {}s", model_id, timeout)

        except Exception as e:
            last_error = e
            if not _should_retry(e):
                logger.error("[VECTOR][fallback] non-retryable error on {}: {}", model_id, e)
                raise
            logger.warning("[VECTOR][fallback] {} failed ({}), trying next", model_id, str(e)[:80])

    raise RuntimeError(
        f"All {len(chain)} models in fallback chain failed. "
        f"Last error: {last_error}"
    )


class FallbackChainExecutor:
    """
    Stateful fallback executor with usage tracking.
    Useful when you want to track which models succeeded/failed over time.
    """

    def __init__(self) -> None:
        self._success_counts: dict[str, int] = {}
        self._failure_counts: dict[str, int] = {}

    async def run(
        self,
        primary_model: str,
        fallback_models: list[str],
        call_fn: Callable,
    ) -> tuple[dict, str]:
        """
        Execute with fallback chain.
        Returns (response, model_id_used).
        """
        chain = [primary_model] + fallback_models

        for model_id in chain:
            timeout = _timeout_for(model_id)
            try:
                result = await asyncio.wait_for(call_fn(model_id), timeout=timeout)
                self._success_counts[model_id] = self._success_counts.get(model_id, 0) + 1
                return result, model_id
            except Exception as e:
                self._failure_counts[model_id] = self._failure_counts.get(model_id, 0) + 1
                if not _should_retry(e):
                    raise
                logger.warning("[VECTOR][fallback] {} → {}", model_id, str(e)[:60])

        raise RuntimeError(f"All models in chain failed: {chain}")

    def stats(self) -> dict:
        return {
            "successes": self._success_counts,
            "failures":  self._failure_counts,
        }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        call_count = {"n": 0}

        async def mock_call(model: str) -> dict:
            call_count["n"] += 1
            if model == "bad-model":
                raise RuntimeError("rate_limit exceeded")
            return {"model": model, "response": "ok"}

        # Test: primary succeeds
        result = await execute_with_fallback(
            primary_model="good-model",
            fallback_models=["backup"],
            call_fn=mock_call,
        )
        assert result["model"] == "good-model"

        # Test: primary fails, fallback succeeds
        result = await execute_with_fallback(
            primary_model="bad-model",
            fallback_models=["good-model"],
            call_fn=mock_call,
        )
        assert result["model"] == "good-model"

        # Test: timeout detection
        assert _is_reasoning_model("openai/o3") is True
        assert _is_reasoning_model("google/gemini-2.5-flash") is False
        assert _timeout_for("openai/o3") == 180.0
        assert _timeout_for("google/gemini-2.5-flash") == 60.0

        print(f"OK fallback_chain.py — fallback chain, timeout detection, retry logic")
        print(f"  calls made: {call_count['n']}")

    asyncio.run(_smoke())
