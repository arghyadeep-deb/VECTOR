"""
ImageAgent — wraps vectorcode's image_gen_provider/registry for AI image generation.

Dispatches to the configured image generation backend (ComfyUI, fal, Replicate,
DALL-E, Stable Diffusion API). Falls back to VECTOR's local ComfyUI adapter.
"""
from __future__ import annotations


from loguru import logger


class ImageAgent:
    """
    Vectorcode's image generation executor.
    Routes through the registered image provider or falls back to VECTOR's
    districts/content/comfyui_adapter.py.
    """

    def __init__(self):
        self._registry = None
        logger.info("[VECTOR][vc_image] initialized")

    def _get_registry(self):
        if self._registry is None:
            try:
                from vectorcode.src.agent import image_gen_registry as _reg
                self._registry = _reg
            except Exception as e:
                logger.debug("[VECTOR][vc_image] registry unavailable: {}", e)
        return self._registry

    def generate(self, prompt: str, aspect_ratio: str = "landscape",
                 model: str = "", negative_prompt: str = "") -> dict:
        """Generate an image. Returns {success, image, model, prompt, provider}."""
        registry = self._get_registry()
        if registry:
            try:
                provider = registry.get_active_provider()
                if provider:
                    result = provider.generate(
                        prompt=prompt,
                        aspect_ratio=aspect_ratio,
                        model=model or "",
                        negative_prompt=negative_prompt,
                    )
                    logger.info("[VECTOR][vc_image] provider={} success={}", provider.name, result.get("success"))
                    return result
            except Exception as e:
                logger.debug("[VECTOR][vc_image] provider failed: {}", e)

        # Fallback: VECTOR's local ComfyUI adapter
        try:
            from districts.content.comfyui_adapter import ComfyUIAdapter
            import asyncio
            adapter = ComfyUIAdapter()
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                adapter.run({"type": "generate", "prompt": prompt, "aspect_ratio": aspect_ratio})
            )
            loop.close()
            if result.get("status") == "ok":
                return {"success": True, "image": result.get("image_path", ""),
                        "model": "comfyui-local", "prompt": prompt, "provider": "comfyui"}
        except Exception as e:
            logger.warning("[VECTOR][vc_image] comfyui fallback failed: {}", e)

        return {"success": False, "error": "No image provider available",
                "prompt": prompt, "provider": "none"}

    def list_providers(self) -> list[str]:
        """List all registered image providers."""
        registry = self._get_registry()
        if registry:
            try:
                return [p.name for p in registry.list_providers()]
            except Exception:
                logger.opt(exception=True).debug("[VECTOR] suppressed exception")
        return ["comfyui-local"]


if __name__ == "__main__":
    agent = ImageAgent()
    providers = agent.list_providers()
    print(f"[OK] providers: {providers}")
    result = agent.generate("a futuristic AI city with glowing neural network nodes", "landscape")
    print(f"[OK] generate: success={result.get('success')} provider={result.get('provider')}")
    print("image_agent.py OK")
