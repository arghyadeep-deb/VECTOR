"""Image generation provider registry — ComfyUI primary, cloud fallbacks."""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

import asyncio
import httpx
from loguru import logger
from core.config import CONFIG


class ImageProviderRegistry:
    """Routes image generation requests across providers with fallback chain."""

    PROVIDERS = ["comfyui", "replicate", "stability", "dalle"]

    async def generate(self, prompt: str, width: int = 512, height: int = 512,
                       steps: int = 20, model: str = None) -> bytes | None:
        """Generate image, trying providers in order until one succeeds."""
        for provider in self.PROVIDERS:
            try:
                result = await self._generate_with(provider, prompt, width, height, steps, model)
                if result:
                    logger.info("[VECTOR][image_registry] Generated via {}", provider)
                    return result
            except Exception as e:
                logger.warning("[VECTOR][image_registry] {} failed: {}", provider, e)
        logger.error("[VECTOR][image_registry] All providers failed")
        return None

    async def _generate_with(self, provider: str, prompt: str, width: int,
                              height: int, steps: int, model: str) -> bytes | None:
        if provider == "comfyui":
            return await self._comfyui(prompt, width, height, steps)
        elif provider == "replicate":
            return await self._replicate(prompt, width, height)
        elif provider == "stability":
            return await self._stability(prompt, width, height)
        elif provider == "dalle":
            return await self._dalle(prompt)
        return None

    async def _comfyui(self, prompt, width, height, steps) -> bytes | None:
        from districts.content.comfyui_adapter import ComfyUIAdapter
        adapter = ComfyUIAdapter()
        result = await adapter.generate_image(prompt=prompt, width=width, height=height, steps=steps)
        return result.get("image_bytes") if result else None

    async def _replicate(self, prompt, width, height) -> bytes | None:
        import os
        api_key = os.getenv("REPLICATE_API_TOKEN")
        if not api_key: return None
        async with httpx.AsyncClient() as client:
            r = await client.post("https://api.replicate.com/v1/predictions",
                json={"version": "stability-ai/sdxl:latest", "input": {"prompt": prompt, "width": width, "height": height}},
                headers={"Authorization": f"Token {api_key}"}, timeout=60)
            return r.content if r.status_code == 200 else None

    async def _stability(self, prompt, width, height) -> bytes | None:
        import os
        api_key = os.getenv("STABILITY_API_KEY")
        if not api_key: return None
        async with httpx.AsyncClient() as client:
            r = await client.post("https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                json={"text_prompts": [{"text": prompt}], "width": width, "height": height},
                headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
            return r.content if r.status_code == 200 else None

    async def _dalle(self, prompt) -> bytes | None:
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key: return None
        async with httpx.AsyncClient() as client:
            r = await client.post("https://api.openai.com/v1/images/generations",
                json={"prompt": prompt, "n": 1, "size": "512x512"},
                headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
            data = r.json()
            url = data.get("data", [{}])[0].get("url")
            if url:
                img = await client.get(url)
                return img.content
        return None


if __name__ == "__main__":
    r = ImageProviderRegistry()
    print("✅ image_provider_registry OK, providers:", r.PROVIDERS)
