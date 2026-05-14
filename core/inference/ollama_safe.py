from __future__ import annotations

from loguru import logger
from core.config import CONFIG

# AirLLM repo path — for large model (70B+) fallback
import sys
from pathlib import Path
_AIRLLM_REPO = Path(__file__).parent.parent.parent.parent / "GitHub/lyogavin_airllm/repo"
if _AIRLLM_REPO.exists():
    sys.path.insert(0, str(_AIRLLM_REPO))

# Models that benefit from AirLLM layer-wise inference (too large for direct VRAM load)
_AIRLLM_MODELS = {"llama2-70b", "llama3-70b", "mixtral-8x7b", "falcon-40b", "codellama-70b"}


def chat(model: str, messages: list[dict], timeout: float = 8.0) -> str:
    """Return Ollama chat text, or empty string on failure/timeout.
    For large models (70B+), falls back to AirLLM layer-wise inference."""
    # Check if this model should use AirLLM
    if any(m in model.lower() for m in _AIRLLM_MODELS):
        result = _airllm_chat(model, messages)
        if result:
            return result

    try:
        import ollama
        client = ollama.Client(host=CONFIG["ollama_host"], timeout=timeout)
        response = client.chat(model=model, messages=messages)
        return response.get("message", {}).get("content", "")
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] {model} unavailable: {e}")
        return ""


def _airllm_chat(model: str, messages: list[dict]) -> str:
    """Use AirLLM for large model inference. Returns empty string on failure."""
    try:
        from integrations.airllm.airllm_runner import AirLLMRunner
        import asyncio
        runner = AirLLMRunner()
        # Convert messages to a single prompt
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


def chat_stream(model: str, messages: list[dict], timeout: float = 120.0):
    """Yield tokens one by one from Ollama streaming chat."""
    try:
        import ollama
        client = ollama.Client(host=CONFIG["ollama_host"], timeout=timeout)
        stream = client.chat(model=model, messages=messages, stream=True)
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] {model} stream failed: {e}")
        yield ""
