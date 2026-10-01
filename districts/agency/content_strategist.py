import sys
import re
import uuid
import json
import asyncio as _asyncio
import concurrent.futures as _cf
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.obsidian_sync import ObsidianSync


def _llm(prompt: str, max_tokens: int = 800, temperature: float = 0.8) -> str:
    """Sync LLM call via ProviderClient — works inside or outside a running event loop."""
    from core.inference.provider_client import ProviderClient as _PC
    from core.loop.context_engine import ContextEngine
    from core.prompt_library import get_library as _gl
    hydration = ContextEngine().session_hydration_prompt({"task": "content_strategy"})
    _sys = _gl().get_for_agent("content_creator") or ""
    messages = [{"role": "system", "content": hydration}]
    if _sys:
        messages.append({"role": "system", "content": _sys})
    messages.append({"role": "user", "content": prompt})
    async def _call():
        r = await _PC().chat(
            messages=messages,
            tier="agentic",
            temperature=temperature,
            max_tokens=max_tokens,
            caller_id="content_strategist",
        )
        return r.content
    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_asyncio.run, _call()).result(timeout=90)


def _safe_filename(text: str, limit: int = 30) -> str:
    """Reduce caller-supplied text to a single safe path component (CWE-22)."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(text)[:limit]).strip("_") or "untitled"


class ContentStrategist(AgentBase):
    """
    Analyzes content trends and suggests content topics for social media,
    blogs, and marketing campaigns.
    """

    CONTENT_TYPES = [
        "blog_post", "social_media", "video_script", "podcast_episode",
        "email_newsletter", "infographic", "case_study", "how_to_guide"
    ]

    PLATFORMS = {
        "youtube": {"max_length": 600, "best_for": ["video_script", "tutorial", "review"]},
        "twitter": {"max_length": 280, "best_for": ["social_media", "opinion", "update"]},
        "linkedin": {"max_length": 3000, "best_for": ["blog_post", "case_study", "professional"]},
        "instagram": {"max_length": 2200, "best_for": ["social_media", "visual", "story"]},
        "reddit": {"max_length": 40000, "best_for": ["discussion", "ama", "guide"]}
    }

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "ContentStrategist", "agency")
        self.capabilities = ["agency", "content", "strategy"]
        if ghost:
            self.inherit_ghost(ghost)

        self._obsidian = ObsidianSync()
        self._content_dir = "Research/ContentStrategy"
        self._trends_cache: dict = {}
        self._topic_ideas: list[dict] = []
        logger.info("[VECTOR][content_strategist] ContentStrategist initialized")

    async def analyze_trends(self, topic: str) -> dict:
        """
        Use Ollama to analyze content trends for a given topic.
        Returns trend analysis with insights.
        """
        prompt = f"""Analyze current content trends for the topic: {topic}

Consider:
1. What type of content is performing well?
2. What angles or hooks are working?
3. What questions is the audience asking?
4. What formats are most engaging?
5. What timing/demographics matter?

Return a structured analysis in this format:
TRENDS:
- [Platform]: Description
- [Platform]: Description

AUDIENCE INSIGHTS:
- Key interest points
- Common questions
- Pain points

CONTENT OPPORTUNITIES:
- High potential topics
- Unique angles to explore
- Format recommendations

Be specific and actionable.
"""

        try:
            analysis = _llm(prompt, max_tokens=800)
            self._trends_cache[topic] = {
                "analysis": analysis,
                "timestamp": self._get_timestamp()
            }
            self.award_points(15, f"trends_analyzed_for_{topic}")
            logger.info(f"[VECTOR][content_strategist] Analyzed trends for: {topic}")
            return {
                "topic": topic,
                "analysis": analysis,
                "timestamp": self._get_timestamp()
            }
        except Exception as e:
            logger.error(f"[VECTOR][content_strategist] Trend analysis failed: {e}")
            return {"topic": topic, "error": str(e)}

    def suggest_topics(self, niche: str, count: int = 10) -> list[dict]:
        """
        Generate content topic suggestions for a niche.
        Returns list of topic ideas with metadata.
        """
        prompt = f"""Generate {count} content topic ideas for the niche: {niche}

For each topic include:
1. Title (catchy and engaging)
2. Content type (blog_post, video, social_media, etc.)
3. Target platform
4. Key angle or hook
5. Brief description (2-3 sentences)
6. SEO keywords (3-5)

Format as a numbered list with all details.
Make topics diverse, engaging, and relevant to current trends.
"""

        try:
            suggestions = _llm(prompt, max_tokens=1200)
            topics = self._parse_topics_from_response(suggestions, niche)
            self._topic_ideas.extend(topics)
            self.award_points(min(count, 10), f"topics_suggested_for_{niche}")
            logger.info(f"[VECTOR][content_strategist] Generated {len(topics)} topics for {niche}")
            return topics
        except Exception as e:
            logger.error(f"[VECTOR][content_strategist] Topic suggestion failed: {e}")
            return []

    def _parse_topics_from_response(self, response: str, niche: str) -> list[dict]:
        """Parse LLM response into structured topic list."""
        topics = []
        lines = response.split("\n")
        current_topic = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line and line[0].isdigit():
                if current_topic:
                    topics.append(current_topic)

                current_topic = {
                    "id": str(uuid.uuid4()),
                    "niche": niche,
                    "title": line.split(".", 1)[-1].strip() if "." in line else line,
                    "content_type": "blog_post",
                    "platform": "linkedin",
                    "angle": "",
                    "description": "",
                    "keywords": [],
                    "created_at": self._get_timestamp()
                }
            elif current_topic:
                line_lower = line.lower()
                if "type:" in line_lower or "content" in line_lower:
                    for ct in self.CONTENT_TYPES:
                        if ct in line_lower:
                            current_topic["content_type"] = ct
                            break
                elif "platform:" in line_lower:
                    for platform in self.PLATFORMS.keys():
                        if platform in line_lower:
                            current_topic["platform"] = platform
                            break
                elif "angle:" in line_lower or "hook:" in line_lower:
                    current_topic["angle"] = line.split(":", 1)[-1].strip()
                elif "keyword" in line_lower:
                    current_topic["keywords"] = [
                        kw.strip().strip(",") for kw in line.split(":", 1)[-1].split()
                        if len(kw.strip()) > 2
                    ]

        if current_topic:
            topics.append(current_topic)

        return topics

    def create_content_plan(self, topic: str) -> dict:
        """
        Create a structured content plan for a topic.
        Includes headlines, content outline, and distribution strategy.
        """
        prompt = f"""Create a comprehensive content plan for the topic: {topic}

Include:
1. Main headline (attention-grabbing)
2. Subheadline (supporting)
3. Content outline (5-7 main sections)
4. Key points for each section (bullet points)
5. Call-to-action suggestions
6. Optimal posting times
7. Cross-platform adaptation notes
8. Engagement prompts for audience

VECTOR ban-safety constraints (posting is via a real device — respect these or the
account gets flagged): a NEW account must warm up ~10 days (human activity, no posting)
before its first post; then at most 1 post/day, spaced 6h+, at human-varied (not exact
clock) times. Ramp volume slowly over weeks. Never propose bulk/burst posting or bought
engagement. Enforced in code by core/control/social_safety.py.

Format clearly with headers and bullet points.
Make it actionable and ready to execute.
"""

        try:
            plan_content = _llm(prompt, max_tokens=1500)

            plan = {
                "id": str(uuid.uuid4()),
                "topic": topic,
                "content": plan_content,
                "headlines": self._extract_headlines(plan_content),
                "outline": self._extract_outline(plan_content),
                "platforms": self._suggest_platforms(topic),
                "created_at": self._get_timestamp(),
                "status": "draft"
            }

            self._save_content_plan(plan)
            self.award_points(20, f"content_plan_created_for_{topic}")

            logger.info(f"[VECTOR][content_strategist] Created content plan for: {topic}")
            return plan

        except Exception as e:
            logger.error(f"[VECTOR][content_strategist] Content plan creation failed: {e}")
            return {"topic": topic, "error": str(e)}

    def _extract_headlines(self, content: str) -> list[str]:
        """Extract headlines from content plan."""
        headlines = []
        lines = content.split("\n")
        for line in lines:
            if any(marker in line.lower() for marker in ["headline", "title"]):
                headline = line.split(":", 1)[-1].strip()
                if headline:
                    headlines.append(headline)
        return headlines[:5]

    def _extract_outline(self, content: str) -> list[str]:
        """Extract content outline from content plan."""
        outline = []
        lines = content.split("\n")
        in_outline = False

        for line in lines:
            if "outline" in line.lower() or "section" in line.lower():
                in_outline = True
                continue
            if in_outline and line.strip():
                if any(end in line.lower() for end in ["posting time", "cross-platform", "engagement"]):
                    break
                if line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "- ", "* ")):
                    outline.append(line.lstrip("1234567.-* ").strip())

        return outline[:7]

    def _suggest_platforms(self, topic: str) -> list[str]:
        """Suggest best platforms for a topic."""
        topic_lower = topic.lower()

        if any(kw in topic_lower for kw in ["tutorial", "how", "learn", "guide"]):
            return ["youtube", "linkedin", "reddit"]
        elif any(kw in topic_lower for kw in ["opinion", "thought", "take"]):
            return ["twitter", "linkedin"]
        elif any(kw in topic_lower for kw in ["product", "review", "unbox"]):
            return ["youtube", "instagram"]
        elif any(kw in topic_lower for kw in ["discussion", "ask", "ama"]):
            return ["reddit", "twitter"]

        return ["linkedin", "twitter"]

    def _save_content_plan(self, plan: dict) -> bool:
        """Save content plan to Obsidian vault."""
        try:
            plan_dir = self._obsidian._vault / self._content_dir / "Plans"
            plan_dir.mkdir(parents=True, exist_ok=True)

            plan_file = plan_dir / f"{_safe_filename(plan['topic'])}_{plan['id'][:8]}.md"
            if not plan_file.resolve().is_relative_to(plan_dir.resolve()):
                raise ValueError("plan path escapes vault plan directory")
            content = f"""# Content Plan: {plan['topic']}

Created: {plan['created_at']}
Status: {plan['status']}

## Headlines
{chr(10).join(f"- {h}" for h in plan.get('headlines', []))}

## Platform Strategy
{', '.join(plan.get('platforms', []))}

## Content Outline
{chr(10).join(f"{i+1}. {s}" for i, s in enumerate(plan.get('outline', [])))}

---

{plan['content']}
"""

            plan_file.write_text(content, encoding="utf-8")
            return True

        except Exception as e:
            logger.error(f"[VECTOR][content_strategist] Failed to save plan: {e}")
            return False

    def get_topic_ideas(self, niche: Optional[str] = None) -> list[dict]:
        """Get all topic ideas, optionally filtered by niche."""
        if niche:
            return [t for t in self._topic_ideas if niche.lower() in t.get("niche", "").lower()]
        return self._topic_ideas

    def save_trends_to_vault(self, topic: str) -> bool:
        """Save trend analysis to Obsidian vault."""
        if topic not in self._trends_cache:
            return False

        try:
            trends_dir = self._obsidian._vault / self._content_dir / "Trends"
            trends_dir.mkdir(parents=True, exist_ok=True)

            trend_file = trends_dir / f"{_safe_filename(topic, 80)}_{self._get_timestamp()[:10]}.md"
            if not trend_file.resolve().is_relative_to(trends_dir.resolve()):
                raise ValueError("trend path escapes vault trends directory")
            content = f"""# Content Trends: {topic}

Analyzed: {self._trends_cache[topic]['timestamp']}

## Analysis

{self._trends_cache[topic]['analysis']}
"""

            trend_file.write_text(content, encoding="utf-8")
            logger.info(f"[VECTOR][content_strategist] Saved trends for {topic}")
            return True

        except Exception as e:
            logger.error(f"[VECTOR][content_strategist] Failed to save trends: {e}")
            return False

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


    async def run(self, task: dict) -> dict:
        p = task.get("params") or {}
        ideas = self.get_topic_ideas(p.get("niche"))
        result = await self.analyze_trends(p.get("topic", "social media"))
        if "error" in result:
            # analyze_trends reports an LLM failure via an "error" key; don't mask it as ok.
            return {"status": "error", "error": result["error"], "ideas": ideas, "trends": result}
        return {"status": "ok", "ideas": ideas, "trends": result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    import asyncio

    async def test():
        strategist = ContentStrategist()

        topics = strategist.suggest_topics("AI Technology", 5)
        print(f"Generated {len(topics)} topics")

        if topics:
            print(f"First topic: {topics[0].get('title', 'N/A')}")

        print("✅ content_strategist.py OK")

    asyncio.run(test())
