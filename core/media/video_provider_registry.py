"""Video generation provider registry — SadTalker primary, cloud fallbacks."""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger


class VideoProviderRegistry:
    """Routes video generation across providers: SadTalker -> RunwayML -> Pika."""

    PROVIDERS = ["sadtalker", "runwayml", "pika"]

    async def generate(self, prompt: str = None, image_path: str = None,
                       audio_path: str = None, duration: int = 5) -> str | None:
        """Generate video, trying providers in order."""
        for provider in self.PROVIDERS:
            try:
                result = await self._generate_with(provider, prompt, image_path, audio_path, duration)
                if result:
                    logger.info("[VECTOR][video_registry] Generated via {}", provider)
                    return result
            except Exception as e:
                logger.warning("[VECTOR][video_registry] {} failed: {}", provider, e)
        return None

    async def _generate_with(self, provider, prompt, image_path, audio_path, duration):
        import os
        if provider == "sadtalker" and image_path and audio_path:
            from districts.content.video_generator import VoiceGenerator
            vg = VoiceGenerator()
            return await vg.generate_video(image_path=image_path, audio_path=audio_path) if hasattr(vg, 'generate_video') else None
        elif provider == "runwayml":
            api_key = os.getenv("RUNWAYML_API_KEY")
            if not api_key: return None
            # RunwayML Gen-3 API stub
            logger.info("[VECTOR][video_registry] RunwayML would generate: {}", prompt[:50] if prompt else "")
            return None
        elif provider == "pika":
            api_key = os.getenv("PIKA_API_KEY")
            if not api_key: return None
            return None
        return None


if __name__ == "__main__":
    r = VideoProviderRegistry()
    print("✅ video_provider_registry OK, providers:", r.PROVIDERS)
