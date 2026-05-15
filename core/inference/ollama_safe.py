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

import sys
import threading
from pathlib import Path

from loguru import logger

from core.config import CONFIG

# ── AirLLM fallback path (large 70B+ models only) ───────────────────────────
_AIRLLM_REPO = Path(__file__).parent.parent.parent.parent / "GitHub/lyogavin_airllm/repo"
if _AIRLLM_REPO.exists():
    sys.path.insert(0, str(_AIRLLM_REPO))

# Models that need AirLLM layer-streaming because they don't fit in VRAM directly.
# These should NEVER be in WARM_POOL — they're too big to stay resident.
_AIRLLM_MODELS = {
    "llama2-70b", "llama3-70b", "mixtral-8x7b", "falcon-40b", "codellama-70b",
}

# ── Warm pool: models always kept hot in VRAM ───────────────────────────────
# These are pre-loaded at startup and stay resident via keep_alive.
# Pick small, high-frequency models so 4 of them fit comfortably.
# Total VRAM ≈ 1 GB (ambient) + 3 GB (fast) + 5 GB (coder) + 0.3 GB (embed) = ~9.3 GB.
# Adjust to taste based on your GPU; matches OLLAMA_MAX_LOADED_MODELS=4.
WARM_POOL: list[str] = [
    CONFIG["models"]["ambient"],   # vector-ambient — wake-word + ambient classify
    CONFIG["models"]["fast"],      # vector-fast    — low-latency fallback
    CONFIG["models"]["coder"],     # vector-coder   — district 4 baseline
    CONFIG["models"]["embed"],     # nomic-embed-text — RAG embeddings
]

# Default keep_alive sent on every chat call — keeps models resident even
# after a long idle window. Set to 30m to match the Ollama daemon env var.
DEFAULT_KEEP_ALIVE = "30m"

# Internal state
_warmed: set[str] = set()
_warm_lock = threading.Lock()


def _is_airllm_model(model: str) -> bool:
    return any(m in model.lower() for m in _AIRLLM_MODELS)


def chat(
    model: str,
    messages: list[dict],
    timeout: float = 8.0,
    keep_alive: str | None = None,
) -> str:
    """Return Ollama chat text, or empty string on failure/timeout.

    Args:
        model: Ollama model tag (e.g. "vector-coder")
        messages: standard chat messages list
        timeout: HTTP timeout in seconds
        keep_alive: how long to keep the model resident after the call.
                    Defaults to DEFAULT_KEEP_ALIVE ("30m"); set to "-1" to
                    pin forever, or "0" to unload immediately after the call.
    """
    # Large models route through AirLLM
    if _is_airllm_model(model):
        result = _airllm_chat(model, messages)
        if result:
            return result
        # If AirLLM failed, still try Ollama (may have a smaller variant available)

    keep_alive = keep_alive or DEFAULT_KEEP_ALIVE

    try:
        import ollama
        client = ollama.Client(host=CONFIG["ollama_host"], timeout=timeout)
        response = client.chat(
            model=model,
            messages=messages,
            keep_alive=keep_alive,
        )
        return response.get("message", {}).get("content", "")
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] {model} unavailable: {e}")
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
        stream = client.chat(
            model=model,
            messages=messages,
            stream=True,
            keep_alive=keep_alive,
        )
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] {model} stream failed: {e}")
        yield ""


def _airllm_chat(model: str, messages: list[dict]) -> str:
    """Use AirLLM for large model inference. Returns empty string on failure."""
    try:
        from integrations.airllm.airllm_runner import AirLLMRunner
        import asyncio
        runner = AirLLMRunner()
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        loop = asyncio.new_event_loop()
        try:
            load_result = loop.run_until_complete(runner.load_model(model))
            if not load_result.get("success"):
                return ""
            gen_result = loop.run_until_complete(runner.generate(prompt))
            return gen_result.get("generated", "")
        finally:
            loop.close()
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] AirLLM fallback failed: {e}")
        return ""


# ── Warm-pool startup ────────────────────────────────────────────────────────


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
            # Embeddings models warm via embed endpoint; chat models via chat
            if "embed" in model.lower():
                client.embeddings(model=model, prompt="ping", keep_alive=keep_alive)
            else:
                client.chat(
                    model=model,
                    messages=[{"role": "user", "content": "."}],
                    options={"num_predict": 1},
                    keep_alive=keep_alive,
                )
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
    return results


def warmed_models() -> set[str]:
    """Return the set of models known to be hot in this process's view."""
    with _warm_lock:
        return set(_warmed)


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info(f"WARM_POOL: {WARM_POOL}")
    logger.info(f"AirLLM models: {_AIRLLM_MODELS}")
    logger.info(f"Default keep_alive: {DEFAULT_KEEP_ALIVE}")
