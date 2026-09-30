"""
UX Researcher — user research, usability analysis, persona development, journey mapping.

Helps Arghyadeep understand how real users interact with VECTOR's outputs and
any products built via the agency district. Data-driven design insights.
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
from core.loop.context_engine import ContextEngine

class UXResearcher(AgentBase):
    """
    User research specialist. Builds personas, maps journeys, analyzes usability,
    turns qualitative feedback into actionable design recommendations.
    """

    def __init__(self):
        super().__init__(agent_id="ux_researcher_001", name="UXResearcher", district="design")
        self.capabilities = ["analyze", "design", "intermediate", "journey", "persona", "plan", "research", "ux"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info("[VECTOR][ux_researcher] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _llm(self, prompt: str, timeout: float) -> str:
        """Call the routed model with mandatory session hydration."""
        hydration = ContextEngine().session_hydration_prompt({"query": prompt})
        return chat(
            model=self._model,
            messages=[{"role": "user", "content": f"{hydration}\n\n{prompt}"}],
            timeout=timeout,
            district="design",
            domain="vision",
        )

    def build_persona(self, name: str, role: str, goals: list[str],
                      pain_points: list[str], tech_level: str = "intermediate") -> dict:
        """Structured user persona with demographics, goals, pains, behaviors."""
        return {
            "name": name,
            "role": role,
            "tech_level": tech_level,
            "goals": goals,
            "pain_points": pain_points,
            "behaviors": {
                "prefers": "documentation over videos" if tech_level == "advanced" else "tutorials",
                "uses": "daily" if "automation" in " ".join(goals).lower() else "weekly",
                "discovers_via": "GitHub" if tech_level in ("intermediate", "advanced") else "social media",
            },
            "quote": f'"{pain_points[0]} — I just want something that works."' if pain_points else "",
            "ux_implications": [
                f"Optimize for {tech_level} users — don't over-explain basics" if tech_level == "advanced"
                else "Provide progressive disclosure — simple first, advanced on demand",
                f"Address: {pain_points[0]}" if pain_points else "Validate key pain points with interviews",
            ],
        }

    def map_user_journey(self, product: str, goal: str, stages: list[str] = None) -> dict:
        """Journey map with touchpoints, emotions, pain points per stage."""
        stages = stages or ["Discover", "Onboard", "First Use", "Regular Use", "Advocate"]
        journey = []
        sentiment_curve = [3, 4, 2, 5, 7]  # default: dip at first-use complexity
        for i, stage in enumerate(stages):
            sentiment = sentiment_curve[i] if i < len(sentiment_curve) else 5
            journey.append({
                "stage": stage,
                "user_action": f"User {stage.lower()}s {product}",
                "touchpoints": [f"{stage.lower()}_page", "documentation", "community"],
                "emotion": "excited" if sentiment > 6 else "frustrated" if sentiment < 4 else "neutral",
                "sentiment_score": sentiment,
                "pain_points": [f"Unclear next step after {stage.lower()}"] if sentiment < 5 else [],
                "opportunities": [f"Improve {stage.lower()} flow clarity"] if sentiment < 5 else [],
            })
        return {
            "product": product,
            "goal": goal,
            "stages": journey,
            "biggest_drop": min(journey, key=lambda s: s["sentiment_score"])["stage"],
            "recommendations": [
                f"Focus UX investment on '{min(journey, key=lambda s: s['sentiment_score'])['stage']}' stage",
                "Add progress indicators to reduce uncertainty",
                "Implement in-context help at confusion points",
            ],
        }

    def analyze_usability_feedback(self, feedback_items: list[str]) -> dict:
        """Categorize raw feedback into usability themes with severity."""
        themes: dict[str, list[str]] = {
            "navigation": [], "performance": [], "clarity": [],
            "onboarding": [], "feature_request": [], "bug": [],
        }
        severity_keywords = {
            "critical": ["can't", "broken", "crash", "error", "fail", "impossible"],
            "high": ["confusing", "difficult", "unclear", "hard to", "slow"],
            "medium": ["would be nice", "suggest", "consider", "maybe"],
        }
        categorized = []
        for item in feedback_items:
            lower = item.lower()
            theme = "clarity"
            if any(w in lower for w in ["nav", "menu", "find", "where"]):
                theme = "navigation"
            elif any(w in lower for w in ["slow", "fast", "load", "wait"]):
                theme = "performance"
            elif any(w in lower for w in ["setup", "start", "begin", "install", "first"]):
                theme = "onboarding"
            elif any(w in lower for w in ["bug", "error", "crash", "broken"]):
                theme = "bug"
            elif any(w in lower for w in ["add", "feature", "wish", "want", "need"]):
                theme = "feature_request"
            severity = "medium"
            for sev, words in severity_keywords.items():
                if any(w in lower for w in words):
                    severity = sev
                    break
            themes[theme].append(item)
            categorized.append({"feedback": item, "theme": theme, "severity": severity})

        top_theme = max(themes, key=lambda t: len(themes[t]))
        return {
            "total_items": len(feedback_items),
            "themes": {k: len(v) for k, v in themes.items() if v},
            "top_issue_area": top_theme,
            "categorized": categorized,
            "action_priority": [k for k, v in sorted(themes.items(), key=lambda x: -len(x[1])) if v][:3],
        }

    async def generate_research_plan(self, product: str, research_questions: list[str]) -> dict:
        """LLM-generated user research plan: methods, participants, timeline."""
        prompt = (
            f"Create a lean UX research plan for '{product}'.\n"
            f"Research questions:\n" + "\n".join(f"- {q}" for q in research_questions)
            + f"\n\nReturn JSON: {{\"methods\": [{{\"name\": \"\", \"participants\": 0, "
            f"\"time_days\": 0, \"questions\": []}}], "
            f"\"total_days\": 0, \"deliverables\": [], \"success_metrics\": []}}"
        )
        try:
            response = await asyncio.to_thread(self._llm, prompt, 20.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][ux_researcher] plan LLM failed: {}", e)

        return {
            "product": product,
            "methods": [
                {"name": "5-user usability test", "participants": 5, "time_days": 5,
                 "questions": research_questions[:2]},
                {"name": "Survey (n=30)", "participants": 30, "time_days": 3,
                 "questions": research_questions[2:] if len(research_questions) > 2 else research_questions},
            ],
            "total_days": 8,
            "deliverables": ["Usability findings report", "Top 5 priority fixes", "Updated persona"],
            "success_metrics": ["Task completion rate > 80%", "SUS score > 70", "NPS > 30"],
        }

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 full-repo mechanical sweep finding): the real
        # governor dispatch shape is {"type": ..., "params": {...}} -- every
        # branch below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Capture task_type from the UNMERGED task first
        # (a nested params dict could carry its own "type" key -- see
        # districts/communications/email_agent.py's identical fix), then
        # flatten params into task once for every branch below.
        task_type = task.get("type", "persona")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "persona":
                persona = self.build_persona(
                    task.get("name", "Dev Persona"),
                    task.get("role", "Software Developer"),
                    task.get("goals", ["Automate repetitive tasks", "Build AI features faster"]),
                    task.get("pain_points", ["Setup takes too long", "Documentation is unclear"]),
                    task.get("tech_level", "intermediate"),
                )
                self.award_points(20, "persona_built")
                return {"status": "ok", "persona": persona}

            elif task_type == "journey":
                journey = self.map_user_journey(
                    task.get("product", "VECTOR"), task.get("goal", "get AI working locally"),
                    task.get("stages", None),
                )
                self.award_points(25, "journey_mapped")
                return {"status": "ok", "journey": journey}

            elif task_type == "analyze":
                result = self.analyze_usability_feedback(task.get("feedback", []))
                self.award_points(20, "feedback_analyzed")
                return {"status": "ok", "analysis": result}

            elif task_type == "plan":
                plan = await self.generate_research_plan(
                    task.get("product", "VECTOR"),
                    task.get("research_questions", ["How do users first discover VECTOR?",
                                                    "Where do users get stuck in onboarding?"]),
                )
                self._get_memory().store(
                    event_type="ux_research_plan",
                    content=f"UX research plan for {task.get('product', 'VECTOR')}",
                    tags=["design", "ux", "research"],
                    source="ux_researcher",
                )
                self.award_points(30, "research_plan_created")
                return {"status": "ok", "plan": plan}

            else:
                return {"status": "ok", "message": "UXResearcher ready. Tasks: persona, journey, analyze, plan"}

        except Exception as e:
            logger.error("[VECTOR][ux_researcher] {}", e)
            self.deduct_points(30, "ux_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = UXResearcher()
        persona = agent.build_persona("Arjun", "ML Engineer",
                                      ["Run AI agents locally", "Avoid cloud costs"],
                                      ["Complex setup", "No offline mode"], "advanced")
        print(f"[OK] persona: {persona['name']} tech={persona['tech_level']} implications={len(persona['ux_implications'])}")
        journey = agent.map_user_journey("VECTOR", "run autonomous AI tasks")
        print(f"[OK] journey: {len(journey['stages'])} stages, drop at '{journey['biggest_drop']}'")
        analysis = agent.analyze_usability_feedback([
            "Can't figure out how to start the loop",
            "Documentation unclear for Ollama setup",
            "Would be great to have a web dashboard",
        ])
        print(f"[OK] analyze: top_issue={analysis['top_issue_area']} items={analysis['total_items']}")
        result = await agent.run({"type": "plan", "product": "VECTOR dashboard"})
        print(f"[OK] run: status={result['status']}")
        print("ux_researcher.py OK")

    asyncio.run(_smoke())
