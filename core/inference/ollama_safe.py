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


def chat(
    model: str,
    messages: list[dict],
    timeout: float = 8.0,
    keep_alive: str | None = None,
    temperature: float = 0.7,
    think: bool | None = None,
    num_predict: int | None = None,
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
    """
    messages = _inject_personality(messages)

    # Large models route through AirLLM
    if _is_airllm_model(model):
        result = _airllm_chat(model, messages)
        if result:
            return result
        # If AirLLM failed, still try Ollama (may have a smaller variant available)

    keep_alive = keep_alive or DEFAULT_KEEP_ALIVE

    # Energy-aware path — captures wall time + GPU energy if telemetry is wired.
    _energy_monitor = _get_energy_monitor()
    _start = time.time()
    try:
        import ollama
        client = ollama.Client(host=CONFIG["ollama_host"], timeout=timeout)
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
        return response.get("message", {}).get("content", "")
    except CircuitBreakerOpenError:
        logger.warning(f"[VECTOR][ollama_safe] circuit breaker open for {model}")
        fallback = _multi_backend_fallback(model, messages, timeout)
        return fallback
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] {model} unavailable: {e}")
        # Multi-backend fallback — try LiteLLM (OpenAI-compatible / Apple FM / Gemma C++)
        # if ollama can't serve. This makes VECTOR resilient to a stopped daemon.
        fallback = _multi_backend_fallback(model, messages, timeout)
        if fallback:
            return fallback
        return ""


def chat_stream(
    model: str,
    messages: list[dict],
    timeout: float = 120.0,
    keep_alive: str | None = None,
):
    """Yield tokens one by one from Ollama streaming chat."""
    keep_alive = keep_alive or DEFAULT_KEEP_ALIVE
    try:
        import ollama
        client = ollama.Client(host=CONFIG["ollama_host"], timeout=timeout)
        stream = _wrap_with_circuit_breaker("ollama", lambda: client.chat(
            model=model,
            messages=messages,
            stream=True,
            keep_alive=keep_alive,
        ))
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
    except CircuitBreakerOpenError:
        logger.warning(f"[VECTOR][ollama_safe] circuit breaker open for {model} stream")
        yield ""
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] {model} stream failed: {e}")
        yield ""


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
        try:
            import ollama
            client = ollama.Client(host=CONFIG["ollama_host"], timeout=60.0)
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
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "telemetry.db"
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


def _multi_backend_fallback(model: str, messages: list[dict], timeout: float) -> str:
    """When the local Ollama daemon is unavailable, try alternative engines
    in order of preference: LiteLLM (OpenAI-compatible) → Apple Foundation
    Models (macOS Sonoma+) → Gemma C++ binary.

    Returns empty string if no fallback succeeds.
    """
    fallback_messages = _to_vectorcode_messages(messages)

    # Try LiteLLM
    litellm_model = os.getenv("VECTOR_LITELLM_FALLBACK_MODEL", "").strip() or model
    if _is_litellm_candidate(litellm_model):
        try:
            from vectorcode.src.vc_engine.litellm import LiteLLMEngine  # type: ignore
            engine = LiteLLMEngine()
            result = engine.generate(fallback_messages, model=litellm_model, max_tokens=2048)
            text = (result or {}).get("content") or (result or {}).get("text", "")
            if text:
                logger.info(f"[VECTOR][ollama_safe] fallback: litellm -> {litellm_model}")
                return text
        except Exception as exc:
            logger.debug(f"[VECTOR][ollama_safe] litellm fallback unavailable: {exc}")
    else:
        logger.debug(f"[VECTOR][ollama_safe] litellm fallback skipped for local model: {model}")

    # Try Apple Foundation Models (macOS Sonoma+ only)
    try:
        from vectorcode.src.vc_engine.apple_fm_shim import AppleFMEngine  # type: ignore
        engine = AppleFMEngine()
        result = engine.generate(fallback_messages, model=model, max_tokens=2048)
        text = (result or {}).get("content") or (result or {}).get("text", "")
        if text:
            logger.info(f"[VECTOR][ollama_safe] fallback: apple_fm -> {model}")
            return text
    except Exception as exc:
        logger.debug(f"[VECTOR][ollama_safe] apple_fm fallback unavailable: {exc}")

    # Try Gemma C++ (very small footprint)
    try:
        from vectorcode.src.vc_engine.gemma_cpp import GemmaCppEngine  # type: ignore
        engine = GemmaCppEngine()
        result = engine.generate(fallback_messages, model=model, max_tokens=2048)
        text = (result or {}).get("content") or (result or {}).get("text", "")
        if text:
            logger.info(f"[VECTOR][ollama_safe] fallback: gemma_cpp -> {model}")
            return text
    except Exception as exc:
        logger.debug(f"[VECTOR][ollama_safe] gemma_cpp fallback unavailable: {exc}")

    return ""


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
