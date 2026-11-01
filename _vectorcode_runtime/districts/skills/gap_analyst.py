"""
Module: agents/skills/gap_analyst.py
District: skills | Focus: Analyze skill gaps, suggest learning paths, prioritize gaps
"""

import sys
import os
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime
from typing import Optional


class GapAnalyst(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="GapAnalyst",
            district="skills",
            generation=1
        )
        self.capabilities = ["analysis", "analyze_gaps", "gap", "skill_gap", "prioritize_gaps", "skills", "suggest_learning_path"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.analyzed_gaps = {}
        logger.info("[VECTOR][skills] GapAnalyst ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        if os.getenv("VECTOR_SKILLS_LLM") != "1":
            return ""
        from core.inference.vectorcode_llm import chat as ollama_chat
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

    def analyze_gaps(self, required_skills: list[str], current_skills: list[str]) -> dict:
        logger.info(f"[VECTOR][skills] Analyzing skill gaps: {len(required_skills)} required, {len(current_skills)} current")
        self.add_lesson({"action": "analyze_gaps", "required": len(required_skills), "current": len(current_skills)})

        required_set = set(s.lower().strip() for s in required_skills)
        current_set = set(s.lower().strip() for s in current_skills)

        critical_gaps = []
        for skill in required_skills:
            if skill.lower().strip() not in current_set:
                critical_gaps.append({
                    "skill": skill,
                    "gap_type": "missing",
                    "urgency": "high",
                    "reason": "Core skill requirement not met",
                })

        partial_gaps = []
        for skill in required_skills:
            if skill.lower().strip() in current_set:
                partial_gaps.append({
                    "skill": skill,
                    "gap_type": "needs_improvement",
                    "urgency": "medium",
                    "reason": "Skill present but may need depth",
                })

        prompt = f"""Analyze these skill gaps for context:
Required but missing: {json.dumps([g['skill'] for g in critical_gaps], indent=2)}
Present but may need depth: {json.dumps([g['skill'] for g in partial_gaps], indent=2)}
Current skills: {current_skills}
Return JSON: {{gap_analysis: [{{skill, severity: critical/major/minor, impact_on_career: string, time_to_acquire: string}}], overall_gap_score: float}}"""
        analysis_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        computed_score = len(critical_gaps) / max(len(required_skills), 1)

        try:
            import re
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(0))
            else:
                analysis = {"gap_analysis": critical_gaps, "overall_gap_score": len(critical_gaps) / max(len(required_skills), 1)}
        except json.JSONDecodeError:
            analysis = {"gap_analysis": critical_gaps, "overall_gap_score": len(critical_gaps) / max(len(required_skills), 1)}

        gap_ids = []
        for gap in (analysis.get("gap_analysis") or critical_gaps):
            if not isinstance(gap, dict):
                continue
            gap_id = f"gap_{gap.get('skill', 'unknown').replace(' ', '_')}"
            self.analyzed_gaps[gap_id] = gap
            gap_ids.append(gap_id)

        try:
            gap_score = float(analysis.get("overall_gap_score"))
            if gap_score != gap_score:
                raise ValueError("nan")
        except (TypeError, ValueError):
            gap_score = computed_score  # was a flat 0.5 when the LLM omitted it

        result = {
            "critical_gaps": len(critical_gaps),
            "partial_gaps": len(partial_gaps),
            "gap_analysis": analysis.get("gap_analysis") or critical_gaps,
            "overall_gap_score": round(gap_score, 2),
            "gap_ids": gap_ids,
            "analyzed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="gaps_analyzed",
            content=f"Skill gap analysis: {len(critical_gaps)} critical, {len(partial_gaps)} partial gaps",
            tags=["skills", "gap_analysis"],
            context=result,
            source="GapAnalyst"
        )

        logger.info(f"[VECTOR][skills] Gap analysis: {len(critical_gaps)} critical gaps, score={result['overall_gap_score']}")
        return result

    def suggest_learning_path(self, skill_gap: dict) -> dict:
        logger.info(f"[VECTOR][skills] Suggesting learning path for: {skill_gap.get('skill', 'unknown')}")
        self.add_lesson({"action": "suggest_learning_path", "skill": skill_gap.get("skill")})

        skill_name = skill_gap.get("skill", "Unknown")
        severity = skill_gap.get("severity", "major")

        prompt = f"""Create a structured learning path for '{skill_name}' (severity: {severity}).
Consider: prerequisite skills, optimal learning sequence, resources needed, estimated time.
Return JSON: {{steps: [{{order: int, topic: string, description: string, duration_hours: int, resource_type: course/book/project}}], total_hours: int, difficulty: string}}"""
        path_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', path_text, re.DOTALL)
            if json_match:
                learning_path = json.loads(json_match.group(0))
            else:
                learning_path = {"steps": [{"order": 1, "topic": skill_name, "description": "Learn " + skill_name, "duration_hours": 20}], "total_hours": 20}
        except json.JSONDecodeError:
            learning_path = {"steps": [{"order": 1, "topic": skill_name, "description": "Learn " + skill_name, "duration_hours": 20}], "total_hours": 20}

        result = {
            "source": "llm" if path_text else "fallback",
            "skill_gap": skill_gap,
            "learning_path": learning_path.get("steps", []),
            "total_hours": learning_path.get("total_hours", 20),
            "difficulty": learning_path.get("difficulty", "intermediate"),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="learning_path_suggested",
            content=f"Suggested learning path for '{skill_name}': {learning_path.get('total_hours', 20)} hours",
            tags=["skills", "learning_path", skill_name],
            context=result,
            source="GapAnalyst"
        )

        return result

    def prioritize_gaps(self, gaps: list[dict]) -> dict:
        logger.info(f"[VECTOR][skills] Prioritizing {len(gaps)} skill gaps")
        self.add_lesson({"action": "prioritize_gaps", "count": len(gaps)})

        prompt = f"""Prioritize these skill gaps for learning:
{json.dumps(gaps, indent=2)}
Score each by: 1) Career impact (1-10), 2) Time to value, 3) Difficulty vs reward, 4) Prerequisites availability.
Return JSON: {{prioritized: [{{skill, priority_rank: int, priority_score: float, rationale: string}}]}}"""
        priority_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', priority_text, re.DOTALL)
            if json_match:
                prioritized = json.loads(json_match.group(0))
            else:
                prioritized = {"prioritized": [{"skill": g.get("skill", "unknown"), "priority_rank": i+1, "priority_score": 5.0} for i, g in enumerate(gaps)]}
        except json.JSONDecodeError:
            prioritized = {"prioritized": [{"skill": g.get("skill", "unknown"), "priority_rank": i+1, "priority_score": 5.0} for i, g in enumerate(gaps)]}

        result = {
            "source": "llm" if priority_text else "fallback",
            "total_gaps": len(gaps),
            "prioritized_gaps": prioritized.get("prioritized", []),
            "highest_priority": prioritized.get("prioritized", [{}])[0].get("skill", "unknown") if prioritized.get("prioritized") else None,
            "prioritized_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="gaps_prioritized",
            content=f"Prioritized {len(gaps)} skill gaps, top: {result['highest_priority']}",
            tags=["skills", "prioritization", "gaps"],
            context=result,
            source="GapAnalyst"
        )

        return result


    async def run(self, task: dict) -> dict:
        task = task or {}
        task_type = task.get("type", "")
        params = task.get("params") or {}

        def _as_list(v) -> list:
            # list("python") would split into characters
            return [v] if isinstance(v, (str, dict)) else list(v or [])

        try:
            if task_type == "analyze_gaps":
                required = _as_list(params.get("required_skills"))
                if not required:
                    # No requirements != "no gaps"
                    return {"status": "error", "error": "required_skills is empty", "task_type": task_type}
                result = self.analyze_gaps(
                    required_skills=required,
                    current_skills=_as_list(params.get("current_skills")),
                )
                return {"status": "ok", **result}
            if task_type == "skill_gap":
                # 2026-10-31: governor routes chat intents like "analyze my
                # skill gaps" / "competency analysis" to this exact task_type
                # (see core/city/governor.py DISTRICT_TASK_MAP + data/intent_examples.json),
                # but this agent only ever handled "analyze_gaps" -- a chat
                # question never carries that structured name, so it always
                # fell through to the "unhandled type" stub below. Same
                # pattern as science_agent.py's chemistry fix: a chat-originated
                # dispatch never carries required_skills/current_skills (nothing
                # extracts them from free text), so run the real analysis when
                # structured data IS present, otherwise answer honestly instead
                # of a dead stub.
                required = _as_list(params.get("required_skills"))
                if required:
                    result = self.analyze_gaps(
                        required_skills=required,
                        current_skills=_as_list(params.get("current_skills")),
                    )
                    return {"status": "ok", **result}
                return {
                    "status": "ok",
                    "response": (
                        "I'd need the skills a role/project requires and the skills "
                        "you currently have to run a real gap analysis -- for example "
                        "'required: Kubernetes, Go, gRPC; current: Python, Docker'. "
                        "What should I compare?"
                    ),
                    "agent": self.name,
                }
            if task_type == "prioritize_gaps":
                result = self.prioritize_gaps(_as_list(params.get("gaps")))
                return {"status": "ok", **result}
            if task_type == "suggest_learning_path":
                result = self.suggest_learning_path(dict(params.get("skill_gap") or {}))
                return {"status": "ok", **result}
        except Exception as exc:
            logger.error("[VECTOR][skills] GapAnalyst task failed: {}", exc)
            return {"status": "error", "error": str(exc), "task_type": task_type}

        return {
            "status": "error",
            "error": f"unhandled type: {task_type}",
            "supported": ["analyze_gaps", "prioritize_gaps", "suggest_learning_path"],
        }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = GapAnalyst()
    assert agent.district == "skills"

    required = ["Python", "Machine Learning", "FastAPI", "Docker", "Kubernetes", "React", "SQL"]
    current = ["Python", "JavaScript", "Git", "Linux"]

    gaps = agent.analyze_gaps(required, current)
    assert "gap_analysis" in gaps
    assert gaps["critical_gaps"] >= 3

    if gaps["gap_analysis"]:
        path = agent.suggest_learning_path(gaps["gap_analysis"][0])
        assert "learning_path" in path

    priorities = agent.prioritize_gaps(gaps["gap_analysis"])
    assert "prioritized_gaps" in priorities

    print("✅ gap_analyst.py OK")
