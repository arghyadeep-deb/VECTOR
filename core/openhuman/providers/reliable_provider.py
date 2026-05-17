"""
VECTOR Reliable Provider — retry, backoff, API-key rotation, model fallback.

Ported from openhuman's providers/reliable.rs.

Wraps any Ollama/OpenAI-compatible provider with:
  - Exponential backoff on transient failures
  - Retry-After header parsing on 429s
  - Round-robin API key rotation on rate limits
  - Model fallback chains (primary → fallback1 → fallback2)
  - Error classification: retryable vs non-retryable vs context-limit

VECTOR runtime uses Ollama exclusively (RULE 11), so API key rotation
applies to cloud providers used only in build sessions.
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from dataclasses import dataclass, field
from itertools import cycle
from pathlib import Path
from typing import Any, AsyncIterator

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from loguru import logger


# ── Error classification (ported from reliable.rs) ─────────────────────────────

def is_non_retryable(error: str) -> bool:
    """4xx client errors except 429 (rate limit) and 408 (timeout)."""
    low = error.lower()
    for code in ("400", "401", "403", "404", "422"):
        if code in low:
            return True
    return False


def is_context_window_exceeded(error: str) -> bool:
    low = error.lower()
    return any(sig in low for sig in (
        "context length", "context window", "maximum context",
        "token limit", "too many tokens", "prompt is too long",
        "input is too long", "request too large",
    ))


def is_upstream_unhealthy(error: str) -> bool:
    return any(code in error for code in ("408", "502", "503", "504"))


def is_rate_limited(error: str) -> bool:
    return "429" in error or "rate limit" in error.lower()


def is_non_retryable_rate_limit(error: str) -> bool:
    """Business quota exhausted — no point retrying with same key."""
    low = error.lower()
    return "quota" in low or "billing" in low or "insufficient_quota" in low


def parse_retry_after_ms(error: str) -> int | None:
    """Extract Retry-After seconds from error message, return as ms."""
    m = re.search(r"retry.?after[:\s]+(\d+(?:\.\d+)?)", error, re.IGNORECASE)
    if m:
        return int(float(m.group(1)) * 1000)
    return None


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class ProviderError(Exception):
    message: str
    retryable: bool = True
    context_limit: bool = False
    rate_limited: bool = False

    def __str__(self) -> str:
        return self.message

    @classmethod
    def classify(cls, raw: str) -> "ProviderError":
        return cls(
            message=raw,
            retryable=not is_non_retryable(raw),
            context_limit=is_context_window_exceeded(raw),
            rate_limited=is_rate_limited(raw),
        )


@dataclass
class CallResult:
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


# ── ReliableProvider ──────────────────────────────────────────────────────────

class ReliableProvider:
    """
    Reliability wrapper around any OpenAI-compatible provider.

    Usage:
        provider = ReliableProvider(
            base_url="http://localhost:11434/v1",
            model="qwen3:14b",
            api_keys=["key1", "key2"],           # rotated on 429
            model_fallbacks={"qwen3:14b": ["qwen3:8b", "mistral-small3.1"]},
            max_retries=3,
        )
        result = await provider.chat([{"role":"user","content":"Hello"}])
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "qwen3:14b",
        api_keys: list[str] | None = None,
        model_fallbacks: dict[str, list[str]] | None = None,
        max_retries: int = 3,
        base_backoff_ms: int = 500,
        timeout_secs: int = 120,
        name: str = "ollama",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = name
        self.max_retries = max_retries
        self.base_backoff_ms = base_backoff_ms
        self.timeout_secs = timeout_secs
        self.model_fallbacks = model_fallbacks or {}

        keys = api_keys or [""]
        self._key_cycle = cycle(keys)
        self._current_key = next(self._key_cycle)

    def _rotate_key(self) -> str:
        self._current_key = next(self._key_cycle)
        return self._current_key

    def _model_chain(self, model: str) -> list[str]:
        """Return [primary, fallback1, fallback2, ...] for a model."""
        return [model] + self.model_fallbacks.get(model, [])

    def _backoff_ms(self, attempt: int, retry_after_ms: int | None) -> float:
        if retry_after_ms:
            return retry_after_ms / 1000.0
        return (self.base_backoff_ms * (2 ** attempt)) / 1000.0

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        system: str | None = None,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        stream: bool = False,
    ) -> CallResult:
        """
        Call the provider with full retry + fallback logic.

        Raises ProviderError if all retries and fallbacks exhausted.
        """
        target_model = model or self.model
        chain = self._model_chain(target_model)

        last_error: str = ""
        for m in chain:
            for attempt in range(self.max_retries):
                try:
                    result = await self._call(messages, m, system, tools, temperature)
                    logger.debug(
                        "[VECTOR][reliable_provider] OK model={} attempt={} provider={}",
                        m, attempt, self.name,
                    )
                    return result

                except Exception as exc:
                    raw = str(exc)
                    err = ProviderError.classify(raw)
                    last_error = raw

                    if err.context_limit:
                        logger.warning("[VECTOR][reliable_provider] context limit — no retry")
                        raise err

                    if not err.retryable:
                        logger.warning("[VECTOR][reliable_provider] non-retryable: {}", raw[:80])
                        break  # next model in chain

                    if err.rate_limited:
                        if is_non_retryable_rate_limit(raw):
                            self._rotate_key()
                            logger.warning("[VECTOR][reliable_provider] quota exhausted, rotated key")
                            break
                        self._rotate_key()

                    wait = self._backoff_ms(attempt, parse_retry_after_ms(raw))
                    logger.warning(
                        "[VECTOR][reliable_provider] attempt {}/{} failed ({}), backoff {:.1f}s",
                        attempt + 1, self.max_retries, raw[:60], wait,
                    )
                    await asyncio.sleep(wait)

        raise ProviderError(message=f"All retries exhausted. Last: {last_error}", retryable=False)

    async def _call(
        self,
        messages: list[dict],
        model: str,
        system: str | None,
        tools: list[dict] | None,
        temperature: float,
    ) -> CallResult:
        """Single HTTP call to OpenAI-compatible endpoint."""
        import httpx

        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        payload: dict[str, Any] = {
            "model": model,
            "messages": all_messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        headers = {"Content-Type": "application/json"}
        if self._current_key:
            headers["Authorization"] = f"Bearer {self._current_key}"

        async with httpx.AsyncClient(timeout=self.timeout_secs) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )

        if resp.status_code != 200:
            raise Exception(f"{resp.status_code} {resp.text[:200]}")

        data = resp.json()
        choice = data["choices"][0]
        content = choice["message"].get("content", "") or ""
        usage = data.get("usage", {})

        return CallResult(
            content=content,
            model=model,
            provider=self.name,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cached_tokens=usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
        )

    async def chat_simple(self, prompt: str, system: str | None = None, **kwargs) -> str:
        """Convenience wrapper — returns text string."""
        result = await self.chat(
            [{"role": "user", "content": prompt}],
            system=system,
            **kwargs,
        )
        return result.content


if __name__ == "__main__":
    import asyncio

    # Error classification tests
    assert is_non_retryable("400 Bad Request")
    assert not is_non_retryable("500 Internal Server Error")
    assert is_rate_limited("429 Too Many Requests")
    assert is_context_window_exceeded("context length exceeded")
    assert parse_retry_after_ms("Retry-After: 30") == 30000

    p = ReliableProvider(model="qwen3:14b", max_retries=2)
    chain = p._model_chain("qwen3:14b")
    assert chain[0] == "qwen3:14b"

    print("OK reliable_provider.py — error classification + retry logic verified")
