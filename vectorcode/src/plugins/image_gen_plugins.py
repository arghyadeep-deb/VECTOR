"""Image generation provider plugins — OpenAI, Codex, xAI backends."""

from loguru import logger
import os
from typing import Optional


try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False


async def generate_openai(prompt: str, size: str = "1024x1024", n: int = 1) -> dict:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key: return {"error": "OPENAI_API_KEY not set"}
    async with httpx.AsyncClient() as c:
        r = await c.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "dall-e-3", "prompt": prompt, "n": n, "size": size})
        return {"urls": [d["url"] for d in r.json().get("data", [])], "provider": "openai"}


async def generate_codex(prompt: str, size: str = "1024x1024") -> dict:
    key = os.environ.get("CODEX_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    if not key: return {"error": "No API key found"}
    async with httpx.AsyncClient() as c:
        r = await c.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "dall-e-3", "prompt": prompt, "n": 1, "size": size,
                  "style": "natural"})
        return {"urls": [d["url"] for d in r.json().get("data", [])], "provider": "codex"}


async def generate_xai(prompt: str) -> dict:
    key = os.environ.get("XAI_API_KEY", "")
    if not key: return {"error": "XAI_API_KEY not set"}
    async with httpx.AsyncClient() as c:
        r = await c.post("https://api.x.ai/v1/images/generations",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "grok-2-image", "prompt": prompt})
        return {"urls": [d["url"] for d in r.json().get("data", [])], "provider": "xai"}
