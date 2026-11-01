"""
VECTOR MediaStudioAgent — District 18: content
AI creative media generation: images, videos, lip sync, animation.

Governor routes: generate_image, generate_video, animate_image, lipsync,
                 generate_i2i, background_remove, upscale, media_status

Usage:
    agent = MediaStudioAgent()
    result = asyncio.run(agent.run({"params": {"action": "generate_image",
                                               "prompt": "A neon cyberpunk city"}}))
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from core.media.generative_studio import GenerativeStudio
from core.media.models import list_by_category
from loguru import logger


class MediaStudioAgent(AgentBase):
    """
    VECTOR's creative media agent — images, videos, lip sync, animation.
    Routes to Wan2GP (free local video) -> sd.cpp (offline images). Local-only.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="MediaStudioAgent",
            district="content",
            generation=generation,
        )
        self.capabilities = ["animate_image", "background_remove", "content", "generate", "generate_i2i", "generate_image", "generate_video", "lipsync", "list_models", "media", "media_status", "status", "upscale"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        self._studio  = GenerativeStudio()
        logger.info("[VECTOR][media_studio] ready gen={} hp={}", generation, self.health_points)

    # ── Individual actions ────────────────────────────────────────────────────

    async def generate_image(self, prompt: str, model: str = "flux-dev", **kwargs) -> dict:
        """Text-to-image generation."""
        logger.info("[VECTOR][media_studio] t2i model={} prompt={!r:.60}", model, prompt)
        result = await self._studio.generate_image(prompt, model=model, **kwargs)
        self._store_result("generate_image", prompt, result)
        self.award_points(30, f"image: {prompt[:40]}")
        return result

    async def generate_i2i(self, prompt: str, image: str, model: str = "nano-banana-edit", **kwargs) -> dict:
        """Image-to-image editing."""
        logger.info("[VECTOR][media_studio] i2i model={}", model)
        result = await self._studio.generate_i2i(prompt, image, model=model, **kwargs)
        self._store_result("generate_i2i", prompt, result)
        self.award_points(30, f"i2i: {model}")
        return result

    async def generate_video(self, prompt: str, model: str = "ltx-video", **kwargs) -> dict:
        """Text-to-video generation."""
        logger.info("[VECTOR][media_studio] t2v model={} prompt={!r:.60}", model, prompt)
        result = await self._studio.generate_video(prompt, model=model, **kwargs)
        self._store_result("generate_video", prompt, result)
        self.award_points(30, f"video: {prompt[:40]}")
        return result

    async def animate_image(self, image: str, prompt: str = "", model: str = "wan22-i2v", **kwargs) -> dict:
        """Animate a still image into video."""
        logger.info("[VECTOR][media_studio] i2v model={}", model)
        result = await self._studio.animate_image(image, prompt=prompt, model=model, **kwargs)
        self._store_result("animate_image", prompt or image[:60], result)
        self.award_points(30, f"animate: {model}")
        return result

    async def lipsync(self, portrait: str, audio: str, model: str = "infinite-talk", **kwargs) -> dict:
        """Lip sync portrait + narration audio → talking head video."""
        logger.info("[VECTOR][media_studio] lipsync model={}", model)
        result = await self._studio.lipsync(portrait, audio, model=model, **kwargs)
        self._store_result("lipsync", f"portrait+audio → {model}", result)
        self.award_points(40, f"lipsync: {model}")
        return result

    async def background_remove(self, image: str) -> dict:
        result = await self._studio.background_remove(image)
        self._store_result("background_remove", image[:60], result)
        self.award_points(20, "bg_remove")
        return result

    async def upscale(self, image: str) -> dict:
        result = await self._studio.upscale(image)
        self._store_result("upscale", image[:60], result)
        self.award_points(20, "upscale")
        return result

    async def get_status(self) -> dict:
        return await self._studio.status()

    async def list_models(self, category: str | None = None) -> dict:
        if category:
            models = list_by_category(category)
        else:
            from core.media.models import all_models
            models = all_models()
        wan2gp = await self._studio._wan2gp.list_models()
        return {
            "cloud_models": [{"id": m.id, "name": m.name, "category": m.category} for m in models],
            "local_models": self._studio._local.list_models(),
            "wan2gp_models": wan2gp,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _store_result(self, event_type: str, context: str, result: dict) -> None:
        url = result.get("url") or result.get("image_path") or ""
        self._memory.store(
            event_type=event_type,
            content=f"MediaStudioAgent {event_type}: {context} → {url[:80]}",
            tags=["media", "content", event_type],
            source="media_studio_agent",
        )

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        # Accept the governor's task["type"] dispatch convention as the
        # primary key, falling back to the legacy params["action"] shape
        # so existing internal callers keep working unchanged.
        action = task.get("type") or p.get("action", "generate_image")

        if action in ("generate_image", "text_to_image", "t2i"):
            return await self.generate_image(
                prompt=p.get("prompt", ""),
                model=p.get("model", "flux-dev"),
                aspect_ratio=p.get("aspect_ratio", "1:1"),
                prefer_local=p.get("prefer_local", True),
            )
        elif action in ("generate_i2i", "image_to_image", "edit_image"):
            return await self.generate_i2i(
                prompt=p.get("prompt", ""),
                image=p.get("image", p.get("image_url", "")),
                model=p.get("model", "nano-banana-edit"),
            )
        elif action in ("generate_video", "text_to_video", "t2v"):
            return await self.generate_video(
                prompt=p.get("prompt", ""),
                model=p.get("model", "ltx-video"),
                aspect_ratio=p.get("aspect_ratio", "16:9"),
                prefer_local=p.get("prefer_local", True),
            )
        elif action in ("animate_image", "image_to_video", "i2v"):
            return await self.animate_image(
                image=p.get("image", p.get("image_url", "")),
                prompt=p.get("prompt", ""),
                model=p.get("model", "wan22-i2v"),
            )
        elif action == "lipsync":
            return await self.lipsync(
                portrait=p.get("portrait", p.get("image", "")),
                audio=p.get("audio", p.get("audio_url", "")),
                model=p.get("model", "infinite-talk"),
                is_video=p.get("is_video", False),
            )
        elif action == "background_remove":
            return await self.background_remove(p.get("image", p.get("image_url", "")))
        elif action == "upscale":
            return await self.upscale(p.get("image", p.get("image_url", "")))
        elif action in ("media_status", "status"):
            return await self.get_status()
        elif action == "list_models":
            return await self.list_models(p.get("category"))

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "what image and video generation models do you have available?"
        # previously hit the bare "unhandled type" error stub. This agent's
        # real capabilities (generate_image/generate_video/lipsync/upscale/
        # background_remove) are all real GPU render jobs — never trigger
        # one from an unmatched free-text query. Route to the two READ-ONLY,
        # no-required-argument capabilities instead: media_status/list_models.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            q = query.lower()
            if any(w in q for w in ("status", "health", "wan2gp", "up and running", "working")):
                return await self.get_status()
            return await self.list_models(p.get("category"))

        return {
            "status": "error",
            "error": f"unhandled type '{action}'",
            "supported": [
                "generate_image", "generate_i2i", "generate_video", "animate_image",
                "lipsync", "background_remove", "upscale", "media_status", "list_models",
            ],
        }

    async def run_forever(self) -> None:
        logger.info("[VECTOR][media_studio] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][media_studio] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = MediaStudioAgent()
        assert agent.health_points == 500
        assert agent.name == "MediaStudioAgent"
        assert agent.district == "content"

        # Status check (no API key needed)
        status = await agent.run({"params": {"action": "media_status"}})
        assert "wan2gp" in status

        # Model list
        models = await agent.run({"params": {"action": "list_models", "category": "t2i"}})
        assert "cloud_models" in models
        assert len(models["cloud_models"]) >= 3

        print(f"OK media_studio_agent.py HP={agent.health_points}")
        print(f"  t2i models: {len(models['cloud_models'])}")
        print(f"  mode: {status.get('mode')}")
        print(f"  wan2gp: {status['wan2gp']}")
        print(f"  local: {status['local']['binary_available']}")

    asyncio.run(_smoke())
