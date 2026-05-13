"""Vision tools — analyze images from URLs using vision-capable models."""

import base64
import httpx
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


async def analyze_image(image_url: str, prompt: str = "Describe this image in detail",
                        provider: str = "openai", api_key: Optional[str] = None) -> str:
    """Analyze an image using a vision-capable model."""
    try:
        image_data = await _download_image(image_url)
        base64_image = base64.b64encode(image_data).decode()

        if provider == "openai":
            api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
            if not api_key: return "OPENAI_API_KEY not set"
            async with httpx.AsyncClient() as c:
                r = await c.post("https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": "gpt-4o", "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}]})
                return r.json()["choices"][0]["message"]["content"]

        elif provider == "anthropic":
            api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key: return "ANTHROPIC_API_KEY not set"
            async with httpx.AsyncClient() as c:
                r = await c.post("https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": "claude-sonnet-4-6", "max_tokens": 1024, "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64_image}}
                    ]}]})
                return r.json()["content"][0]["text"]

        return f"No provider implementation for: {provider}"
    except Exception as e:
        return f"Vision analysis failed: {e}"


async def _download_image(url: str) -> bytes:
    async with httpx.AsyncClient() as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content
