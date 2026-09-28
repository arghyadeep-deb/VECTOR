import sys
import uuid

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


async def _llm(prompt: str, max_tokens: int = 1500, temperature: float = 0.88) -> str:
    """2026-09-24 (external review, Phase 3 — loop-freeze root cause): this
    used to be a SYNC function that span up its own ThreadPoolExecutor +
    nested asyncio.run() and blocked on Future.result(timeout=120) --
    every caller here is itself async and already running inside the
    live autonomous-loop/API event loop, so that blocking call froze the
    ENTIRE event loop (all other dispatches, all other API requests) for
    up to 120s on every script/hook/CTA generation. ProviderClient.chat()
    is already async -- just await it directly."""
    from core.inference.provider_client import ProviderClient as _PC
    from core.prompt_library import get_library as _gl
    _sys = _gl().get_for_agent("script_generator") or ""
    messages = [{"role": "user", "content": prompt}]
    if _sys:
        messages = [{"role": "system", "content": _sys}] + messages
    r = await _PC().chat(
        messages=messages,
        model="domain:content.script",   # gpt-5 → glm-4.7 → llama-3.3 → ... → ollama
        tier="agentic", temperature=temperature, max_tokens=max_tokens,
        caller_id="script_generator",
    )
    return r.content


class ScriptGenerator(AgentBase):
    """
    Generates video scripts, hooks, and call-to-action content
    for YouTube, social media, and marketing videos.
    """

    SCRIPT_STRUCTURES = {
        "youtube_tutorial": {
            "sections": ["intro_hook", "topic_intro", "main_content", "examples", "summary", "cta"],
            "avg_pacing": "medium"
        },
        "youtube_short": {
            "sections": ["hook", "punch_line"],
            "avg_pacing": "fast"
        },
        "reel": {
            "sections": ["hook", "body", "cta"],
            "avg_pacing": "fast"
        },
        "explainer": {
            "sections": ["hook", "problem", "solution", "benefits", "cta"],
            "avg_pacing": "medium"
        },
        "review": {
            "sections": ["intro", "first_impressions", "deep_dive", "pros_cons", "verdict", "cta"],
            "avg_pacing": "slow"
        }
    }

    # 2026-09-24 (external review, Phase 3 -- KNOWN_ISSUES #81): class-level
    # (not instance-level) so it survives callers constructing a fresh
    # ScriptGenerator() on every dispatch. VECTOR_TECHNICAL_KNOWLEDGE/
    # 81_LIVE_LOOP_HEALTH_CHECK.md showed the identical "AI trends" topic
    # regenerated 1,306+ times in one day (content dispatch fires ~every 9s
    # with no upstream topic diversity). During the cooldown the last
    # successful script for that topic is returned (marked cached=True)
    # instead of burning another LLM call -- returning the real cached
    # content, not an empty skip, keeps downstream composition (script ->
    # schedule_post) working. Does not fix WHY the same topic keeps
    # arriving; that's the content/marketing pipeline's topic selection.
    _script_cache: dict[tuple, tuple[float, dict]] = {}
    _TOPIC_COOLDOWN_SECONDS = 3600.0

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "ScriptGenerator", "content")
        self.capabilities = ["content", "generate", "script", "video"]
        if ghost:
            self.inherit_ghost(ghost)

        self._generated_scripts: list[dict] = []
        self._hooks_cache: list[dict] = []
        logger.info("[VECTOR][script_generator] ScriptGenerator initialized")

    @classmethod
    def reset_script_cache(cls) -> None:
        cls._script_cache.clear()

    @staticmethod
    def _cache_key(topic: str, duration_min: float, script_type: str, facts: str | None) -> tuple:
        return (topic.strip().lower(), duration_min, script_type, hash(facts) if facts else None)

    def _cached_script(self, topic: str, duration_min: float, script_type: str,
                       facts: str | None = None) -> dict | None:
        import time
        entry = ScriptGenerator._script_cache.get(self._cache_key(topic, duration_min, script_type, facts))
        if entry and (time.time() - entry[0]) < self._TOPIC_COOLDOWN_SECONDS:
            return entry[1]
        return None

    def _remember_script(self, topic: str, duration_min: float, script_type: str, script: dict,
                         facts: str | None = None) -> None:
        import time
        ScriptGenerator._script_cache[self._cache_key(topic, duration_min, script_type, facts)] = (time.time(), script)

    async def generate_script(self, topic: str, duration_min: float = 5.0,
                        script_type: str = "youtube_tutorial",
                        facts: str | None = None) -> dict:
        """
        Generate a complete video script for a topic.
        Duration in minutes, script_type determines structure.

        `facts` is verified ground truth about the topic. Without it the model only
        has the topic string and will invent details (2026-09-25: it made up
        "personalities, economies and lives" for VECTOR's agents), so pass facts
        whenever the script must be accurate.
        """
        cached = self._cached_script(topic, duration_min, script_type, facts)
        if cached is not None:
            logger.debug(
                "[VECTOR][script_generator] '{}' generated within the last {:.0f}s "
                "-- returning cached script, no LLM call", topic, self._TOPIC_COOLDOWN_SECONDS,
            )
            return {**cached, "cached": True}

        structure = self.SCRIPT_STRUCTURES.get(
            script_type,
            self.SCRIPT_STRUCTURES["youtube_tutorial"]
        )

        prompt = f"""Generate a complete video script for a {duration_min}-minute {script_type.replace('_', ' ')} about: {topic}

Requirements:
- Total duration: {duration_min} minutes
- Script type: {script_type}
- Sections to include: {', '.join(structure['sections'])}
- Pacing: {structure['avg_pacing']}

For each section provide:
1. Section name
2. Duration (in seconds)
3. Full script text with dialogue/narration
4. Visual cues or B-roll suggestions

Make it engaging, natural-sounding, and suitable for video format.
Format with clear section headers.
"""
        if facts:
            prompt += f"""
Ground truth (use ONLY these facts). Do not invent features, numbers, names or visuals
that are not stated here. If something is not covered by these facts, leave it out:
{facts}
"""

        try:
            script_content = await _llm(prompt, max_tokens=2000)

            script = {
                "id": str(uuid.uuid4()),
                "topic": topic,
                "duration_min": duration_min,
                "script_type": script_type,
                "content": script_content,
                "sections": self._extract_sections(script_content),
                "word_count": len(script_content.split()),
                "estimated_duration": self._calculate_duration(script_content),
                "created_at": self._get_timestamp()
            }

            self._generated_scripts.append(script)
            self._remember_script(topic, duration_min, script_type, script, facts)
            self.award_points(25, f"script_generated_{topic[:20]}")

            logger.info(f"[VECTOR][script_generator] Generated {duration_min}min script for: {topic}")
            return script

        except Exception as e:
            logger.error(f"[VECTOR][script_generator] Script generation failed: {e}")
            return {"topic": topic, "error": str(e)}

    def _extract_sections(self, script_content: str) -> list[dict]:
        """Extract sections from generated script."""
        sections = []
        current_section = None
        current_content = []

        for line in script_content.split("\n"):
            line = line.strip()
            if not line:
                continue

            if any(header in line.lower() for header in [
                "intro", "hook", "topic", "content", "example",
                "summary", "cta", "conclusion", "outro", "problem",
                "solution", "verdict", "impression"
            ]):
                if current_section:
                    sections.append({
                        "name": current_section,
                        "content": "\n".join(current_content)
                    })

                current_section = line.strip(":- ").title()
                current_content = []
            else:
                if current_section:
                    current_content.append(line)

        if current_section:
            sections.append({
                "name": current_section,
                "content": "\n".join(current_content)
            })

        return sections

    def _calculate_duration(self, script_content: str) -> float:
        """Estimate video duration from script word count."""
        words = len(script_content.split())
        words_per_minute = 150
        return round(words / words_per_minute, 1)

    async def generate_hook(self, topic: str, count: int = 5) -> list[dict]:
        """
        Generate attention-grabbing hooks for a topic.
        Returns multiple hook variations.
        """
        prompt = f"""Generate {count} attention-grabbing video hooks for the topic: {topic}

Types of hooks to include:
1. Question hook - Start with a compelling question
2. Statistic hook - Lead with an interesting fact/number
3. Story hook - Begin with a short anecdote
4. Contrarian hook - State an unpopular opinion
5. Problem hook - Start with a pain point

For each hook provide:
1. Hook text (15-30 words max)
2. Hook type
3. Why it works (brief explanation)
4. Best used for (content type)

Be creative, bold, and attention-grabbing.
"""

        try:
            hooks_text = await _llm(prompt, max_tokens=1000)

            hooks = self._parse_hooks(hooks_text, topic)
            self._hooks_cache.extend(hooks)

            self.award_points(min(count * 3, 15), f"hooks_generated_for_{topic[:20]}")
            logger.info(f"[VECTOR][script_generator] Generated {len(hooks)} hooks for: {topic}")

            return hooks

        except Exception as e:
            logger.error(f"[VECTOR][script_generator] Hook generation failed: {e}")
            return []

    def _parse_hooks(self, hooks_text: str, topic: str) -> list[dict]:
        """Parse LLM response into structured hooks."""
        hooks = []
        lines = hooks_text.split("\n")
        current_hook = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line and (line[0].isdigit() or line.startswith("-")):
                if current_hook and current_hook.get("text"):
                    hooks.append(current_hook)

                current_hook = {
                    "id": str(uuid.uuid4()),
                    "topic": topic,
                    "text": line.lstrip("0123456789.- )").strip(),
                    "type": "unknown",
                    "why_it_works": "",
                    "best_for": "",
                    "created_at": self._get_timestamp()
                }
            elif current_hook:
                line_lower = line.lower()
                if "type:" in line_lower or "question" in line_lower or "statistic" in line_lower:
                    current_hook["type"] = line.split(":", 1)[-1].strip()
                elif "why" in line_lower or "works" in line_lower:
                    current_hook["why_it_works"] = line.split(":", 1)[-1].strip()
                elif "best" in line_lower or "used" in line_lower:
                    current_hook["best_for"] = line.split(":", 1)[-1].strip()

        if current_hook and current_hook.get("text"):
            hooks.append(current_hook)

        return hooks

    async def generate_cta(self, topic: str, cta_type: str = "standard") -> dict:
        """
        Generate call-to-action text for a topic.
        Types: standard, urgency, question, community
        """
        cta_instructions = {
            "standard": "Standard subscribe/like/comment CTA",
            "urgency": "CTA with time-sensitive urgency",
            "question": "Ask a question to drive comments",
            "community": "CTA to join a community or movement"
        }

        instruction = cta_instructions.get(cta_type, cta_instructions["standard"])

        prompt = f"""Generate a compelling call-to-action (CTA) for a video about: {topic}

CTA Type: {instruction}

Include:
1. Primary CTA (what you want them to do)
2. Secondary CTA (optional bonus action)
3. Reason to act (why they should do it)

Keep it concise, genuine, and not pushy.
Return ONLY the CTA text, nothing else.
"""

        try:
            cta_text = await _llm(prompt, max_tokens=300, temperature=0.7)

            self.award_points(5, "cta_generated")
            logger.info(f"[VECTOR][script_generator] Generated CTA for: {topic}")

            return {
                "status": "success",
                "topic": topic,
                "cta_type": cta_type,
                "cta_text": cta_text
            }

        except Exception as e:
            logger.error(f"[VECTOR][script_generator] CTA generation failed: {e}")
            return {"topic": topic, "error": str(e)}

    async def expand_script(self, script: dict, target_duration_min: float) -> dict:
        """Expand an existing script to target duration."""
        current_duration = script.get("duration_min", 5.0)
        if target_duration_min <= current_duration:
            return script

        expansion_factor = target_duration_min / current_duration

        prompt = f"""Expand this video script to be approximately {target_duration_min} minutes long.
Current length is about {current_duration} minutes, so you need to add about {(target_duration_min - current_duration):.1f} minutes of content.

Original Script:
{script.get('content', '')}

Keep the same structure and tone, but add more:
- Deeper explanations
- Additional examples
- More detailed demonstrations
- Extended Q&A sections

Return the expanded script with the same format.
"""

        try:
            expanded_content = await _llm(prompt, max_tokens=3000)

            expanded_script = script.copy()
            expanded_script["id"] = str(uuid.uuid4())
            expanded_script["duration_min"] = target_duration_min
            expanded_script["content"] = expanded_content
            expanded_script["word_count"] = len(expanded_content.split())
            expanded_script["expanded_from"] = script.get("id")
            expanded_script["created_at"] = self._get_timestamp()

            self._generated_scripts.append(expanded_script)
            self.award_points(15, "script_expanded")

            return expanded_script

        except Exception as e:
            logger.error(f"[VECTOR][script_generator] Script expansion failed: {e}")
            return script

    def get_generated_scripts(self, limit: int = 20) -> list[dict]:
        """Get recently generated scripts."""
        return self._generated_scripts[-limit:]

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        result = await self.generate_script(
            p.get("topic", "AI trends"), p.get("duration_min", 5.0),
            p.get("script_type", "youtube_tutorial"), facts=p.get("facts"),
        )
        return {"status": "ok", **result}


if __name__ == "__main__":
    import asyncio

    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        generator = ScriptGenerator()

        hooks = await generator.generate_hook("Python Programming", 3)
        print(f"Generated {len(hooks)} hooks")

        if hooks:
            print(f"First hook: {hooks[0].get('text', 'N/A')[:50]}...")

        cta = await generator.generate_cta("Web Development", "urgency")
        print(f"CTA: {cta.get('cta_text', 'N/A')[:50]}...")

        print("✅ script_generator.py OK")

    asyncio.run(_smoke())
