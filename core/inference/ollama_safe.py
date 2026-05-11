from __future__ import annotations

from loguru import logger

from core.config import CONFIG


def chat(model: str, messages: list[dict], timeout: float = 8.0) -> str:
    """Return Ollama chat text, or empty string on failure/timeout."""
    try:
        import ollama

        client = ollama.Client(host=CONFIG["ollama_host"], timeout=timeout)
        response = client.chat(model=model, messages=messages)
        return response.get("message", {}).get("content", "")
    except Exception as e:
        logger.warning(f"[VECTOR][ollama_safe] {model} unavailable: {e}")
        return ""
