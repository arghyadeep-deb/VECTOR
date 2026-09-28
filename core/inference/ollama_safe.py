"""Safe Ollama wrapper — parallel-aware, warm-pool aware.

Ollama defaults to OLLAMA_MAX_LOADED_MODELS=1 on GPU, which causes models to
constantly load/unload as VECTOR's task router switches between coder, council,
ambient, etc. This wrapper:

  • Pins a small WARM_POOL so the highest-frequency models stay hot in VRAM
  • Passes ``keep_alive`` on every request so models don't unload between calls
  • Falls back to AirLLM only for the single 70B+ slot (large model fallback)

To make warm-pool actually parallel, the Ollama daemon also needs:
  OLLAMA_MAX_LOADED_MODELS >= len(WARM_POOL)
  OLLAMA_NUM_PARALLEL      >= 4
  OLLAMA_KEEP_ALIVE        >= 30m
(set once at User scope, then restart the Ollama tray daemon.)
"""
from __future__ import annotations

__all__ = [
    "chat",
    "chat_stream",
    "DEFAULT_KEEP_ALIVE",
    "warm_models",
    "warmed_models",
]


import os
import sys
import threading
import time
from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.resilience.circuit_breaker import CircuitBreakerOpenError
from core.breaker_registry import get_registry

# LangSmith tracing (2026-07-21, VECTOR eval work) — traceable() is a documented
# no-op when LANGCHAIN_TRACING_V2 isn't set, so this is safe to leave on
# permanently; falls back to an identity decorator if langsmith isn't
# importable for any reason so chat() never breaks because of tracing.
try:
    from langsmith import traceable
except Exception:
    def traceable(*_dargs, **_dkwargs):
        def _identity(fn):
            return fn
        return _identity

# â”€â”€ AirLLM fallback path (large 70B+ models only) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_airllm_env = os.environ.get("AIRLLM_REPO_PATH", "")
_AIRLLM_REPO = Path(_airllm_env) if _airllm_env else None
if _AIRLLM_REPO and _AIRLLM_REPO.exists():
    sys.path.insert(0, str(_AIRLLM_REPO))

# Models that need AirLLM layer-streaming because they don't fit in VRAM directly.
# These should NEVER be in WARM_POOL — they're too big to stay resident.
_AIRLLM_MODELS = {
    "llama2-70b", "llama3-70b", "mixtral-8x7b", "falcon-40b", "codellama-70b",
}

# â”€â”€ Warm pool: models always kept hot in VRAM â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# These are pre-loaded at startup and stay resident via keep_alive.
# Tuned for 12 GB VRAM (RTX 5070 mobile): vector-coder is the high-frequency
# workhorse for district 4 (coding, reviews, GitBot); nomic-embed-text is hit
# constantly by the memory layer. Total ~9.6 GB, leaving headroom for the
# 4th-slot rotating model (council, chairman, fast, etc.) to swap in cleanly.
#
# When you upgrade to >24 GB VRAM, expand to:
#   [ambient, fast, coder, embed, reasoning]
WARM_POOL: list[str] = [
    CONFIG["models"]["coder"],     # vector-coder    — district 4 baseline
    CONFIG["models"]["embed"],     # nomic-embed-text — RAG embeddings
]

# Default keep_alive sent on every chat call — keeps models resident even
# after a long idle window. Set to 30m to match the Ollama daemon env var.
DEFAULT_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")

# Absorbed OJ model catalog (supplementary — logs available models)
try:
    from vectorcode.src.intelligence import BUILTIN_MODELS, register_builtin_models
    register_builtin_models()
    logger.info(f"[VECTOR][ollama_safe] model catalog loaded ({len(BUILTIN_MODELS)} built-in)")
except Exception:
    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

def _wrap_with_circuit_breaker(name: str, func, *args, **kwargs):
    import asyncio
    cb = get_registry().get(name)
    if cb is None:
        return func(*args, **kwargs)
    try:
        _coro = cb.call(lambda: func(*args, **kwargs))
        return asyncio.run(_coro)
    except RuntimeError:
        _coro.close()
        import time
        from core.resilience.circuit_breaker import CircuitState
        if cb.state == CircuitState.OPEN:
            if time.time() - cb.last_failure_time < cb.config.recovery_timeout:
                raise CircuitBreakerOpenError(f"circuit breaker '{name}' is open")
            cb.state = CircuitState.HALF_OPEN
            cb.success_count = 0
            cb._half_open_retries = 0
        if cb.state == CircuitState.HALF_OPEN and cb._half_open_retries >= cb.config.half_open_max_retries:
            raise CircuitBreakerOpenError(f"circuit breaker '{name}' half-open retries exhausted")
        if cb.state == CircuitState.HALF_OPEN:
            cb._half_open_retries += 1
        try:
            result = func(*args, **kwargs)
            if cb.state == CircuitState.HALF_OPEN:
                cb.success_count += 1
                if cb.success_count >= cb.config.success_threshold:
                    cb.state = CircuitState.CLOSED
                    cb.failure_count = 0
            elif cb.state == CircuitState.CLOSED:
                cb.failure_count = 0
            return result
        except Exception:
            cb.failure_count += 1
            cb.last_failure_time = time.time()
            if cb.state == CircuitState.CLOSED and cb.failure_count >= cb.config.failure_threshold:
                cb.state = CircuitState.OPEN
            elif cb.state == CircuitState.HALF_OPEN:
                cb.state = CircuitState.OPEN
            raise

# Internal state
_warmed: set[str] = set()
_warm_lock = threading.Lock()

# â”€â”€ Concurrency bound â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# OLLAMA_MAX_LOADED_MODELS=1 (.claude/rules/models.md, 12GB RTX 5070 Ti) means
# the daemon holds exactly ONE model resident and serves every request off a
# single decode slot. Nothing here ever bounded how many requests VECTOR
# itself fired at it concurrently — two brain processes were once observed
# holding 90 simultaneous connections against a backend that serves one model
# at a time. This is the sync-side half of the fix (chat/chat_stream/
# warm_models all call `ollama.Client(...)` synchronously via the `ollama`
# package, which is not awaitable, so a threading.Semaphore is the correct
# primitive here — NOT an asyncio.Semaphore, which only guards coroutines on
# one event loop and would silently do nothing for calls made from worker
# threads). CONFIG["ollama_max_concurrent"] (default 2) is shared with the
# separate asyncio.Semaphore in provider_client.py; see that file's comment
# for why the two are independent instances rather than one shared lock.
_OLLAMA_SYNC_SEMAPHORE = threading.Semaphore(CONFIG["ollama_max_concurrent"])


def _is_airllm_model(model: str) -> bool:
    return any(m in model.lower() for m in _AIRLLM_MODELS)


def _inject_personality(messages: list[dict]) -> list[dict]:
    """Inject VECTOR personality system prompt into messages if enabled."""
    try:
        if not CONFIG.get("personality", {}).get("enabled", True):
            return messages
        from core.personality import PersonalityEngine
        pe = PersonalityEngine()
        personality_prompt = pe.tone.compose_system_prompt(pe.card, pe.sentiment.analyze(""))
        if not personality_prompt:
            return messages
        enriched = list(messages)
        system_idx = None
        for i, m in enumerate(enriched):
            if m.get("role") == "system":
                system_idx = i
                break
        personality_block = f"\n\n[PERSONALITY]\n{personality_prompt}"
        if system_idx is not None:
            enriched[system_idx] = {"role": "system", "content": enriched[system_idx]["content"] + personality_block}
        else:
            enriched.insert(0, {"role": "system", "content": personality_prompt})
        return enriched
    except Exception as e:
        logger.debug(f"[VECTOR][ollama_safe] personality injection skipped: {e}")
        return messages


@traceable(name="ollama_chat", run_type="llm")
def chat(
    model: str,
    messages: list[dict],
    timeout: float = 8.0,
    keep_alive: str | None = None,
    temperature: float = 0.7,
    think: bool | None = None,
    num_predict: int | None = None,
    *,
    caller_id: str = "ollama_safe_direct",
) -> str:
    """Return Ollama chat text, or empty string on failure/timeout.

    Args:
        model: Ollama model tag (e.g. "vector-coder")
        messages: standard chat messages list
        timeout: HTTP timeout in seconds
        keep_alive: how long to keep the model resident after the call.
                    Defaults to DEFAULT_KEEP_ALIVE ("30m"); set to "-1" to
                    pin forever, or "0" to unload immediately after the call.
        think: None = model default. False disables thinking-mode reasoning —
               essential for short classification calls (a thinking model
               burns 100+ hidden tokens before a one-line answer: ~7s → ~2s).
        num_predict: hard cap on generated tokens (None = model default).
        caller_id: observability tag — identifies which of the ~10 direct
                   callers (agent_base, governor, model_router, realtime
                   voice, ...) issued this call. Default "ollama_safe_direct"
                   when a caller doesn't pass one; never affects routing.
    """
    messages = _inject_personality(messages)

    # Large models route through AirLLM
    if _is_airllm_model(model):
        result = _airllm_chat(model, messages)
        if result:
            _record_observability(
                caller_id, model, "airllm", result, 0.0, status="ok",
            )
            return result
        # If AirLLM failed, still try Ollama (may have a smaller variant available)

    keep_alive = keep_alive or DEFAULT_KEEP_ALIVE

    # Energy-aware path — captures wall time + GPU energy if telemetry is wired.
    _energy_monitor = _get_energy_monitor()
    _start = time.time()
    try:
        import ollama
        # 2026-08-05 (connection-leak fix): must be `with ... as client:`, not a
        # bare assignment. ollama.Client() builds a full httpx.Client() with its
        # own connection pool (see ollama._client.BaseClient.__init__); httpx.Client
        # has no __del__, and its internal object graph is cyclic, so an
        # unclosed client's socket is NOT reclaimed by refcounting when `client`
        # goes out of scope — only a cyclic-GC sweep collects it, which is
        # unbounded in timing. Every call site here used to leak one ESTABLISHED
        # TCP connection to 127.0.0.1:11434 per invocation; confirmed live via
        # `Get-NetTCPConnection` climbing from 7 (fresh process) to 100 (25h
        # uptime) with zero drain, and reproduced in isolation (gc.disable() +
        # drop refs -> connections stay open; only gc.collect() closes them).
        # Concurrency bound: block here (never drop the call) until a slot
        # frees up. This is exactly the backpressure OLLAMA_MAX_LOADED_MODELS=1
        # needs — a caller waits its turn instead of piling onto a daemon that
        # can only actually serve requests off one resident model at a time.
        # Held only across the actual request/response round-trip below, not
        # across personality injection / AirLLM routing above, so those stay
        # unbounded (they don't touch Ollama).
        # 2026-08-06 (KNOWN_ISSUES #0 Part 1): `with _OLLAMA_SYNC_SEMAPHORE:`
        # blocks forever with no timeout. That was ranked secondary when first
        # found because it needs a slot-holder to already be stuck — but
        # fccdeb91f proved a holder CAN hang indefinitely (the exact
        # ThreadPoolExecutor-shutdown bug that fix addresses one layer up), so
        # a hang here would queue every other Ollama caller behind it too,
        # turning one stuck call into many. Bounded acquire instead; on
        # timeout, fall back exactly like a dead Ollama daemon does below
        # (_multi_backend_fallback, then "" — never raises, never fabricates a
        # response: chat()'s existing failure contract, not a new one).
        _sem_timeout = CONFIG.get("ollama_semaphore_timeout_sec", 60.0)
        if not _OLLAMA_SYNC_SEMAPHORE.acquire(timeout=_sem_timeout):
            logger.warning(
                f"[VECTOR][ollama_safe] semaphore acquire timed out after "
                f"{_sem_timeout}s for model={model} — all "
                f"{CONFIG['ollama_max_concurrent']} Ollama concurrency slot(s) "
                f"are still held, a caller is likely stuck (see KNOWN_ISSUES #0). "
                f"Falling back without touching Ollama."
            )
            fallback = _multi_backend_fallback(model, messages, timeout, caller_id=caller_id)
            if not fallback:
                _record_observability(
                    caller_id, model, "ollama", "", (time.time() - _start) * 1000,
                    status="error", error_kind="semaphore_timeout",
                )
            return fallback
        try:
            with ollama.Client(host=CONFIG["ollama_host"], timeout=timeout) as client:
                _opts = {"temperature": temperature}
                if num_predict is not None:
                    _opts["num_predict"] = num_predict
                _kwargs = {"model": model, "messages": messages,
                           "keep_alive": keep_alive, "options": _opts}
                if think is not None:
                    _kwargs["think"] = think

                def _call():
                    try:
                        return client.chat(**_kwargs)
                    except TypeError:
                        # Older ollama-python without the `think` kwarg — retry without.
                        _kwargs.pop("think", None)
                        return client.chat(**_kwargs)

                if _energy_monitor is not None:
                    with _energy_monitor.sample() as _energy:
                        response = _wrap_with_circuit_breaker("ollama", _call)
                    _record_telemetry(model, time.time() - _start, response, _energy)
                else:
                    response = _wrap_with_circuit_breaker("ollama", _call)
                    _record_telemetry(model, time.time() - _start, response, None)
                content = response.get("message", {}).get("content", "")
                _record_observability(
                    caller_id, model, "ollama", content,
                    (time.time() - _start) * 1000,
                    status="ok" if content else "empty_content",
                    input_tokens=int(response.get("prompt_eval_count", 0) or 0),
                    output_tokens=int(response.get("eval_count", 0) or 0),
                )
                return content
        finally:
            _OLLAMA_SYNC_SEMAPHORE.release()
    except CircuitBreakerOpenError:
        logger.warning(f"[VECTOR][ollama_safe] circuit breaker open for {model}")
        fallback = _multi_backend_fallback(model, messages, timeout, caller_id=caller_id)
        if not fallback:
            _record_observability(
                caller_id, model, "ollama", "", (time.time() - _start) * 1000,
                status="error", error_kind="circuit_breaker_open",
            )
        return fallback
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] {model} unavailable: {e}")
        # Multi-backend fallback — try LiteLLM (OpenAI-compatible / Apple FM / Gemma C++)
        # if ollama can't serve. This makes VECTOR resilient to a stopped daemon.
        fallback = _multi_backend_fallback(model, messages, timeout, caller_id=caller_id)
        if fallback:
            return fallback
        _record_observability(
            caller_id, model, "ollama", "", (time.time() - _start) * 1000,
            status="error", error_kind=type(e).__name__,
        )
        return ""


def chat_stream(
    model: str,
    messages: list[dict],
    timeout: float = 120.0,
    keep_alive: str | None = None,
    *,
    caller_id: str = "ollama_safe_stream",
):
    """Yield tokens one by one from Ollama streaming chat.

    Concurrency note: the semaphore below is held for the ENTIRE duration the
    caller spends iterating this generator, not just the instant the request
    is issued — deliberately. The resource being protected is Ollama's single
    decode slot (OLLAMA_MAX_LOADED_MODELS=1), and a caller mid-stream really
    is occupying that slot for as long as it keeps pulling tokens, so a slot
    that released early would let a second caller pile a second generation
    onto the same one-model daemon while the first is still mid-stream —
    exactly the over-subscription this bound exists to prevent. This does
    mean a slow consumer holds a slot longer; that is the correct trade-off
    here, not a bug. Ordinary generator cleanup (StopIteration, an exception,
    or an explicit .close()) runs the surrounding try/finally and releases
    the slot; a caller that abandons partial iteration without closing the
    generator relies on CPython's refcounting GC to call __del__ -> close(),
    same caveat already documented for the connection leak fix above.
    """
    keep_alive = keep_alive or DEFAULT_KEEP_ALIVE
    # See chat()'s comment above (KNOWN_ISSUES #0 Part 1) — bounded acquire,
    # not `with _OLLAMA_SYNC_SEMAPHORE:`. A stream call deliberately holds its
    # slot for the whole iteration (see docstring above), so a stuck holder
    # here is exactly the scenario the timeout exists to catch; on timeout we
    # yield "" and stop, the same honest-failure shape already used below for
    # a circuit-breaker-open or a hard Ollama failure.
    _sem_timeout = CONFIG.get("ollama_semaphore_timeout_sec", 60.0)
    _stream_start = time.time()
    if not _OLLAMA_SYNC_SEMAPHORE.acquire(timeout=_sem_timeout):
        logger.warning(
            f"[VECTOR][ollama_safe] semaphore acquire timed out after "
            f"{_sem_timeout}s for {model} stream — all "
            f"{CONFIG['ollama_max_concurrent']} Ollama concurrency slot(s) "
            f"are still held, a caller is likely stuck (see KNOWN_ISSUES #0)."
        )
        _record_observability(
            caller_id, model, "ollama", "", (time.time() - _stream_start) * 1000,
            status="error", error_kind="semaphore_timeout",
        )
        yield ""
        return
    _full_text = ""
    _prompt_eval_count = 0
    _eval_count = 0
    try:
        import ollama
        # See chat()'s comment above — must close the client (connection-leak fix).
        with ollama.Client(host=CONFIG["ollama_host"], timeout=timeout) as client:
            stream = _wrap_with_circuit_breaker("ollama", lambda: client.chat(
                model=model,
                messages=messages,
                stream=True,
                keep_alive=keep_alive,
            ))
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    _full_text += token
                    yield token
                # The final chunk (done=True) carries the same
                # prompt_eval_count/eval_count fields as the non-streaming
                # response — capture them for exact token counts instead of
                # falling back to the char-count estimate in
                # _record_observability(). Never affects what is yielded.
                if chunk.get("done"):
                    _prompt_eval_count = int(chunk.get("prompt_eval_count", 0) or 0)
                    _eval_count = int(chunk.get("eval_count", 0) or 0)
        _record_observability(
            caller_id, model, "ollama", _full_text, (time.time() - _stream_start) * 1000,
            status="ok" if _full_text else "empty_content",
            input_tokens=_prompt_eval_count,
            output_tokens=_eval_count,
        )
    except CircuitBreakerOpenError:
        logger.warning(f"[VECTOR][ollama_safe] circuit breaker open for {model} stream")
        _record_observability(
            caller_id, model, "ollama", _full_text, (time.time() - _stream_start) * 1000,
            status="error", error_kind="circuit_breaker_open",
        )
        yield ""
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] {model} stream failed: {e}")
        _record_observability(
            caller_id, model, "ollama", _full_text, (time.time() - _stream_start) * 1000,
            status="error", error_kind=type(e).__name__,
        )
        yield ""
    finally:
        _OLLAMA_SYNC_SEMAPHORE.release()


def _airllm_chat(model: str, messages: list[dict]) -> str:
    """Use AirLLM for large model inference. Returns empty string on failure."""
    import asyncio

    async def _run():
        from core.inference.airllm_runner import AirLLMRunner
        runner = AirLLMRunner()
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        load_result = await runner.load_model(model)
        if not load_result.get("success"):
            return ""
        result = await runner.generate(prompt)
        return result.get("generated", "")

    try:
        return asyncio.run(_run())
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] AirLLM fallback failed: {e}")
        return ""


# â”€â”€ Warm-pool startup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def warm_models(models: list[str] | None = None, keep_alive: str = "30m") -> dict[str, bool]:
    """Pre-load each model into VRAM so the first real request is instant.

    Sends a tiny no-op chat with keep_alive set to pin the model resident.
    Idempotent — already-warmed models in this process are skipped.

    Returns a dict of {model_name: success_bool}.
    """
    targets = models or WARM_POOL
    results: dict[str, bool] = {}

    with _warm_lock:
        to_warm = [m for m in targets if m not in _warmed]

    for model in to_warm:
        # See chat()'s comment above (KNOWN_ISSUES #0 Part 1) — bounded
        # acquire, not `with _OLLAMA_SYNC_SEMAPHORE:`. Models are warmed one
        # at a time in this loop already (sequential, not spawned as
        # concurrent threads), so this never nests — it just makes warm-up
        # share the same bound as regular chat() traffic instead of being
        # able to pile an unbounded warm-up burst on top of live requests at
        # startup. On timeout, treat it exactly like any other warm-up
        # failure below (results[model] = False) and move on to the next
        # model rather than blocking startup forever.
        _sem_timeout = CONFIG.get("ollama_semaphore_timeout_sec", 60.0)
        if not _OLLAMA_SYNC_SEMAPHORE.acquire(timeout=_sem_timeout):
            results[model] = False
            logger.warning(
                f"[VECTOR][ollama_safe] semaphore acquire timed out after "
                f"{_sem_timeout}s warming {model} — all "
                f"{CONFIG['ollama_max_concurrent']} Ollama concurrency slot(s) "
                f"are still held, a caller is likely stuck (see KNOWN_ISSUES #0)."
            )
            continue
        try:
            import ollama
            # See chat()'s comment above — must close the client (connection-leak fix).
            with ollama.Client(host=CONFIG["ollama_host"], timeout=60.0) as client:
                if "embed" in model.lower():
                    _wrap_with_circuit_breaker("ollama", lambda: client.embeddings(model=model, prompt="ping", keep_alive=keep_alive))
                else:
                    _wrap_with_circuit_breaker("ollama", lambda: client.chat(
                        model=model,
                        messages=[{"role": "user", "content": "."}],
                        options={"num_predict": 1},
                        keep_alive=keep_alive,
                    ))
            with _warm_lock:
                _warmed.add(model)
            results[model] = True
            logger.info(f"[VECTOR][ollama_safe] warmed {model}")
        except Exception as e:
            results[model] = False
            logger.warning(f"[VECTOR][ollama_safe] warm-up failed for {model}: {e}")
        finally:
            _OLLAMA_SYNC_SEMAPHORE.release()

    if results:
        ok = sum(1 for v in results.values() if v)
        logger.info(f"[VECTOR][ollama_safe] warm pool: {ok}/{len(results)} ready ({list(results.keys())})")

    # Also surface BUILTIN_MODELS that are locally available but not in WARM_POOL
    try:
        if "BUILTIN_MODELS" in dir() and isinstance(BUILTIN_MODELS, dict):
            available = set()
            for model_id in BUILTIN_MODELS:
                if isinstance(model_id, str) and model_id not in targets:
                    available.add(model_id)
            if available:
                logger.info(f"[VECTOR][ollama_safe] catalog models available: {list(available)[:5]}")
    except Exception:
        logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

    return results


def warmed_models() -> set[str]:
    """Return the set of models known to be hot in this process's view."""
    with _warm_lock:
        return set(_warmed)


# â”€â”€ Self-test â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if __name__ == "__main__":
    logger.info(f"WARM_POOL: {WARM_POOL}")
    logger.info(f"AirLLM models: {_AIRLLM_MODELS}")
    logger.info(f"Default keep_alive: {DEFAULT_KEEP_ALIVE}")



# â”€â”€ Energy + telemetry helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_energy_monitor_singleton: object | None = None
_energy_monitor_init = False
_telemetry_store_singleton: object | None = None
_telemetry_init = False


def _get_energy_monitor():
    """Lazy singleton — returns the EnergyMonitor or None if telemetry isn't wired.

    Detection runs once. If the telemetry module isn't installed or the GPU
    can't be probed, returns None and silently skips energy capture.
    """
    global _energy_monitor_singleton, _energy_monitor_init
    if _energy_monitor_init:
        return _energy_monitor_singleton
    _energy_monitor_init = True
    try:
        from core.telemetry import create_energy_monitor  # type: ignore[attr-defined]
        _energy_monitor_singleton = create_energy_monitor()
        if _energy_monitor_singleton is not None:
            logger.info(
                f"[VECTOR][ollama_safe] energy monitor active: "
                f"{_energy_monitor_singleton.vendor()}"
            )
    except Exception as exc:
        logger.debug(f"[VECTOR][ollama_safe] energy monitor unavailable: {exc}")
        _energy_monitor_singleton = None
    return _energy_monitor_singleton


def _get_telemetry_store():
    """Lazy singleton TelemetryStore for persistent inference records.

    Stores under <vector_root>/data/telemetry.db so it doesn't conflict with
    the main vector_memory.db. Schema is auto-migrated by TelemetryStore.
    """
    global _telemetry_store_singleton, _telemetry_init
    if _telemetry_init:
        return _telemetry_store_singleton
    _telemetry_init = True
    try:
        from core.telemetry import TelemetryStore  # type: ignore[attr-defined]
        # Build a sane default db path next to the project root
        from core.runtime_paths import data_path
        db_path = data_path("telemetry.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _telemetry_store_singleton = TelemetryStore(db_path)
        logger.info(f"[VECTOR][ollama_safe] telemetry store ready at {db_path}")
    except Exception as exc:
        logger.debug(f"[VECTOR][ollama_safe] telemetry store unavailable: {exc}")
        _telemetry_store_singleton = None
    return _telemetry_store_singleton


def _record_telemetry(model: str, latency_s: float, response: dict, energy) -> None:
    """Best-effort telemetry recording — never raises into the caller.

    Builds a TelemetryRecord dataclass and persists it via TelemetryStore.record().
    Captures: timestamp, model, latency, tokens, energy_joules, power_watts,
    gpu_utilization, energy_method, energy_vendor.
    """
    try:
        store = _get_telemetry_store()
        if store is None:
            return
        from vectorcode.src.vc_core.types import TelemetryRecord  # lazy import

        completion_tokens = int((response or {}).get("eval_count", 0) or 0)
        prompt_tokens = int((response or {}).get("prompt_eval_count", 0) or 0)
        total_tokens = prompt_tokens + completion_tokens

        # Energy fields default to 0 if monitor not active
        energy_joules = float(getattr(energy, "energy_joules", 0.0) or 0.0)
        power_watts = float(getattr(energy, "mean_power_watts", 0.0) or 0.0)
        gpu_util = float(getattr(energy, "mean_utilization_pct", 0.0) or 0.0)
        gpu_mem = float(getattr(energy, "mean_memory_used_gb", 0.0) or 0.0)
        gpu_temp = float(getattr(energy, "mean_temperature_c", 0.0) or 0.0)
        method = str(getattr(energy, "energy_method", "") or "")
        vendor = str(getattr(energy, "vendor", "") or "")

        # Derived: tokens per joule (efficiency), energy per output token
        tok_per_j = (total_tokens / energy_joules) if energy_joules > 0 else 0.0
        e_per_out = (energy_joules / completion_tokens) if completion_tokens > 0 else 0.0
        throughput = (completion_tokens / latency_s) if latency_s > 0 else 0.0

        rec = TelemetryRecord(
            timestamp=time.time(),
            model_id=model,
            engine="ollama",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_seconds=latency_s,
            energy_joules=energy_joules,
            power_watts=power_watts,
            gpu_utilization_pct=gpu_util,
            gpu_memory_used_gb=gpu_mem,
            gpu_temperature_c=gpu_temp,
            throughput_tok_per_sec=throughput,
            energy_per_output_token_joules=e_per_out,
            tokens_per_joule=tok_per_j,
            energy_method=method,
            energy_vendor=vendor,
        )
        store.record(rec)
    except Exception as exc:
        logger.debug(f"[VECTOR][telemetry] record failed: {exc}")


# â”€â”€ Multi-backend fallback (LiteLLM / Apple FM / Gemma C++) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _attempt_all_fallback_engines(
    model: str, fallback_messages, *, caller_id: str,
) -> str:
    """Sequentially try LiteLLM -> Apple Foundation Models -> Gemma C++.
    Unbounded by design (a slow/hung engine.generate() call blocks this
    function for as long as the engine takes) -- callers must bound their
    own wait via _multi_backend_fallback()'s deadline, not this function.
    Returns empty string if no fallback succeeds. Order and per-engine
    behavior are unchanged from before the R1 remediation (Task 88);
    only the caller-side bounding changed."""
    # Try LiteLLM
    litellm_model = os.getenv("VECTOR_LITELLM_FALLBACK_MODEL", "").strip() or model
    if _is_litellm_candidate(litellm_model):
        _t0 = time.time()
        try:
            from vectorcode.src.vc_engine.litellm import LiteLLMEngine  # type: ignore
            engine = LiteLLMEngine()
            result = engine.generate(fallback_messages, model=litellm_model, max_tokens=2048)
            text = (result or {}).get("content") or (result or {}).get("text", "")
            if text:
                logger.info(f"[VECTOR][ollama_safe] fallback: litellm -> {litellm_model}")
                _record_observability(
                    caller_id, litellm_model, "litellm_fallback", text,
                    (time.time() - _t0) * 1000, status="ok",
                )
                return text
        except Exception as exc:
            logger.debug(f"[VECTOR][ollama_safe] litellm fallback unavailable: {exc}")
    else:
        logger.debug(f"[VECTOR][ollama_safe] litellm fallback skipped for local model: {model}")

    # Try Apple Foundation Models (macOS Sonoma+ only)
    _t0 = time.time()
    try:
        from vectorcode.src.vc_engine.apple_fm_shim import AppleFMEngine  # type: ignore
        engine = AppleFMEngine()
        result = engine.generate(fallback_messages, model=model, max_tokens=2048)
        text = (result or {}).get("content") or (result or {}).get("text", "")
        if text:
            logger.info(f"[VECTOR][ollama_safe] fallback: apple_fm -> {model}")
            _record_observability(
                caller_id, model, "apple_fm_fallback", text,
                (time.time() - _t0) * 1000, status="ok",
            )
            return text
    except Exception as exc:
        logger.debug(f"[VECTOR][ollama_safe] apple_fm fallback unavailable: {exc}")

    # Try Gemma C++ (very small footprint)
    _t0 = time.time()
    try:
        from vectorcode.src.vc_engine.gemma_cpp import GemmaCppEngine  # type: ignore
        engine = GemmaCppEngine()
        result = engine.generate(fallback_messages, model=model, max_tokens=2048)
        text = (result or {}).get("content") or (result or {}).get("text", "")
        if text:
            logger.info(f"[VECTOR][ollama_safe] fallback: gemma_cpp -> {model}")
            _record_observability(
                caller_id, model, "gemma_cpp_fallback", text,
                (time.time() - _t0) * 1000, status="ok",
            )
            return text
    except Exception as exc:
        logger.debug(f"[VECTOR][ollama_safe] gemma_cpp fallback unavailable: {exc}")

    return ""


def _multi_backend_fallback(
    model: str, messages: list[dict], timeout: float,
    *, caller_id: str = "ollama_safe_direct",
) -> str:
    """When the local Ollama daemon is unavailable, try alternative engines
    in order of preference: LiteLLM (OpenAI-compatible) → Apple Foundation
    Models (macOS Sonoma+) → Gemma C++ binary.

    Returns empty string if no fallback succeeds.

    2026-09 (Task 88, R1 runtime remediation -- KNOWN_ISSUES class: a
    parameter accepted at a boundary and silently discarded, same family as
    the hypothesis/text key mismatch and the sorted()/json.dumps() policy-key
    mismatch): `timeout` used to be accepted here and never referenced --
    none of the three engine.generate() calls received it and none of them
    were wrapped in a circuit breaker, so a hung engine (network stall inside
    LiteLLM's litellm.completion(), a stuck pygemma.completion() native call,
    ...) blocked this synchronous function, and therefore its caller's
    thread, indefinitely. This is reachable from the event-loop thread via
    Governor._llm_classify() and AgentBase.vchat(), both of which call
    ollama_safe.chat() synchronously from inside `async def` functions.

    Fix: the actual three-engine attempt now runs on a dedicated worker
    thread and this function bounds its WAIT on that thread to `timeout`
    seconds via Future.result(timeout=...) -- never asyncio.wait_for (this
    function is synchronous and may be called from a thread with no running
    event loop). Engine order, per-engine try/except behavior, and the
    total-failure `return ""` contract are byte-for-byte unchanged from
    before this fix; only the caller-side wait is now bounded.

    KNOWN LIMITATION (residual, not solved by this fix, see Task 88 report):
    bounding the WAIT does not CANCEL the underlying engine call. Python
    threads cannot be forcibly terminated. If `_attempt_all_fallback_engines`
    is still inside e.g. `litellm.completion(...)` or
    `self._gemma.completion(prompt)` when the deadline is reached, that
    native/network call keeps running in the background, on its own thread,
    until it finishes or the process exits -- it is simply no longer being
    waited on, and its eventual result (if any) is discarded. Each call
    creates its own single-thread executor (not a shared pool), so a
    stuck call cannot exhaust a shared thread-pool slot needed by a later,
    independent fallback attempt; it can only leak its own one thread.
    """
    fallback_messages = _to_vectorcode_messages(messages)

    from concurrent.futures import ThreadPoolExecutor

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        _attempt_all_fallback_engines, model, fallback_messages, caller_id=caller_id,
    )
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        logger.warning(
            f"[VECTOR][ollama_safe] multi-backend fallback exceeded its {timeout}s "
            f"deadline for model={model} -- abandoning the wait and returning the "
            f"honest empty-string failure (chat()'s existing contract, not a new "
            f"one). KNOWN LIMITATION: the underlying engine call is NOT cancelled "
            f"and may continue running in the background on its own thread until "
            f"it completes or the process exits; see KNOWN_ISSUES / Task 88."
        )
        _record_observability(
            caller_id, model, "fallback", "", timeout * 1000,
            status="timeout", error_kind="fallback_deadline_exceeded",
        )
        return ""
    finally:
        # wait=False: do not block here on a possibly-still-running worker --
        # that would silently reintroduce the exact unbounded wait this fix
        # exists to remove. The (single, per-call) executor and its thread
        # are released for GC once the worker eventually returns.
        executor.shutdown(wait=False)


def _record_observability(
    caller_id: str,
    model: str,
    provider: str,
    content: str,
    latency_ms: float,
    *,
    status: str = "ok",
    error_kind: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Best-effort inference_calls record for ollama_safe's direct-call
    bypass path (does not route through ProviderClient.chat()). Never
    raises into the caller — observability must not break inference.
    Estimates tokens from char count // 4 when the caller didn't supply
    exact input_tokens/output_tokens (e.g. AirLLM/fallback engines that
    return plain text with no token-count field at all). The exact/estimated
    distinction is recorded in metadata.token_exact so reports never
    silently blend provider-reported and estimated counts."""
    try:
        from core.metering.inference_observability import (
            get_inference_observability, extract_domain, is_autonomous_caller,
        )
        token_exact = bool(input_tokens or output_tokens)
        if not token_exact and content:
            output_tokens = max(1, len(content) // 4)
        get_inference_observability().record(
            caller_id=caller_id,
            domain=extract_domain(caller_id, model),
            tier="",
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            is_ollama=(provider == "ollama"),
            is_autonomous=is_autonomous_caller(caller_id),
            status=status,
            error_kind=error_kind,
            metadata={"token_exact": token_exact},
        )
    except Exception:
        pass  # observability must never break the call path


def _to_vectorcode_messages(messages: list[dict]):
    """Convert OpenAI-style dict messages to vectorcode Message objects."""
    from vectorcode.src.vc_core.types import Message, Role

    role_map = {
        "system": Role.SYSTEM,
        "user": Role.USER,
        "assistant": Role.ASSISTANT,
        "tool": Role.TOOL,
    }
    converted = []
    for item in messages:
        role = role_map.get(str(item.get("role", "user")).lower(), Role.USER)
        converted.append(
            Message(
                role=role,
                content=str(item.get("content") or ""),
                name=item.get("name"),
                tool_call_id=item.get("tool_call_id"),
                metadata={"source": "ollama_safe_fallback"},
            )
        )
    return converted


def _is_litellm_candidate(model: str) -> bool:
    """Return True when a model name is explicit enough for LiteLLM routing."""
    if not model:
        return False
    if "/" in model:
        return True
    known_prefixes = (
        "gpt-",
        "o1",
        "o3",
        "o4",
        "claude-",
        "gemini/",
        "gemini-",
        "groq/",
        "deepseek/",
        "mistral/",
        "openrouter/",
        "together/",
        "fireworks/",
        "perplexity/",
        "cohere/",
        "xai/",
    )
    return model.startswith(known_prefixes)
