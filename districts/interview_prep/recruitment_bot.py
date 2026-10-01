"""
Recruitment Bot — helps Arghyadeep with placement prep and job applications.

Analyzes job descriptions, reviews resume for ATS optimization,
tracks applications, generates cold outreach messages, monitors
placement season at KIIT.
"""

import asyncio
import datetime
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.inference.vectorcode_llm import chat

class RecruitmentBot(AgentBase):
    """
    Placement and recruitment specialist for Arghyadeep.
    Tracks companies, analyzes JDs, reviews resumes, writes outreach.
    """

    OWNER_PROFILE = {
        "name": "Arghyadeep Deb",
        "degree": "B.Tech CSE",
        "college": "KIIT University",
        "year": "3rd Year (2023-27)",
        "skills": ["Python", "AI/ML", "FastAPI", "LangChain", "SQLite", "Docker", "Next.js"],
        "projects": ["VECTOR (personal AI system)", "VectorCode (agent framework)"],
        "target_roles": ["AI Engineer", "ML Engineer", "Backend Engineer", "Software Engineer"],
        "target_companies": ["Google", "Microsoft", "OpenAI", "Anthropic", "Startups"],
    }

    def __init__(self):
        super().__init__(agent_id="recruitment_bot_001", name="RecruitmentBot", district="interview_prep")
        self.capabilities = ["analyze_jd", "brief", "hiring", "interview", "outreach", "recruitment", "review_resume", "track"]
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        logger.info("[VECTOR][recruitment_bot] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self):
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    async def analyze_job_description(self, jd: str, company: str = "Unknown") -> dict:
        """Analyze a JD and provide fit assessment + preparation tips."""
        profile_str = (
            f"Skills: {', '.join(self.OWNER_PROFILE['skills'])}\n"
            f"Projects: {', '.join(self.OWNER_PROFILE['projects'])}\n"
            f"Target: {', '.join(self.OWNER_PROFILE['target_roles'])}"
        )
        prompt = (
            f"Analyze this job description for {company} for a KIIT CSE 3rd year student.\n\n"
            f"Student profile:\n{profile_str}\n\n"
            f"JD:\n{jd[:1500]}\n\n"
            f"Provide JSON:\n"
            f'{{"fit_score": 1-10, '
            f'"matching_skills": ["list"], '
            f'"missing_skills": ["list"], '
            f'"key_requirements": ["top 3"], '
            f'"preparation_tips": ["3 specific tips"], '
            f'"should_apply": true|false, '
            f'"resume_keywords": ["ATS keywords to include"]}}'
        )
        try:
            import json as _json, re
            response = chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=30.0)
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return _json.loads(match.group())
            logger.warning("[VECTOR][recruitment_bot] JD analysis: no JSON in model response")
            return {"error": "JD analysis failed: model returned no parseable JSON"}
        except Exception as e:
            logger.warning("[VECTOR][recruitment_bot] JD analysis failed: {}", e)
            return {"error": f"JD analysis failed: {e}"}

    async def review_resume_section(self, section: str, content: str) -> str:
        """Review a resume section and suggest ATS-optimized improvements."""
        prompt = (
            f"Review this {section} section for a KIIT CSE student targeting AI/ML/Backend roles.\n\n"
            f"Current content:\n{content}\n\n"
            f"Provide:\n1. ATS optimization score (1-10)\n2. 3 specific improvements\n3. Rewritten version\n"
            f"Focus on: quantified achievements, action verbs, technical keywords."
        )
        try:
            return chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=25.0)
        except Exception as e:
            logger.warning("[VECTOR][recruitment_bot] Resume review failed: {}", e)
            raise

    async def generate_cold_outreach(self, target_name: str, company: str, role: str) -> str:
        """Generate a personalized cold outreach message for LinkedIn/email."""
        prompt = (
            f"Write a cold outreach message for Arghyadeep Deb (KIIT CSE, 3rd year) "
            f"to {target_name} at {company} about a {role} opportunity.\n\n"
            f"VECTOR project: personal autonomous AI system built with Python, FastAPI, "
            f"LangChain, local LLMs (Ollama), Darwinian multi-agent architecture.\n\n"
            f"Keep under 150 words. Be specific, genuine, not salesy. "
            f"Mention one specific thing about {company}. End with a clear ask."
        )
        try:
            return chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=20.0)
        except Exception as e:
            logger.warning("[VECTOR][recruitment_bot] Message generation failed: {}", e)
            raise

    def track_application(self, company: str, role: str, status: str, notes: str = "") -> None:
        """Store application in memory and Obsidian tracker."""
        self._get_memory().store(
            event_type="job_application",
            content=f"Applied to {company} — {role} ({status})",
            tags=["placement", "application", status.lower()],
            context={"company": company, "role": role, "status": status, "notes": notes,
                     "date": datetime.datetime.now().isoformat()},
            source="recruitment_bot",
        )
        try:
            content = (
                f"| {datetime.datetime.now().strftime('%Y-%m-%d')} | {company} | {role} | {status} | {notes} |\n"
            )
            # Append to placement tracker
            tracker = Path(CONFIG.get("paths", {}).get("obsidian_vault",
                          str(Path.home() / "V.E.C.T.O.R Brain"))) / "Placement Tracker.md"
            if tracker.exists():
                with open(tracker, "a", encoding="utf-8") as f:
                    f.write(content)
            else:
                tracker.write_text(
                    "# Placement Tracker\n\n| Date | Company | Role | Status | Notes |\n|---|---|---|---|---|\n" + content,
                    encoding="utf-8"
                )
        except Exception as e:
            logger.debug("[VECTOR][recruitment_bot] tracker write failed: {}", e)

    async def generate_placement_brief(self) -> str:
        """Generate a placement season status brief."""
        prompt = (
            f"Generate a placement preparation brief for Arghyadeep Deb:\n"
            f"- KIIT CSE 3rd year student (2023-27)\n"
            f"- Strong in Python/AI/ML, built VECTOR autonomous AI\n"
            f"- Target: AI/ML/Backend roles at top companies\n"
            f"- Current date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"Include:\n1. Placement timeline (KIIT placement season)\n"
            f"2. Weekly preparation plan\n3. Companies to target and why\n"
            f"4. VECTOR project pitch in 30 seconds\n5. Top 3 resume improvements"
        )
        try:
            return chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=30.0)
        except Exception as e:
            logger.warning("[VECTOR][recruitment_bot] Brief generation failed: {}", e)
            raise

    async def _answer_recruitment_question(self, query: str) -> str:
        """Answer a free-text question about placement/recruitment grounded
        in the owner's real profile — never writes an Obsidian note.
        This is the fallback for anything that doesn't match a known
        task_type, following the design-district #33 fix pattern."""
        profile_summary = (
            f"Owner: {self.OWNER_PROFILE['name']}, {self.OWNER_PROFILE['degree']}, "
            f"{self.OWNER_PROFILE['college']}, {self.OWNER_PROFILE['year']}. "
            f"Skills: {', '.join(self.OWNER_PROFILE['skills'][:5])}. "
            f"Target roles: {', '.join(self.OWNER_PROFILE['target_roles'])}."
        )
        prompt = (
            f"You are VECTOR's recruitment/placement coach for Arghyadeep. "
            f"Answer the owner's question using this profile context — do not "
            f"invent data:\n\n{profile_summary}\n\n"
            f"Question: {query}\n\n"
            f"Be specific and actionable. Do not write a full placement brief "
            f"unless that's exactly what was asked for."
        )
        try:
            result = chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=25.0)
            return (result or "").strip() or "I need a bit more context to help with placement questions."
        except Exception as e:
            logger.warning(f"[VECTOR][recruitment_bot] answer failed: {e}")
            return "I ran into a problem answering that — try again in a moment."

    async def run(self, task: dict) -> dict:
        # 2026-08-06: run() always fell through to generate_placement_brief()
        # (writes an Obsidian note) for ANY unmatched task_type, ignoring
        # free-text questions entirely — same bug class as design district's #33.
        task_type = task.get("type", "")
        query = (
            (task.get("params") or {}).get("query")
            or task.get("params", {}).get("content")
            or task.get("query")
            or ""
        ).strip()
        try:
            if task_type == "analyze_jd":
                result = await self.analyze_job_description(
                    task.get("jd", "Software Engineer role at a tech company"),
                    task.get("company", "Unknown"),
                )
                if "error" in result:
                    return {"status": "error", "error": result["error"]}
                self.award_points(30, "jd_analyzed")
                return {"status": "ok", "analysis": result}

            elif task_type == "review_resume":
                review = await self.review_resume_section(
                    task.get("section", "Projects"),
                    task.get("content", "VECTOR project: autonomous AI system"),
                )
                self.award_points(35, "resume_reviewed")
                return {"status": "ok", "review": review}

            elif task_type == "outreach":
                msg = await self.generate_cold_outreach(
                    task.get("target_name", "Hiring Manager"),
                    task.get("company", "Company"),
                    task.get("role", "Software Engineer"),
                )
                self.award_points(25, "outreach_generated")
                return {"status": "ok", "message": msg}

            elif task_type == "track":
                self.track_application(
                    task.get("company", "Unknown"),
                    task.get("role", "SWE"),
                    task.get("status", "applied"),
                    task.get("notes", ""),
                )
                self.award_points(10, "application_tracked")
                return {"status": "ok", "tracked": True}

            elif task_type not in ("brief",) and query:
                # Free-text question — answer it grounded in owner profile,
                # don't silently write an Obsidian journal note.
                answer = await self._answer_recruitment_question(query)
                if answer:
                    self.award_points(15, "recruitment_question_answered")
                    return {"status": "ok", "response": answer}

            elif task_type == "brief" or not query:
                # Explicit brief request, or no query at all — safe default
                if task_type == "brief":
                    brief = await self.generate_placement_brief()
                    try:
                        self._get_obsidian().write_note("Placement", "Placement Brief", brief)
                    except Exception:
                        logger.debug("[VECTOR] suppressed exception", exc_info=True)
                    self.award_points(40, "placement_brief_generated")
                    return {"status": "ok", "brief": brief}

            # No query, no explicit brief — return status, no side effects
            return {"status": "ok", "response": "RecruitmentBot ready. Ask a placement question or use task_type='brief' for a full placement brief."}

        except Exception as e:
            logger.error("[VECTOR][recruitment_bot] {}", e)
            self.deduct_points(30, "recruitment_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = RecruitmentBot()
        analysis = await agent.analyze_job_description(
            "Looking for a Python developer with ML experience. FastAPI, Docker required. AI/ML projects preferred.",
            "TechCorp"
        )
        print(f"[OK] analyze_jd: fit={analysis.get('fit_score')} apply={analysis.get('should_apply')}")
        msg = await agent.generate_cold_outreach("Sarah Chen", "OpenAI", "AI Engineer")
        print(f"[OK] cold_outreach: {len(msg)} chars generated")
        agent.track_application("Google", "L3 SWE", "applied", "VECTOR project impressed them")
        print("[OK] track_application: stored")
        result = await agent.run({"type": "brief"})
        print(f"[OK] run: status={result['status']}")
        print("recruitment_bot.py OK")

    asyncio.run(_smoke())
