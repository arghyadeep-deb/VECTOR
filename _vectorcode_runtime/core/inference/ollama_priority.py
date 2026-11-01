"""Priority gate for local Ollama access.

Ollama is configured with OLLAMA_MAX_LOADED_MODELS=1 on the owner's GPU, so
interactive voice/command calls and autonomous background calls can evict each
other even when VECTOR's process-level concurrency semaphores are behaving.
This gate is intentionally timing-only: it never changes prompts, models, or
decision content; it only lets background callers yield briefly when an owner
interaction is pending or active.
"""
from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

from loguru import logger

from core.config import CONFIG


__all__ = [
    "acquire_background",
    "acquire_background_sync",
    "acquire_interactive",
    "acquire_interactive_sync",
    "begin_interactive_session",
    "end_interactive_session",
    "has_interactive_demand",
    "has_interactive_demand_sync",
    "priority_mode_for_caller",
]


_INTERACTIVE_CALLER_PREFIXES = (
    "api_command",
    "governor_classify_chat_intent",
    "governor_answer_translate",
    "realtime_voice",
    "voice_",
)

_condition = threading.Condition()
_interactive_pending = 0
_interactive_active = 0


def priority_mode_for_caller(caller_id: str | None) -> str:
    """Return ``interactive`` for owner-facing call sites, else background."""
    caller = (caller_id or "").strip()
    if caller.startswith(_INTERACTIVE_CALLER_PREFIXES):
        return "interactive"
    return "background"


def has_interactive_demand_sync() -> bool:
    """True while an owner-facing Ollama call is waiting or active."""
    with _condition:
        return _interactive_pending > 0 or _interactive_active > 0


async def has_interactive_demand() -> bool:
    return await asyncio.to_thread(has_interactive_demand_sync)


def begin_interactive_session(*, caller_id: str = "realtime_voice") -> None:
    """Mark owner-facing demand active for a whole voice turn, not just the
    LLM call inside it.

    acquire_interactive()/acquire_interactive_sync() only mark demand for
    the duration of the Ollama call itself (_stream_ollama_tokens()). That
    leaves a real race window: VAD detection -> STT transcription ->
    speaker verification all happen BEFORE that call starts, sometimes
    taking several seconds on their own, during which a background caller
    sees no interactive demand at all and can win the single-model-slot
    race moments before the owner's turn actually needs vector-focus --
    live-observed 2026-10-14 as wildly inconsistent 8-35s latency for
    what should be a ~2s warm round trip. Call this as soon as the
    conversation leaves LISTENING for USER_SPEAKING (earliest real signal
    the owner is engaging), and end_interactive_session() once the turn's
    response is fully done -- covers the whole turn, not just its tail."""
    global _interactive_active
    with _condition:
        _interactive_active += 1
        _condition.notify_all()
    logger.debug("[VECTOR][ollama_priority] interactive session begin caller={}", caller_id)


def end_interactive_session(*, caller_id: str = "realtime_voice") -> None:
    global _interactive_active
    with _condition:
        _interactive_active = max(0, _interactive_active - 1)
        _condition.notify_all()
    logger.debug("[VECTOR][ollama_priority] interactive session end caller={}", caller_id)


@contextmanager
def acquire_interactive_sync(
    *,
    caller_id: str = "interactive",
    model: str = "",
) -> Iterator[None]:
    """Mark owner-facing Ollama demand before waiting on the normal semaphore."""
    global _interactive_pending, _interactive_active
    with _condition:
        _interactive_pending += 1
        _condition.notify_all()
    try:
        with _condition:
            _interactive_pending -= 1
            _interactive_active += 1
            _condition.notify_all()
        logger.debug(
            "[VECTOR][ollama_priority] interactive enter caller={} model={}",
            caller_id,
            model,
        )
        yield
    finally:
        with _condition:
            _interactive_active = max(0, _interactive_active - 1)
            _condition.notify_all()
        logger.debug(
            "[VECTOR][ollama_priority] interactive exit caller={} model={}",
            caller_id,
            model,
        )


@asynccontextmanager
async def acquire_interactive(
    *,
    caller_id: str = "interactive",
    model: str = "",
) -> AsyncIterator[None]:
    with acquire_interactive_sync(caller_id=caller_id, model=model):
        yield


@contextmanager
def acquire_background_sync(
    *,
    caller_id: str = "background",
    model: str = "",
    wait_timeout_sec: float | None = None,
) -> Iterator[None]:
    """Let background Ollama work yield to owner interactions, bounded."""
    timeout = (
        float(wait_timeout_sec)
        if wait_timeout_sec is not None
        else float(CONFIG.get("ollama_background_priority_wait_sec", 20.0))
    )
    start = time.monotonic()
    waited = 0.0
    with _condition:
        while (_interactive_pending > 0 or _interactive_active > 0) and waited < timeout:
            remaining = max(0.0, timeout - waited)
            _condition.wait(timeout=remaining)
            waited = time.monotonic() - start
    if waited > 0.0:
        logger.info(
            "[VECTOR][ollama_priority] background caller={} model={} yielded {:.2f}s for interactive demand",
            caller_id,
            model,
            min(waited, timeout),
        )
    if waited >= timeout and timeout > 0:
        logger.warning(
            "[VECTOR][ollama_priority] background caller={} model={} reached {:.1f}s priority wait cap; proceeding",
            caller_id,
            model,
            timeout,
        )
    yield


@asynccontextmanager
async def acquire_background(
    *,
    caller_id: str = "background",
    model: str = "",
    wait_timeout_sec: float | None = None,
) -> AsyncIterator[None]:
    cm = acquire_background_sync(
        caller_id=caller_id,
        model=model,
        wait_timeout_sec=wait_timeout_sec,
    )
    await asyncio.to_thread(cm.__enter__)
    try:
        yield
    finally:
        await asyncio.to_thread(cm.__exit__, None, None, None)


if __name__ == "__main__":
    assert priority_mode_for_caller("api_command") == "interactive"
    assert priority_mode_for_caller("vc_llm_vector-reasoning") == "background"
    print("OK ollama_priority.py")
