"""
VideoAgent — wraps vectorcode's video_gen_provider/registry for AI video generation.

Dispatches to registered video backends (Runway, Luma, Pika, etc.).
Falls back to VECTOR's content/video_generator.py (SadTalker + FFmpeg CUDA).
"""
from __future__ import annotations


from loguru import logger


class VideoAgent:
    """
    Vectorcode's video generation executor.
    Routes through registered video provider or falls back to local FFmpeg pipeline.
    """

    def __init__(self):
        self._registry = None
        logger.info("[VECTOR][vc_video] initialized")

    def _get_registry(self):
        if self._registry is None:
            try:
                from vectorcode.src.agent import video_gen_registry as _reg
                self._registry = _reg
            except Exception as e:
                logger.debug("[VECTOR][vc_video] registry unavailable: {}", e)
        return self._registry

    def generate(self, prompt: str, duration_secs: float = 5.0,
                 aspect_ratio: str = "landscape", model: str = "") -> dict:
        """Generate a video clip. Returns {success, video_path, model, provider}."""
        registry = self._get_registry()
        if registry:
            try:
                provider = registry.get_active_provider()
                if provider:
                    result = provider.generate(
                        prompt=prompt,
                        duration_seconds=duration_secs,
                        aspect_ratio=aspect_ratio,
                        model=model or "",
                    )
                    logger.info("[VECTOR][vc_video] provider={} success={}", provider.name, result.get("success"))
                    return result
            except Exception as e:
                logger.debug("[VECTOR][vc_video] provider failed: {}", e)

        # Fallback: VECTOR's local video generator
        try:
            from districts.content.video_generator import VideoGenerator
            import asyncio
            gen = VideoGenerator()
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                gen.run({"type": "generate", "prompt": prompt, "duration": duration_secs})
            )
            loop.close()
            if result.get("status") == "ok":
                return {"success": True, "video_path": result.get("video_path", ""),
                        "model": "sadtalker-local", "provider": "local"}
        except Exception as e:
            logger.warning("[VECTOR][vc_video] local fallback failed: {}", e)

        return {"success": False, "error": "No video provider available", "prompt": prompt}

    def list_providers(self) -> list[str]:
        """List all registered video providers."""
        registry = self._get_registry()
        if registry:
            try:
                return [p.name for p in registry.list_providers()]
            except Exception:
                logger.opt(exception=True).debug("[VECTOR] suppressed exception")
        return ["sadtalker-local"]


if __name__ == "__main__":
    agent = VideoAgent()
    providers = agent.list_providers()
    print(f"[OK] providers: {providers}")
    result = agent.generate("VECTOR AI system overview animation")
    print(f"[OK] generate: success={result.get('success')} provider={result.get('provider')}")
    print("video_agent.py OK")
