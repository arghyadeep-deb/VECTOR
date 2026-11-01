import sys
import uuid
import asyncio as _asyncio
import concurrent.futures as _cf

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


def _llm(prompt: str, max_tokens: int = 800, temperature: float = 0.85) -> str:
    from core.inference.provider_client import ProviderClient as _PC
    from core.prompt_library import get_library as _gl
    _sys = _gl().get_for_agent("video_generator") or ""
    messages = [{"role": "user", "content": prompt}]
    if _sys:
        messages = [{"role": "system", "content": _sys}] + messages
    async def _call():
        r = await _PC().chat(
            messages=messages,
            model="domain:content.video_prompts",   # gemini → gpt-4o → glm-4.7 → ollama
            tier="agentic", temperature=temperature, max_tokens=max_tokens,
            caller_id="video_generator",
        )
        return r.content
    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_asyncio.run, _call()).result(timeout=90)


class VideoGenerator(AgentBase):
    """
    Generates video descriptions, B-roll suggestions, and
    title/thumbnail ideas for video content.
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "VideoGenerator", "content")
        self.capabilities = ["content", "generate", "generate_tags", "render_html", "title", "title_thumbnail", "variables", "video"]
        if ghost:
            self.inherit_ghost(ghost)

        self._generated_content: list[dict] = []
        logger.info("[VECTOR][video_generator] VideoGenerator initialized")

    def generate_video_description(self, script: str, platform: str = "youtube") -> dict:
        """
        Generate SEO-optimized video description from script.
        Includes hashtags, timestamps, and key points.
        """
        platform_limits = {
            "youtube": {"max_length": 5000, "include_timestamps": True},
            "instagram": {"max_length": 2200, "include_timestamps": False},
            "tiktok": {"max_length": 150, "include_timestamps": False}
        }

        config = platform_limits.get(platform, platform_limits["youtube"])

        prompt = f"""Generate an SEO-optimized video description for {platform}.

Requirements:
- Max length: {config['max_length']} characters
- Include timestamps: {config['include_timestamps']}
- Make it engaging and keyword-rich

Script/Content:
{script[:3000]}

Include:
1. Hook line (first 1-2 lines to grab attention)
2. Key points summary
3. Timestamps (if applicable)
4. Relevant hashtags (5-10)
5. Links/call-to-action

Format appropriately for {platform}.
"""

        try:
            description = _llm(prompt, max_tokens=1200)

            description_data = {
                "id": str(uuid.uuid4()),
                "platform": platform,
                "description": description,
                "char_count": len(description),
                "created_at": self._get_timestamp()
            }

            self._generated_content.append(description_data)
            self.award_points(10, "video_description_generated")

            return {
                "status": "success",
                **description_data
            }

        except Exception as e:
            logger.error(f"[VECTOR][video_generator] Description generation failed: {e}")
            return {"error": str(e)}

    def suggest_broll(self, topic: str, duration_sec: int = 30) -> list[dict]:
        """
        Suggest B-roll footage for a topic.
        Returns list of B-roll suggestions with descriptions.
        """
        prompt = f"""Suggest B-roll footage for a video about: {topic}

Duration needed: approximately {duration_sec} seconds total

For each B-roll suggestion provide:
1. Scene description (what to show)
2. Duration (in seconds)
3. Where in the video it fits (intro, middle, etc.)
4. Source suggestion (stock site, type of footage)

Make suggestions diverse and visually engaging.
Format as a numbered list.
"""

        try:
            broll_text = _llm(prompt, max_tokens=800)
            broll_suggestions = self._parse_broll_suggestions(broll_text, topic)

            self.award_points(len(broll_suggestions) * 2, "broll_suggestions_generated")
            logger.info(f"[VECTOR][video_generator] Generated {len(broll_suggestions)} B-roll suggestions")

            return broll_suggestions

        except Exception as e:
            logger.error(f"[VECTOR][video_generator] B-roll suggestion failed: {e}")
            return []

    def _parse_broll_suggestions(self, broll_text: str, topic: str) -> list[dict]:
        """Parse B-roll suggestions from LLM response."""
        suggestions = []
        lines = broll_text.split("\n")
        current = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line and (line[0].isdigit() or line.startswith("-")):
                if current:
                    suggestions.append(current)

                current = {
                    "id": str(uuid.uuid4()),
                    "topic": topic,
                    "scene": line.lstrip("0123456789.- )").strip(),
                    "duration_sec": 5,
                    "placement": "main_content",
                    "source_hint": "",
                    "created_at": self._get_timestamp()
                }
            elif current:
                line_lower = line.lower()
                if "second" in line_lower or "sec" in line_lower:
                    import re
                    match = re.search(r'(\d+)', line)
                    if match:
                        current["duration_sec"] = int(match.group(1))
                elif "intro" in line_lower or "middle" in line_lower or "outro" in line_lower:
                    for placement in ["intro", "middle", "outro", "main_content", "conclusion"]:
                        if placement in line_lower:
                            current["placement"] = placement
                            break
                elif "stock" in line_lower or "source" in line_lower or "footage" in line_lower:
                    current["source_hint"] = line.split(":", 1)[-1].strip()

        if current:
            suggestions.append(current)

        return suggestions

    def generate_title_thumbnail(self, topic: str, count: int = 5) -> dict:
        """
        Generate video title options and thumbnail ideas.
        Returns titles and thumbnail concept descriptions.
        """
        prompt = f"""Generate {count} YouTube title options and thumbnail concepts for: {topic}

For each option provide:
1. Title (SEO-friendly, attention-grabbing, under 60 characters)
2. Thumbnail concept description (what text/visuals to include)
3. Title style (question, list, how-to, controversial, etc.)

Titles should:
- Be under 60 characters
- Include target keywords
- Create curiosity or promise value
- Be different from each other

Format clearly with numbered options.
"""

        try:
            content = _llm(prompt, max_tokens=1000)
            options = self._parse_title_options(content, topic)

            self.award_points(15, "title_thumbnail_generated")
            logger.info(f"[VECTOR][video_generator] Generated {len(options)} title options")

            return {
                "status": "success",
                "topic": topic,
                "options": options,
                "created_at": self._get_timestamp()
            }

        except Exception as e:
            logger.error(f"[VECTOR][video_generator] Title generation failed: {e}")
            options = [
                {
                    "id": str(uuid.uuid4()),
                    "topic": topic,
                    "title": f"{topic}: What You Need to Know",
                    "style": "how-to",
                    "thumbnail_concept": f"Clear bold text over a relevant visual for {topic}",
                    "char_count": len(f"{topic}: What You Need to Know"),
                    "created_at": self._get_timestamp(),
                }
            ]
            return {
                "status": "success",
                "topic": topic,
                "options": options,
                "created_at": self._get_timestamp(),
                "degraded": True,
                "warning": str(e),
            }

    def _parse_title_options(self, content: str, topic: str) -> list[dict]:
        """Parse title options from LLM response."""
        options = []
        lines = content.split("\n")
        current_option = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line and line[0].isdigit():
                if current_option:
                    options.append(current_option)

                current_option = {
                    "id": str(uuid.uuid4()),
                    "topic": topic,
                    "title": line.split(".", 1)[-1].strip() if "." in line else line,
                    "style": "unknown",
                    "thumbnail_concept": "",
                    "char_count": 0,
                    "created_at": self._get_timestamp()
                }
            elif current_option:
                line_lower = line.lower()
                if "style:" in line_lower or "type:" in line_lower:
                    current_option["style"] = line.split(":", 1)[-1].strip()
                elif "thumbnail" in line_lower or "concept" in line_lower:
                    current_option["thumbnail_concept"] = line.split(":", 1)[-1].strip()

        if current_option:
            current_option["char_count"] = len(current_option["title"])
            options.append(current_option)

        for opt in options:
            opt["char_count"] = len(opt["title"])

        return options

    def generate_tags(self, topic: str, count: int = 15) -> list[str]:
        """
        Generate YouTube tags for a topic.
        Returns list of relevant tags.
        """
        prompt = f"""Generate {count} YouTube tags for the topic: {topic}

Tags should:
- Include main keywords
- Be specific and relevant
- Include variations and related terms
- Mix of broad and narrow tags

Return ONLY a comma-separated list of tags, nothing else.
"""

        try:
            tags_text = _llm(prompt, max_tokens=200, temperature=0.5)
            tags = [t.strip() for t in tags_text.split(",") if t.strip()][:count]

            self.award_points(5, "tags_generated")
            return tags

        except Exception as e:
            logger.error(f"[VECTOR][video_generator] Tag generation failed: {e}")
            base = [t.strip().lower() for t in topic.replace("-", " ").split() if t.strip()]
            tags = base + [topic.lower(), "video", "explainer", "guide"]
            return list(dict.fromkeys(tags))[:count]

    def suggest_scheduling(self, topic: str) -> dict:
        """
        Suggest optimal posting times based on topic.
        Returns recommended days and times.
        """
        prompt = f"""Suggest optimal posting schedule for content about: {topic}

Consider:
1. Target audience time zones
2. Platform best practices
3. Topic-specific timing (educational, entertainment, news, etc.)
4. Competition analysis

Return recommended posting times with reasoning.
"""

        try:
            schedule = _llm(prompt, max_tokens=500, temperature=0.5)
            return {
                "status": "success",
                "topic": topic,
                "schedule": schedule,
                "recommendations": self._extract_schedule_recs(schedule)
            }

        except Exception as e:
            logger.error(f"[VECTOR][video_generator] Scheduling suggestion failed: {e}")
            return {"topic": topic, "error": str(e)}

    def _extract_schedule_recs(self, schedule_text: str) -> list[dict]:
        """Extract structured schedule recommendations."""
        recs = []
        lines = schedule_text.split("\n")

        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or "-" in line):
                recs.append({"text": line})

        return recs

    async def _render_with_hyperframes_first(self, html_path: str, output_path: str) -> str | None:
        """Try hyperframes sidecar first, fall back to VECTOR's own renderer."""
        try:
            from core.video.vector_composer import VectorComposer
            vc = VectorComposer()
            return await vc.render_via_hyperframes(html_path, output_path)
        except Exception as e:
            logger.debug("[VECTOR][video_gen] hyperframes unavailable: {}", e)
            return None

    async def render_html_to_video(self, html_path: str, output_path: str, **kwargs) -> dict:
        """Render an HTML composition to video.

        Tries hyperframes sidecar first (fast, GPU-accelerated), then falls
        back to VectorComposer's built-in renderer.
        """
        result_path = await self._render_with_hyperframes_first(html_path, output_path)
        if result_path:
            self.award_points(20, "html_video_rendered_hyperframes")
            return {"status": "ok", "path": result_path, "renderer": "hyperframes"}

        # Fallback: VECTOR's built-in VectorComposer render pipeline
        try:
            from core.video.vector_composer import VectorComposer, ComposerJob
            job = ComposerJob(
                composition_path=html_path,
                output_path=output_path,
                **{k: v for k, v in kwargs.items() if k in ("variables", "narration", "fps", "resolution")},
            )
            vc = VectorComposer()
            render_result = await vc.render(job)
            if render_result and getattr(render_result, "output_path", None):
                self.award_points(20, "html_video_rendered_composer")
                return {"status": "ok", "path": render_result.output_path, "renderer": "vector_composer"}
        except Exception as e:
            logger.warning("[VECTOR][video_gen] VectorComposer render failed: {}", e)

        return {"status": "error", "error": "all renderers failed", "html_path": html_path}

    async def run(self, task: dict) -> dict:
        """Governor dispatch interface."""
        p = task.get("params", {}) or {}
        task_type = task.get("type") or p.get("action", "title_thumbnail")
        supported = ["title_thumbnail", "generate_tags", "render_html"]

        if task_type in ("render_html", "render_video", "html_to_video"):
            return await self.render_html_to_video(
                html_path=p.get("html_path", ""),
                output_path=p.get("output_path", "output.mp4"),
            )
        if task_type == "generate_tags":
            tags = self.generate_tags(p.get("topic", "VECTOR AI"), count=p.get("count", 15))
            return {"status": "ok", "tags": tags}
        if task_type in ("title_thumbnail", "generate_title_thumbnail"):
            topic = p.get("topic", p.get("script", "VECTOR AI"))
            result = self.generate_title_thumbnail(topic, count=p.get("count", 5))
            return {**result, "status": "ok" if result.get("status") == "success" else "error"}

        # 2026-08-05: real chat dispatch arrives as an LLM-invented task_type
        # with the user's actual question in params["query"]/["content"] —
        # "can you suggest some tags for my new AI tools video?" previously
        # hit the bare "unhandled type" error stub. Route it to whichever
        # real capability the query actually asks for; never trigger
        # render_html_to_video (a real GPU render job) from unmatched free
        # text — that stays gated behind an exact type match above.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            q = query.lower()
            topic = p.get("topic", query)
            if any(w in q for w in ("title", "thumbnail")):
                result = self.generate_title_thumbnail(topic, count=p.get("count", 5))
                return {**result, "status": "ok" if result.get("status") == "success" else "error"}
            if "b-roll" in q or "broll" in q or "footage" in q:
                return {"status": "ok", "suggestions": self.suggest_broll(topic)}
            if "schedul" in q or ("post" in q and "time" in q):
                return self.suggest_scheduling(topic)
            if "description" in q:
                return self.generate_video_description(p.get("script", topic), platform=p.get("platform", "youtube"))
            # default: tag suggestions — cheapest, safest real capability,
            # no required args beyond the query text itself.
            tags = self.generate_tags(topic, count=p.get("count", 15))
            return {"status": "ok", "tags": tags}

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    generator = VideoGenerator()

    result = generator.generate_title_thumbnail("Python Machine Learning", 3)
    print(f"Generated {len(result.get('options', []))} title options")

    tags = generator.generate_tags("Web Development", 10)
    print(f"Generated {len(tags)} tags")

    print("✅ video_generator.py OK")
