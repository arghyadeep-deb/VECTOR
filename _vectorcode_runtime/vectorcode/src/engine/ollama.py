"""Ollama engine adapter for VECTOR."""
from __future__ import annotations
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx

OLLAMA_BASE_URL = "http://127.0.0.1:11434"

async def ollama_generate(model: str, prompt: str, **kwargs: Any) -> str:
    """Generate text with Ollama."""
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OLLAMA_BASE_URL}/api/generate",
                              json={"model": model, "prompt": prompt, "stream": False, **kwargs})
        r.raise_for_status()
        return r.json().get("response", "")

async def ollama_chat(model: str, messages: List[Dict], **kwargs: Any) -> str:
    """Chat with Ollama."""
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OLLAMA_BASE_URL}/api/chat",
                              json={"model": model, "messages": messages, "stream": False, **kwargs})
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")

def list_models() -> List[str]:
    """List installed Ollama models."""
    try:
        import subprocess
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        return [l.split()[0] for l in r.stdout.strip().splitlines()[1:] if l.strip()]
    except Exception:
        return []


class OllamaEngine:
    """Ollama-backed inference engine."""
    def __init__(self, model: str = "vector-focus", base_url: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.base_url = base_url

    async def generate(self, messages, **kw):
        return await ollama_chat(self.model, messages, **kw)

    async def get_models(self):
        return list_models()
