"""
VECTOR WebsiteToVideoAgent — District 18: content
Captures any URL as a narrated video for YouTube/social media.

Triggers:
  - governor task_type: "website_to_video", "url_capture", "site_video"
  - Direct: agent.run({"params": {"url": "https://arxiv.org/abs/...", "output": "out.mp4"}})

Pipeline:
  URL → scrape → extract content → screenshot → HTML composition → render → MP4
"""
from __future__ import annotations

import asyncio
import datetime
import os
import sys
import uuid
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from loguru import logger


class WebsiteToVideoAgent(AgentBase):
    """
    Converts any URL into a rendered narrated video.
    Powered by VECTOR's HTML rendering pipeline (    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="WebsiteToVideoAgent",
            district="content",
            generation=generation,
        )
        self.capabilities = ["capture_url", "content", "data_viz", "remove_bg", "title_card", "video", "website"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        logger.info("[VECTOR][website_to_video_agent] ready gen={} hp={}", generation, self.health_points)

    async def capture_url(
        self,
        url: str,
        output_path: str,
        duration: float = 8.0,
        quality: str = "standard",
        add_narration: bool = False,
        resolution: str = "landscape",
    ) -> dict:
        """Capture a URL as a video. Main entry point."""
        from core.video.website_to_video import WebsiteToVideo, CaptureOptions
        from core.video.composition_types import Fps

        logger.info("[VECTOR][w2v_agent] capturing: {}", url)

        pipeline = WebsiteToVideo()
        opts = CaptureOptions(
            url=url,
            output_path=output_path,
            fps=Fps(30, 1),
            resolution=resolution,
            quality=quality,   # type: ignore[arg-type]
            duration_seconds=duration,
            add_narration=add_narration,
        )

        try:
            result = await pipeline.capture(opts)
            self.award_points(40, f"website captured: {url}")
            self._memory.store(
                event_type="website_capture",
                content=f"WebsiteToVideo: {url} -> {output_path}",
                tags=["content", "video", "website"],
                source="website_to_video_agent",
            )
            return {
                "status": "ok",
                "url": url,
                "output": output_path,
                "title": result.title,
                "file_size": result.composer_result.file_size_bytes if result.composer_result else 0,
            }
        except Exception as e:
            logger.error("[VECTOR][w2v_agent] capture failed: {}", e)
            self.deduct_points(15, f"capture failed: {url}")
            return {"status": "error", "error": str(e), "url": url}

    async def render_title_card(
        self,
        title: str,
        subtitle: str = "",
        output_path: str = "title_card.mp4",
        duration: float = 5.0,
        style: str = "dark",
    ) -> dict:
        """Generate a VECTOR-branded title card video."""
        import tempfile
        from core.video.vector_composer import (
            VectorComposer, ComposerJob, CompositionTemplate
        )
        from core.video.composition_types import Fps

        with tempfile.TemporaryDirectory() as tmp:
            html_path = os.path.join(tmp, "title.html")
            CompositionTemplate.title_card(title, subtitle, style=style, output_path=html_path)

            composer = VectorComposer()
            job = ComposerJob(
                composition_path=html_path,
                output_path=output_path,
                fps=Fps(30, 1),
                resolution="landscape",
                duration_seconds=duration,
                quality="standard",
            )
            result = await composer.render(job)

        self.award_points(20, f"title card: {title}")
        return {"status": "ok", "output": output_path, "title": title,
                "size": result.file_size_bytes}

    async def render_data_viz(
        self,
        title: str,
        data: dict,
        output_path: str = "data_viz.mp4",
        duration: float = 8.0,
    ) -> dict:
        """Render a bar chart data visualization as video."""
        import tempfile
        from core.video.vector_composer import (
            VectorComposer, ComposerJob, CompositionTemplate
        )
        from core.video.composition_types import Fps

        with tempfile.TemporaryDirectory() as tmp:
            html_path = os.path.join(tmp, "viz.html")
            CompositionTemplate.data_viz(title, data, output_path=html_path)

            composer = VectorComposer()
            job = ComposerJob(
                composition_path=html_path,
                output_path=output_path,
                fps=Fps(30, 1),
                resolution="landscape",
                duration_seconds=duration,
            )
            result = await composer.render(job)

        self.award_points(25, f"data viz: {title}")
        return {"status": "ok", "output": output_path, "title": title,
                "size": result.file_size_bytes}

    async def remove_background(
        self,
        input_path: str,
        output_path: str,
        model: str = "u2net_human",
        quality: str = "balanced",
    ) -> dict:
        """Remove background from image or video → transparent output."""
        from core.video.background_remover import remove_background as _remove

        logger.info("[VECTOR][w2v_agent] removing background: {}", input_path)
        try:
            result = _remove(input_path, output_path, model=model, quality=quality)  # type: ignore[arg-type]
            self.award_points(15, f"bg removed: {input_path}")
            return {"status": "ok", "output": output_path,
                    "frames": result.frames_processed, "provider": result.provider}
        except Exception as e:
            logger.error("[VECTOR][w2v_agent] bg removal failed: {}", e)
            self.deduct_points(10, f"bg removal failed")
            return {"status": "error", "error": str(e)}

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", {}) or {}
        action = task.get("type") or p.get("action", "capture_url")

        if action == "capture_url":
            return await self.capture_url(
                url=p.get("url", ""),
                output_path=p.get("output", f"renders/website_{datetime.date.today()}.mp4"),
                duration=float(p.get("duration", 8.0)),
                quality=p.get("quality", "standard"),
                add_narration=bool(p.get("narration", False)),
            )
        elif action == "title_card":
            return await self.render_title_card(
                title=p.get("title", "VECTOR"),
                subtitle=p.get("subtitle", ""),
                output_path=p.get("output", "title_card.mp4"),
                duration=float(p.get("duration", 5.0)),
            )
        elif action == "data_viz":
            return await self.render_data_viz(
                title=p.get("title", "Data"),
                data=p.get("data", {}),
                output_path=p.get("output", "data_viz.mp4"),
                duration=float(p.get("duration", 8.0)),
            )
        elif action == "remove_bg":
            return await self.remove_background(
                input_path=p.get("input", ""),
                output_path=p.get("output", "out_alpha.webm"),
                model=p.get("model", "u2net_human"),
            )

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "can you turn my landing page into a short promo video?" previously
        # hit the bare "unhandled type" error stub. Every real capability
        # here (capture_url/title_card/data_viz/remove_bg) renders video or
        # processes media — a real, resource-consuming job — and there is no
        # safe read-only capability to fall back to. Never guess one from
        # free text; answer with a grounded explanation of what's needed
        # instead of an error stub.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            return {
                "status": "ok",
                "response": (
                    "I can capture a URL as a narrated video (capture_url + url), "
                    "render a title card (title_card + title), render a data "
                    "visualization (data_viz + title/data), or remove a background "
                    "from an image/video (remove_bg + input). Tell me which one and "
                    "give me the required input — I won't start a render without it."
                ),
            }

        return {
            "status": "error",
            "error": f"unhandled type '{action}'",
            "supported": ["capture_url", "title_card", "data_viz", "remove_bg"],
        }

    async def run_forever(self) -> None:
        logger.info("[VECTOR][website_to_video_agent] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][website_to_video_agent] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = WebsiteToVideoAgent()
        assert agent.health_points == 500
        assert agent.name == "WebsiteToVideoAgent"
        assert agent.district == "content"

        # Test title card (no Playwright needed for HTML generation)
        from core.video.vector_composer import CompositionTemplate
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            html = os.path.join(tmp, "t.html")
            CompositionTemplate.title_card("Test Title", "Subtitle", output_path=html)
            content = Path(html).read_text()
            assert "Test Title" in content
            assert "window.__vector" in content

        print(f"OK website_to_video.py (agent) HP={agent.health_points}")

    asyncio.run(_smoke())
