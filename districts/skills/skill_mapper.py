"""
Module: agents/skills/skill_mapper.py
District: skills | Focus: Map person skills, identify gaps, track progress
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime
from typing import Optional


class SkillMapper(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="SkillMapper",
            district="skills",
            generation=1
        )
        self.capabilities = ["learn", "skill_map", "skills"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.skill_maps = {}
        logger.info("[VECTOR][skills] SkillMapper ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
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

    @staticmethod
    def _parse_json(text: str):
        import re
        m = re.search(r'\{.*\}', text or "", re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

    def map_skills(self, person_name: str) -> dict:
        logger.info(f"[VECTOR][skills] Mapping skills for: {person_name}")
        self.add_lesson({"action": "map_skills", "person": person_name})

        # KNOWN_ISSUES #21: EpisodicMemory() wraps a process-wide SINGLETON
        # sqlite connection (core.memory.episodic.get_db_connection()), not a
        # private one. Calling .close() on a local instance here used to close
        # that shared connection for every other agent/thread using episodic
        # memory at the time — any of them holding a cached .conn reference
        # (rather than re-resolving via get_temp_cursor() on every call) would
        # then fail with "Cannot operate on a closed database" until process
        # restart. Just let this local instance go out of scope; nothing needs
        # explicit closing since the connection is shared and long-lived.
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        events = mem.recall(person_name, limit=100)

        if not events:
            # No history: an LLM asked to "map skills" from nothing just invents
            # them. Report no_data instead of a fabricated skill map.
            logger.warning("[VECTOR][skills] No activity history for {}; skill map not generated", person_name)
            return {"status": "no_data", "error": "no activity history to map skills from",
                    "person_name": person_name, "skills": [], "total_skills": 0,
                    "categories": [], "skills_by_category": {}}
        content_text = " ".join([e.get("content", "") for e in events])[:2000]

        prompt = f"""Map out all skills for '{person_name}' based on their activity history:
{content_text[:1500]}
Categorize skills into: technical, soft, domain, tools. 
Rate proficiency: beginner (1-3), intermediate (4-6), advanced (7-8), expert (9-10).
Return JSON: {{skills: [{{name, category, proficiency, evidence: string[], last_practiced: string}}]}}"""
        result_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        skills_data = self._parse_json(result_text)
        if not isinstance(skills_data, dict) or not isinstance(skills_data.get("skills"), list):
            # LLM failed or returned junk: do NOT invent a canned skill at
            # proficiency 5 and cache/store it as a real map.
            logger.warning("[VECTOR][skills] Skill mapping LLM output unusable for {}", person_name)
            return {"status": "error", "error": "skill mapping failed: no usable LLM output",
                    "person_name": person_name, "skills": [], "total_skills": 0,
                    "categories": [], "skills_by_category": {}}

        categories = {}
        for s in skills_data.get("skills", []):
            cat = s.get("category", "unknown")
            categories.setdefault(cat, []).append(s)

        mapped = {
            "status": "ok",
            "person_name": person_name,
            "skills": skills_data.get("skills", []),
            "total_skills": len(skills_data.get("skills", [])),
            "categories": list(categories.keys()),
            "skills_by_category": categories,
        }

        self.skill_maps[person_name] = mapped

        self.memory.store(
            event_type="skills_mapped",
            content=f"Mapped {len(skills_data.get('skills', []))} skills for {person_name}",
            tags=["skills", "mapping", person_name],
            context=mapped,
            source="SkillMapper"
        )

        logger.info(f"[VECTOR][skills] Mapped {len(skills_data.get('skills', []))} skills for {person_name}")
        return mapped

    def suggest_skill_gaps(self, person_name: str) -> dict:
        logger.info(f"[VECTOR][skills] Suggesting skill gaps for: {person_name}")
        self.add_lesson({"action": "suggest_skill_gaps", "person": person_name})

        if person_name not in self.skill_maps:
            self.map_skills(person_name)

        mapped = self.skill_maps.get(person_name, {})
        current_skills = [s["name"] for s in mapped.get("skills", []) if isinstance(s, dict) and s.get("name")]
        if not current_skills:
            # Gaps against an empty/failed skill map are meaningless.
            return {"status": "error", "error": "no mapped skills available to compute gaps against",
                    "person_name": person_name, "current_skills": [], "skill_gaps": [], "gaps_count": 0}

        prompt = f"""For person with these current skills: {current_skills}
Suggest missing skills that would be valuable for career growth, tech industry trends, and productivity.
Focus on: in-demand technical skills, complementary soft skills, emerging technologies.
Return JSON: {{gaps: [{{skill_name, category, importance: 1-10, reason: string, resource: string}}]}}"""
        gaps_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        gaps_data = self._parse_json(gaps_text)
        if not isinstance(gaps_data, dict) or not isinstance(gaps_data.get("gaps"), list):
            logger.warning("[VECTOR][skills] Skill-gap LLM output unusable for {}", person_name)
            return {"status": "error", "error": "skill gap suggestion failed: no usable LLM output",
                    "person_name": person_name, "current_skills": current_skills,
                    "skill_gaps": [], "gaps_count": 0}

        result = {
            "status": "ok",
            "person_name": person_name,
            "current_skills": current_skills,
            "skill_gaps": gaps_data.get("gaps", []),
            "gaps_count": len(gaps_data.get("gaps", [])),
        }

        self.memory.store(
            event_type="skill_gaps_suggested",
            content=f"Suggested {len(gaps_data.get('gaps', []))} skill gaps for {person_name}",
            tags=["skills", "gaps", person_name],
            context=result,
            source="SkillMapper"
        )

        return result

    def track_skill_progress(self, skill_name: str) -> dict:
        logger.info(f"[VECTOR][skills] Tracking skill progress: {skill_name}")
        self.add_lesson({"action": "track_skill_progress", "skill": skill_name})

        # KNOWN_ISSUES #21 — see map_skills() above; don't close the shared
        # singleton connection from a local EpisodicMemory instance.
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        skill_data = mem.get_skill(skill_name)

        if not skill_data:
            # Never seen: don't fabricate a 0.3 "Beginner" row in the DB.
            return {"skill_name": skill_name, "confidence": 0.0, "level": "Not tracked",
                    "evidence": "No tracking data for this skill",
                    "tracked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}

        evidence_text = skill_data.get("evidence", "") or ""
        confidence = skill_data.get("confidence")
        if confidence is None:
            confidence = 0.0

        level = "Novice" if confidence < 0.3 else "Beginner" if confidence < 0.5 else "Intermediate" if confidence < 0.7 else "Advanced" if confidence < 0.85 else "Expert"

        result = {
            "skill_name": skill_name,
            "confidence": round(confidence, 2),
            "level": level,
            "evidence": evidence_text[:200] if evidence_text else "New skill, tracking started",
            "tracked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="skill_progress_tracked",
            content=f"Tracking progress for {skill_name}: level={level}, confidence={confidence:.2f}",
            tags=["skills", "progress", skill_name],
            context=result,
            source="SkillMapper"
        )

        return result


    async def run(self, task: dict) -> dict:
        p = (task or {}).get("params") or {}
        result = self.track_skill_progress(p.get("skill", "python"))
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = SkillMapper()
    assert agent.district == "skills"

    mapped = agent.map_skills("Arghyadeep")
    assert "skills" in mapped
    assert "total_skills" in mapped

    gaps = agent.suggest_skill_gaps("Arghyadeep")
    assert "skill_gaps" in gaps

    progress = agent.track_skill_progress("Python")
    assert "level" in progress
    assert "confidence" in progress

    print("✅ skill_mapper.py OK")