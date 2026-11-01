"""
Social Media Strategist — LinkedIn, Twitter/X, GitHub presence strategy.

Builds thought leadership for Arghyadeep's VECTOR project, AI/ML content,
and personal brand as a KIIT CSE student targeting AI/ML/Backend roles.
"""

import asyncio
import datetime
import json
import re

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat
from districts.marketing._skill_loader import load_skill, SkillMixin

_OWNER = {
    "name": "Arghyadeep Deb",
    "platforms": {"linkedin": "Arghyadeep Deb", "twitter": "arghyadeep_deb", "github": "arghyadeep-deb"},
    "content_pillars": [
        "VECTOR AI project updates",
        "Python / AI / ML engineering",
        "Student to engineer journey",
        "Open source contributions",
        "AI agent architecture insights",
    ],
    "tone": "authentic, technical but accessible, builder mindset",
}

class SocialMediaStrategist(AgentBase, SkillMixin):
    """
    Cross-platform social media strategy and content generation.
    LinkedIn posts, Twitter threads, weekly content calendars, GitHub README sections.
    Augmented with: social, content-strategy, copywriting skill prompts.
    """

    def __init__(self):
        super().__init__(agent_id="social_media_strategist_001",
                         name="SocialMediaStrategist", district="marketing")
        self.capabilities = ["analyze", "calendar", "linkedin", "marketing", "social", "social_media", "twitter_thread"]
        self._memory: EpisodicMemory | None = None
        self._skill_prompt = load_skill("social", "content-strategy", "copywriting")
        from core.prompt_library import get_library as _gl
        _lib = _gl().get_for_agent("social_media_strategist") or ""
        if _lib:
            self._skill_prompt = (self._skill_prompt + "\n\n" + _lib).strip()
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        logger.info("[VECTOR][social] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    async def generate_linkedin_post(self, topic: str, tone: str = "professional") -> str:
        """LinkedIn post with hook, body, CTA, hashtags."""
        prompt = (
            f"Write a LinkedIn post for {_OWNER['name']} (KIIT CSE student, building VECTOR AI).\n"
            f"Topic: {topic}\nTone: {tone}\n\n"
            f"Format:\n"
            f"[Hook — 1 punchy line that stops the scroll]\n\n"
            f"[Body — 3-5 short paragraphs, one idea each, use line breaks]\n\n"
            f"[CTA — one specific question or action]\n\n"
            f"[5 relevant hashtags]\n\n"
            f"Keep under 1300 characters. Be genuine, not salesy."
        )
        try:
            return self._chat(prompt, timeout=25.0)
        except Exception as e:
            logger.warning("[VECTOR][social] LinkedIn LLM failed: {}", e)
            return (
                f"Built something new: {topic}\n\n"
                f"As a 3rd-year CSE student at KIIT, I'm working on VECTOR — an autonomous AI system that learns and improves itself.\n\n"
                f"Here's what I learned building it:\n• Local LLMs > cloud APIs for privacy\n• HP-based agent evolution actually works\n• The loop never stops — resilience is everything\n\n"
                f"What's the hardest thing you've built as a student?\n\n"
                f"#AI #Python #MachineLearning #StudentDeveloper #OpenSource"
            )

    async def generate_twitter_thread(self, topic: str, tweet_count: int = 5) -> list[str]:
        """Numbered Twitter thread, each tweet ≤280 chars."""
        prompt = (
            f"Write a {tweet_count}-tweet Twitter/X thread for: '{topic}'\n"
            f"Author: {_OWNER['name']}, KIIT CSE student building VECTOR AI.\n"
            f"Rules: Tweet 1 = strong hook. Last tweet = CTA/follow. Each ≤280 chars. Number each tweet.\n"
            f"Return as JSON array of strings: [\"tweet1\", \"tweet2\", ...]"
        )
        try:
            response = self._chat(prompt, timeout=25.0)
            match = re.search(r"\[.*\]", response, re.DOTALL)
            if match:
                tweets = json.loads(match.group())
                return [t[:280] for t in tweets[:tweet_count]]
        except Exception as e:
            logger.warning("[VECTOR][social] Twitter LLM failed: {}", e)

        return [
            f"1/ {topic} — here's what I learned building VECTOR AI 🧵",
            f"2/ Started with a simple idea: what if your AI actually remembered context between sessions?",
            f"3/ Built episodic memory with SQLite FTS5. Now VECTOR recalls events, learns from outcomes.",
            f"4/ The darwinian HP system was the game changer. Agents that perform well survive. Others die.",
            f"5/ Full thread on GitHub. If you're building autonomous AI, let's connect. What's your stack?",
        ][:tweet_count]

    def plan_content_calendar(self, week_start: str = "", posts_per_week: int = 5) -> list[dict]:
        """Weekly content calendar: [{day, platform, content_pillar, topic, format}]."""
        if not week_start:
            week_start = datetime.datetime.now().strftime("%Y-%m-%d")
        try:
            start = datetime.datetime.strptime(week_start, "%Y-%m-%d")
        except ValueError:
            start = datetime.datetime.now()

        schedule = [
            {"day_offset": 0, "platform": "linkedin", "pillar": _OWNER["content_pillars"][0],
             "format": "text_post", "topic": "VECTOR weekly update — what shipped"},
            {"day_offset": 1, "platform": "twitter", "pillar": _OWNER["content_pillars"][1],
             "format": "thread", "topic": "Python AI tip of the week"},
            {"day_offset": 2, "platform": "github", "pillar": _OWNER["content_pillars"][3],
             "format": "readme_update", "topic": "Document a new VECTOR feature"},
            {"day_offset": 3, "platform": "linkedin", "pillar": _OWNER["content_pillars"][2],
             "format": "story_post", "topic": "Lesson learned as a student builder"},
            {"day_offset": 4, "platform": "twitter", "pillar": _OWNER["content_pillars"][4],
             "format": "single_tweet", "topic": "AI agent architecture insight"},
        ]
        calendar = []
        for item in schedule[:posts_per_week]:
            date = (start + datetime.timedelta(days=item["day_offset"])).strftime("%Y-%m-%d")
            calendar.append({
                "date": date,
                "platform": item["platform"],
                "content_pillar": item["pillar"],
                "topic": item["topic"],
                "format": item["format"],
                "status": "planned",
            })
        return calendar

    async def analyze_post_performance(self, post_text: str, platform: str, metrics: dict) -> dict:
        """LLM analysis of what worked based on text + performance metrics."""
        metrics_str = ", ".join(f"{k}={v}" for k, v in metrics.items())
        prompt = (
            f"Analyze this {platform} post performance:\n\n"
            f"Post: {post_text[:500]}\n"
            f"Metrics: {metrics_str}\n\n"
            f"Return JSON: {{\"what_worked\": [], \"what_to_improve\": [], "
            f"\"score\": 1-10, \"best_time_to_repost\": \"day/time\"}}"
        )
        try:
            response = self._chat(prompt, timeout=20.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][social] analyze LLM failed: {}", e)

        return {
            "what_worked": ["Clear hook", "Authentic voice"],
            "what_to_improve": ["Add more specific numbers", "End with stronger CTA"],
            "score": 6,
            "best_time_to_repost": "Tuesday 9AM IST",
        }

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "calendar")
        try:
            if task_type == "linkedin":
                post = await self.generate_linkedin_post(
                    task.get("topic", "Building an autonomous AI system"),
                    task.get("tone", "professional"),
                )
                self.award_points(20, "linkedin_post_created")
                return {"status": "ok", "post": post, "platform": "linkedin"}

            elif task_type == "twitter_thread":
                tweets = await self.generate_twitter_thread(
                    task.get("topic", "AI agent engineering"),
                    task.get("tweet_count", 5),
                )
                self.award_points(25, "twitter_thread_created")
                return {"status": "ok", "tweets": tweets, "count": len(tweets)}

            elif task_type == "analyze":
                result = await self.analyze_post_performance(
                    task.get("post_text", ""), task.get("platform", "linkedin"),
                    task.get("metrics", {}),
                )
                self.award_points(15, "post_analyzed")
                return {"status": "ok", "analysis": result}

            elif task_type not in ("calendar",) and (task.get("params", {}).get("query") or task.get("params", {}).get("content") or task.get("query")):
                # 2026-07-28: unmatched/free-text task_type always fell
                # through to "calendar" — a fixed weekly schedule with no
                # LLM even involved, ignoring what was actually asked —
                # same bug class as design district's #33.
                query = task.get("params", {}).get("query") or task.get("params", {}).get("content") or task.get("query")
                return {"status": "ok", "response": await self.answer_marketing_question(query)}

            else:  # calendar
                calendar = self.plan_content_calendar(
                    task.get("week_start", ""), task.get("posts_per_week", 5)
                )
                self._get_memory().store(
                    event_type="content_calendar",
                    content=f"Content calendar: {len(calendar)} posts planned",
                    tags=["marketing", "social_media"],
                    source="social_media_strategist",
                )
                self.award_points(20, "calendar_planned")
                return {"status": "ok", "calendar": calendar, "posts_planned": len(calendar)}

        except Exception as e:
            logger.error("[VECTOR][social] {}", e)
            self.deduct_points(30, "social_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = SocialMediaStrategist()
        calendar = agent.plan_content_calendar(posts_per_week=5)
        print(f"[OK] calendar: {len(calendar)} posts planned for week")
        post = await agent.generate_linkedin_post("Building VECTOR — a self-improving AI")
        print(f"[OK] linkedin: {len(post)} chars generated")
        tweets = await agent.generate_twitter_thread("Darwinian AI agents", tweet_count=3)
        print(f"[OK] twitter: {len(tweets)} tweets generated")
        result = await agent.run({"type": "calendar"})
        print(f"[OK] run: status={result['status']} posts={result.get('posts_planned')}")
        print("social_media_strategist.py OK")

    asyncio.run(_smoke())
