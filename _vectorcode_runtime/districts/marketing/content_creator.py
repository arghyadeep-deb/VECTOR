"""
Content Creator — editorial calendar, blog posts, newsletters, content repurposing.

Generates long-form content for VECTOR's presence, Arghyadeep's personal brand,
and any client content managed via the agency district.
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

_CONTENT_TYPES = ["blog_post", "whitepaper", "tutorial", "newsletter", "social_post",
                  "video_script", "case_study", "podcast_outline"]

_REPURPOSE_MAP = {
    "blog_post": ["twitter_thread", "linkedin_post", "newsletter_section", "video_script"],
    "video_script": ["blog_post", "twitter_thread", "newsletter"],
    "twitter_thread": ["blog_post", "linkedin_post"],
    "newsletter": ["linkedin_post", "blog_post"],
}

class ContentCreator(AgentBase, SkillMixin):
    """
    Multi-format content creation and repurposing specialist.
    Editorial calendars, blog posts, newsletters, content briefs.
    Augmented with: copywriting, content-strategy skill prompts.
    """

    def __init__(self):
        super().__init__(agent_id="content_creator_001", name="ContentCreator", district="marketing")
        self.capabilities = ["blog", "brief", "calendar", "content", "create", "marketing", "newsletter", "repurpose"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        self._skill_prompt = load_skill("copywriting", "content-strategy")
        from core.prompt_library import get_library as _gl
        _lib = _gl().get_for_agent("content_creator") or ""
        if _lib:
            self._skill_prompt = (self._skill_prompt + "\n\n" + _lib).strip()
        logger.info("[VECTOR][content_creator] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def generate_content_brief(self, topic: str, format: str = "blog_post") -> dict:
        """Pre-writing brief: angle, audience, key points, SEO, CTA."""
        format = format if format in _CONTENT_TYPES else "blog_post"
        word_counts = {"blog_post": 800, "whitepaper": 2500, "tutorial": 1200,
                       "newsletter": 400, "case_study": 1000, "video_script": 600}
        return {
            "topic": topic,
            "format": format,
            "angle": f"Practical guide: how a KIIT CSE student built {topic} with Python",
            "target_audience": "developers, AI enthusiasts, student builders",
            "key_points": [
                f"What is {topic} and why it matters",
                "Technical implementation details",
                "Real challenges and how they were solved",
                "Results and lessons learned",
            ],
            "seo_keywords": [topic, f"{topic} Python", f"build {topic}", f"{topic} tutorial"],
            "tone": "authentic, technical, builder mindset",
            "word_count": word_counts.get(format, 800),
            "cta": "Star the VECTOR GitHub repo / follow for more AI engineering content",
        }

    async def generate_blog_post(self, topic: str, target_audience: str = "developers",
                                  word_count: int = 800) -> str:
        """Full blog post with SEO title, intro hook, H2 sections, conclusion."""
        prompt = (
            f"Write a {word_count}-word blog post about: '{topic}'\n"
            f"Target audience: {target_audience}\n"
            f"Author: Arghyadeep Deb, KIIT CSE student building VECTOR (autonomous AI system)\n\n"
            f"Structure:\n"
            f"# [SEO-optimized title]\n\n"
            f"[Hook paragraph — problem/surprise/insight]\n\n"
            f"## [Section 1]\n[content]\n\n"
            f"## [Section 2]\n[content]\n\n"
            f"## [Section 3]\n[content]\n\n"
            f"## Key Takeaways\n- [3 bullet points]\n\n"
            f"[CTA paragraph]\n\n"
            f"Be specific, use code examples where relevant, avoid fluff."
        )
        try:
            return self._chat(prompt, timeout=40.0)
        except Exception as e:
            logger.warning("[VECTOR][content_creator] blog LLM failed: {}", e)
            return (
                f"# How I Built {topic}: A Student Developer's Journey\n\n"
                f"As a 3rd-year CSE student at KIIT, I've been building VECTOR — an autonomous AI system "
                f"that never stops running. Here's what I learned.\n\n"
                f"## The Problem\n{topic} seemed impossible at first. But breaking it down changed everything.\n\n"
                f"## The Implementation\nPython + local LLMs + SQLite = surprisingly powerful stack.\n\n"
                f"## What Worked\nSimplicity. The best solution was the one I could understand completely.\n\n"
                f"## Key Takeaways\n- Start with the simplest thing that works\n"
                f"- Local > cloud for privacy-sensitive AI\n- Ship fast, iterate faster\n\n"
                f"Check out VECTOR on GitHub. Questions? Drop a comment."
            )

    def create_editorial_calendar(self, month: str = "", content_count: int = 12) -> list[dict]:
        """Monthly content calendar with topic ideas per week."""
        if not month:
            month = datetime.datetime.now().strftime("%Y-%m")
        try:
            base = datetime.datetime.strptime(month + "-01", "%Y-%m-%d")
        except ValueError:
            base = datetime.datetime.now().replace(day=1)

        topics = [
            ("blog_post", "How I built VECTOR's Darwinian agent system"),
            ("tutorial", "Local LLMs with Ollama: complete Python guide"),
            ("newsletter", "VECTOR weekly: what shipped, what broke, what I learned"),
            ("blog_post", "Permission gateway pattern for safe AI agents"),
            ("tutorial", "SQLite FTS5 for AI memory — no vector DB needed"),
            ("case_study", "VECTOR vs GPT wrapper: architecture comparison"),
            ("blog_post", "Why HP-based agent evolution actually works"),
            ("tutorial", "Building a multi-agent orchestrator with Python"),
            ("newsletter", "VECTOR weekly: agent council voting system"),
            ("blog_post", "KIIT to AI Engineer: skills that actually matter"),
            ("tutorial", "Episodic memory for AI agents — design and implementation"),
            ("blog_post", "What I wish I knew before building an autonomous AI"),
        ]
        calendar = []
        for i, (fmt, topic) in enumerate(topics[:content_count]):
            week_num = i // 3 + 1
            post_date = (base + datetime.timedelta(days=i * 2 + (week_num - 1))).strftime("%Y-%m-%d")
            calendar.append({
                "week": week_num,
                "date": post_date,
                "format": fmt,
                "topic": topic,
                "platform": "linkedin+twitter" if fmt == "newsletter" else "blog",
                "status": "planned",
                "seo_keyword": topic.split(":")[0].strip().lower(),
            })
        return calendar

    async def write_newsletter_issue(self, theme: str, items: list[str]) -> str:
        """Structured newsletter: subject, preview, sections, CTA."""
        ts = datetime.datetime.now().strftime("%B %d, %Y")
        subject = f"🤖 VECTOR Weekly — {theme} [{ts}]"
        preview = f"What shipped this week in VECTOR AI and what you can steal for your own projects."
        body = f"# {subject}\n\n_{preview}_\n\n## This Week\n\n"
        for i, item in enumerate(items, 1):
            body += f"**{i}.** {item}\n\n"
        body += (
            f"## What I'm Building\n"
            f"VECTOR — an autonomous AI that runs 24/7, learns from every decision, "
            f"and gets smarter over time. All local, all Python.\n\n"
            f"## This Week's Insight\n"
            f"The best AI system isn't the smartest one. It's the one that never crashes "
            f"and always remembers.\n\n"
            f"---\n"
            f"[⭐ Star VECTOR on GitHub] | [Follow on LinkedIn] | [Reply to this email]\n"
        )
        return body

    async def repurpose_content(self, original: str, source_format: str, target_format: str) -> str:
        """Adapt existing content to new format."""
        prompt = (
            f"Repurpose this {source_format} into a {target_format}:\n\n"
            f"{original[:1500]}\n\n"
            f"Rules: Keep the core insight. Adapt tone and structure for {target_format}. "
            f"Don't just summarize — transform for the new medium."
        )
        try:
            return self._chat(prompt, timeout=30.0)
        except Exception as e:
            logger.warning("[VECTOR][content_creator] repurpose LLM failed: {}", e)
            return f"[Repurposed from {source_format} to {target_format}]\n\n{original[:300]}..."

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "brief")
        try:
            if task_type == "blog":
                post = await self.generate_blog_post(
                    task.get("topic", "building autonomous AI"),
                    task.get("target_audience", "developers"),
                    task.get("word_count", 800),
                )
                self.award_points(35, "blog_post_created")
                return {"status": "ok", "content": post, "format": "blog_post"}

            elif task_type == "calendar":
                calendar = self.create_editorial_calendar(
                    task.get("month", ""), task.get("content_count", 12)
                )
                self._get_memory().store(
                    event_type="editorial_calendar",
                    content=f"Editorial calendar: {len(calendar)} pieces planned",
                    tags=["marketing", "content"],
                    source="content_creator",
                )
                self.award_points(25, "calendar_created")
                return {"status": "ok", "calendar": calendar, "total_pieces": len(calendar)}

            elif task_type == "newsletter":
                nl = await self.write_newsletter_issue(
                    task.get("theme", "Weekly update"),
                    task.get("items", ["VECTOR shipped a new district", "Key architecture decision made"]),
                )
                self.award_points(25, "newsletter_created")
                return {"status": "ok", "content": nl, "format": "newsletter"}

            elif task_type == "repurpose":
                result = await self.repurpose_content(
                    task.get("original", ""), task.get("source_format", "blog_post"),
                    task.get("target_format", "twitter_thread"),
                )
                self.award_points(20, "content_repurposed")
                return {"status": "ok", "content": result,
                        "from": task.get("source_format"), "to": task.get("target_format")}

            elif task_type not in ("brief",) and (task.get("params", {}).get("query") or task.get("params", {}).get("content") or task.get("query")):
                # 2026-07-28: unmatched/free-text task_type always fell
                # through to "brief" for a hardcoded topic
                # ("building autonomous AI agents"), ignoring what was
                # actually asked — same bug class as design district's #33.
                query = task.get("params", {}).get("query") or task.get("params", {}).get("content") or task.get("query")
                return {"status": "ok", "response": await self.answer_marketing_question(query)}

            else:  # brief
                brief = self.generate_content_brief(
                    task.get("topic", "building autonomous AI agents"),
                    task.get("format", "blog_post"),
                )
                self.award_points(15, "content_brief_created")
                return {"status": "ok", "brief": brief}

        except Exception as e:
            logger.error("[VECTOR][content_creator] {}", e)
            self.deduct_points(30, "content_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = ContentCreator()
        brief = agent.generate_content_brief("Darwinian AI agents", "tutorial")
        print(f"[OK] brief: topic='{brief['topic']}' words={brief['word_count']}")
        cal = agent.create_editorial_calendar(content_count=4)
        print(f"[OK] calendar: {len(cal)} pieces, week1={cal[0]['topic'][:40]}")
        post = await agent.generate_blog_post("autonomous AI memory", word_count=200)
        print(f"[OK] blog: {len(post.split())} words generated")
        result = await agent.run({"type": "brief", "topic": "VECTOR HP system"})
        print(f"[OK] run: status={result['status']}")
        print("content_creator.py OK")

    asyncio.run(_smoke())
