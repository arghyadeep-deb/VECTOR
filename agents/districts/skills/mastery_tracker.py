"""
Module: agents/districts/skills/mastery_tracker.py
District: skills | Focus: Track skill mastery levels, suggest next steps
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime
from typing import Optional


class MasteryTracker(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="MasteryTracker",
            district="skills",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.mastery_levels = {}
        self.milestones = {
            0.0: "Novice",
            0.2: "Beginner",
            0.4: "Intermediate",
            0.6: "Proficient",
            0.8: "Advanced",
            0.9: "Expert",
            1.0: "Master",
        }
        logger.info("[VECTOR][skills] MasteryTracker ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.ollama_safe import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def _get_level(self, score: float) -> str:
        sorted_milestones = sorted(self.milestones.items(), key=lambda x: x[0], reverse=True)
        for threshold, level in sorted_milestones:
            if score >= threshold:
                return level
        return "Novice"

    def track_mastery(self, skill_name: str, score: float) -> dict:
        logger.info(f"[VECTOR][skills] Tracking mastery of {skill_name}: score={score}")
        self.add_lesson({"action": "track_mastery", "skill": skill_name, "score": score})

        score = max(0.0, min(1.0, score))
        level = self._get_level(score)

        previous = self.mastery_levels.get(skill_name, {})
        previous_score = previous.get("score", 0.0)
        progress_delta = score - previous_score

        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        mem.update_skill(skill_name, score, {"tracking": "mastery", "last_update": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        mem.close()

        self.mastery_levels[skill_name] = {
            "score": score,
            "level": level,
            "progress_delta": round(progress_delta, 3),
            "previous_score": previous_score,
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "milestones_passed": [m for m, t in sorted(self.milestones.items()) if previous_score < t <= score],
        }

        result = {
            "skill_name": skill_name,
            "score": round(score, 3),
            "level": level,
            "progress_delta": round(progress_delta, 3),
            "milestones_passed": self.mastery_levels[skill_name]["milestones_passed"],
            "tracked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="mastery_tracked",
            content=f"Mastery of {skill_name} updated to {score:.3f} ({level})",
            tags=["skills", "mastery", skill_name],
            context=result,
            source="MasteryTracker"
        )

        if result["milestones_passed"]:
            logger.info(f"[VECTOR][skills] Milestone reached for {skill_name}: {result['milestones_passed']}")
        else:
            logger.info(f"[VECTOR][skills] Mastery of {skill_name}: score={score}, level={level}")

        return result

    def get_mastery_level(self, skill_name: str) -> dict:
        logger.info(f"[VECTOR][skills] Getting mastery level for: {skill_name}")

        if skill_name in self.mastery_levels:
            level_data = self.mastery_levels[skill_name]
        else:
            from core.memory.episodic import EpisodicMemory
            mem = EpisodicMemory()
            skill_data = mem.get_skill(skill_name)
            mem.close()

            if skill_data and skill_data.get("confidence"):
                score = skill_data["confidence"]
                level_data = {
                    "score": score,
                    "level": self._get_level(score),
                    "previous_score": 0,
                    "progress_delta": 0,
                    "milestones_passed": [],
                    "last_updated": skill_data.get("updated_at", datetime.datetime.now(datetime.timezone.utc).isoformat()),
                }
            else:
                level_data = {
                    "score": 0.0,
                    "level": "Not tracked",
                    "previous_score": 0,
                    "progress_delta": 0,
                    "milestones_passed": [],
                    "last_updated": None,
                }

        return {
            "skill_name": skill_name,
            **level_data,
        }

    def suggest_next_steps(self, skill_name: str) -> dict:
        logger.info(f"[VECTOR][skills] Suggesting next steps for: {skill_name}")
        self.add_lesson({"action": "suggest_next_steps", "skill": skill_name})

        if skill_name not in self.mastery_levels:
            self.get_mastery_level(skill_name)

        level_data = self.mastery_levels.get(skill_name, {})
        current_score = level_data.get("score", 0.0)
        current_level = level_data.get("level", "Novice")

        prompt = f"""Suggest concrete next steps to improve mastery of '{skill_name}'.
Current level: {current_level} (score: {current_score:.2f}/1.0)
Next milestone: {self._get_level(current_score + 0.1)} (target: {current_score + 0.1:.2f})
Provide: 1) 3 specific action items, 2) Daily/weekly practice recommendations, 3) Resource suggestions, 4) Project ideas to cement learning, 5) Signs of mastery.
Format as JSON: {{next_steps: [{{action, type: practice/project/study, estimated_hours: int}}], weekly_focus: string, projects: string[], mastery_indicators: string[]}}"""
        steps_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', steps_text, re.DOTALL)
            if json_match:
                steps_data = json.loads(json_match.group(0))
            else:
                steps_data = {"next_steps": [{"action": steps_text[:200], "type": "study", "estimated_hours": 10}]}
        except json.JSONDecodeError:
            steps_data = {"next_steps": [{"action": steps_text[:200], "type": "study", "estimated_hours": 10}]}

        result = {
            "skill_name": skill_name,
            "current_level": current_level,
            "current_score": round(current_score, 3),
            "next_steps": steps_data.get("next_steps", []),
            "weekly_focus": steps_data.get("weekly_focus", ""),
            "project_ideas": steps_data.get("projects", []),
            "mastery_indicators": steps_data.get("mastery_indicators", []),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="next_steps_suggested",
            content=f"Suggested next steps for mastering '{skill_name}'",
            tags=["skills", "mastery", "improvement", skill_name],
            context=result,
            source="MasteryTracker"
        )

        return result


    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        result = self.get_mastery_level(p.get("skill", "python"))
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = MasteryTracker()
    assert agent.district == "skills"

    t1 = agent.track_mastery("Python", 0.3)
    assert t1["level"] == "Beginner"
    assert t1["score"] == 0.3

    t2 = agent.track_mastery("Python", 0.65)
    assert t2["level"] == "Proficient"
    assert t2["progress_delta"] > 0

    t3 = agent.track_mastery("Python", 0.91)
    assert t3["level"] == "Expert"
    assert len(t3["milestones_passed"]) > 0

    level = agent.get_mastery_level("Python")
    assert "score" in level
    assert level["score"] == 0.91

    steps = agent.suggest_next_steps("Python")
    assert "next_steps" in steps
    assert "current_level" in steps

    print("✅ mastery_tracker.py OK")