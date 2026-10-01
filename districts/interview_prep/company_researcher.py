import re
import sys
import uuid
import json
import asyncio as _asyncio
import concurrent.futures as _cf
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.obsidian_sync import ObsidianSync


def _llm(prompt: str, max_tokens: int = 1000, temperature: float = 0.6) -> str:
    from core.inference.provider_client import ProviderClient as _PC
    async def _call():
        r = await _PC().chat(
            messages=[{"role": "user", "content": prompt}],
            model="domain:research",   # glm-4.7 → gemini-2.5-pro → o4-mini → ollama
            tier="reasoning", temperature=temperature, max_tokens=max_tokens,
            caller_id="company_researcher",
        )
        return r.content
    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_asyncio.run, _call()).result(timeout=90)


class CompanyResearcher(AgentBase):
    """
    Researches companies for interview preparation,
    generates likely interview questions, and provides tips.
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "CompanyResearcher", "interview_prep")
        self.capabilities = ["company", "interview", "research"]
        if ghost:
            self.inherit_ghost(ghost)

        self._obsidian = ObsidianSync()
        self._research_cache: dict[str, dict] = {}
        self._research_dir = "Research/CompanyResearch"
        logger.info("[VECTOR][company_researcher] CompanyResearcher initialized")

    async def research_company(self, name: str) -> dict:
        """
        Research a company and gather relevant information.
        """
        name = name.strip()
        if not name:
            return {"status": "error", "message": "Company name required"}

        prompt = f"""Research the company: {name}

Provide comprehensive information including:
1. Company Overview (founded, size, headquarters, industry)
2. Mission and Values
3. Recent News and Developments (last 2 years)
4. Products/Services
5. Company Culture and Work Environment
6. Leadership Team (CEO and key executives)
7. Financial Status (if public)
8. Competitors
9. Glassdoor/Employee Reviews Summary
10. Interview Process Overview

Be specific and factual. If information is uncertain, indicate that clearly.
Use current knowledge and be thorough.
"""

        try:
            research = _llm(prompt, max_tokens=1500)

            research_data = {
                "id": str(uuid.uuid4()),
                "company": name,
                "research": research,
                "timestamp": self._get_timestamp(),
                "sections": self._parse_research_sections(research)
            }

            self._research_cache[name.lower()] = research_data
            await self._save_research(research_data)

            self.award_points(25, f"company_researched_{name}")
            logger.info(f"[VECTOR][company_researcher] Researched: {name}")

            return research_data

        except Exception as e:
            logger.error(f"[VECTOR][company_researcher] Research failed: {e}")
            return {"company": name, "error": str(e)}

    def _parse_research_sections(self, research: str) -> dict:
        """Parse research into sections."""
        sections = {}
        current_section = None
        current_content = []

        for line in research.split("\n"):
            line = line.strip()
            if not line:
                continue

            if "**" in line or line.isupper():
                if current_section:
                    sections[current_section] = "\n".join(current_content)
                current_section = line.strip("**:- ").title()
                current_content = []
            else:
                if current_section:
                    current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content)

        return sections

    async def _save_research(self, research: dict) -> bool:
        """Save research to Obsidian vault."""
        try:
            research_path = self._obsidian._vault / self._research_dir
            research_path.mkdir(parents=True, exist_ok=True)

            # CWE-22: company name is caller-supplied; keep the file inside research_path.
            safe_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", research["company"]).strip(" .") or "company"
            file_path = research_path / f"{safe_name}.md"
            if not file_path.resolve().is_relative_to(research_path.resolve()):
                logger.warning(f"[VECTOR][company_researcher] Refusing save outside research dir: {research['company']!r}")
                return False
            content = f"""# {research['company']}

Researched: {research['timestamp']}

---

{research['research']}
"""

            file_path.write_text(content, encoding="utf-8")
            return True

        except Exception as e:
            logger.warning(f"[VECTOR][company_researcher] Failed to save research: {e}")
            return False

    def get_interview_tips(self, company: str) -> list[str]:
        """
        Get interview tips specific to a company.
        """
        if company.lower() in self._research_cache:
            research = self._research_cache[company.lower()]
            return self._extract_tips_from_research(research.get("research", ""))
        return self._get_generic_tips()

    def _extract_tips_from_research(self, research: str) -> list[str]:
        """Extract tips from research data."""
        tips = []

        if "culture" in research.lower():
            tips.append("Research the company's culture before your interview")

        if "mission" in research.lower():
            tips.append("Align your answers with the company's stated mission and values")

        if "leadership" in research.lower():
            tips.append("Know about recent leadership changes or announcements")

        tips.extend(self._get_generic_tips())
        return tips[:10]

    def _get_generic_tips(self) -> list[str]:
        """Get generic interview tips."""
        return [
            "Research the company's products, services, and recent news",
            "Understand the company's mission and values",
            "Prepare specific examples using the STAR method",
            "Review the job description and match your skills",
            "Prepare thoughtful questions for the interviewer",
            "Practice active listening during the interview",
            "Follow up with a thank-you email after the interview"
        ]

    def generate_questions(self, company: str, role: str) -> list[dict]:
        """
        Generate likely interview questions for a company and role.
        """
        prompt = f"""Generate 15 likely interview questions for a {role} position at {company}.

Include:
1. Company-specific questions (based on their products/services/culture)
2. Role-specific technical questions
3. Behavioral questions related to common scenarios at tech companies
4. Questions about your fit with the company
5. Curveball questions to test thinking

For each question provide:
1. Question text
2. Why they ask it
3. What they're looking for
4. Sample strong answer outline

Format as a numbered list.
"""

        try:
            questions_text = _llm(prompt, max_tokens=1200)

            questions = self._parse_generated_questions(questions_text, company, role)

            self.award_points(20, f"questions_generated_for_{company}")
            return questions

        except Exception as e:
            logger.error(f"[VECTOR][company_researcher] Question generation failed: {e}")
            return []

    def _parse_generated_questions(self, questions_text: str, company: str, role: str) -> list[dict]:
        """Parse generated questions into structured format."""
        questions = []
        lines = questions_text.split("\n")
        current_q = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line and (line[0].isdigit() or line.startswith("-")):
                if current_q and current_q.get("question"):
                    questions.append(current_q)

                current_q = {
                    "id": str(uuid.uuid4()),
                    "company": company,
                    "role": role,
                    "question": line.lstrip("0123456789.- )").strip(),
                    "reason": "",
                    "looking_for": "",
                    "sample_answer": "",
                    "type": "general"
                }
            elif current_q:
                line_lower = line.lower()
                if "why" in line_lower:
                    current_q["reason"] = line.split(":", 1)[-1].strip()
                elif "looking" in line_lower or "want" in line_lower:
                    current_q["looking_for"] = line.split(":", 1)[-1].strip()
                elif "answer" in line_lower or "sample" in line_lower:
                    current_q["sample_answer"] = line.split(":", 1)[-1].strip()

        if current_q and current_q.get("question"):
            questions.append(current_q)

        return questions

    def get_salary_info(self, company: str, role: str) -> dict:
        """
        Provide estimated salary information for a role at a company.
        Note: Uses rough estimates, actual data may vary.
        """
        prompt = f"""Provide rough salary estimates for a {role} at {company}.

Include ranges for:
1. Entry Level
2. Mid-Level
3. Senior Level
4. Total Compensation (if applicable)

Note: Be clear these are rough estimates based on public data.
"""

        try:
            estimates = _llm(prompt, max_tokens=600, temperature=0.4)
            return {
                "status": "success",
                "company": company,
                "role": role,
                "estimates": estimates,
                "note": "These are rough estimates - verify with current market data"
            }

        except Exception as e:
            logger.error(f"[VECTOR][company_researcher] Salary info failed: {e}")
            return {"company": company, "role": role, "error": str(e)}

    def get_cached_research(self, company: str) -> Optional[dict]:
        """Get cached research for a company."""
        return self._research_cache.get(company.lower())

    def get_research_history(self) -> list[dict]:
        """Get history of researched companies."""
        return [
            {"company": name, "timestamp": data["timestamp"]}
            for name, data in self._research_cache.items()
        ]

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        company = p.get("company", "")
        if company:
            result = await self.research_company(company)
            if "error" in result:
                return {"status": "error", **result}
            return {"status": "ok", **result}
        # 2026-07-28: when params.company was absent (always true for
        # free-text chat dispatch, which never populates it), this
        # returned a bare {"status":"ok","agent":name} — worse than
        # design district's #33 stub, since it returns literally no
        # content at all instead of even a wrong one. Answer the real
        # question grounded in this agent's real capabilities instead.
        query = p.get("query") or p.get("content") or task.get("query")
        if query:
            prompt = (
                "You are VECTOR's company research assistant for interview prep. "
                "You can research_company(name) for company-specific facts, or "
                "get_interview_tips(company) for tips. Answer the owner's question "
                f"directly:\n\n{query}\n\nIf they named a specific company, say so "
                "and note they can ask you to research it."
            )
            try:
                answer = _llm(prompt, max_tokens=500, temperature=0.6)
            except Exception as e:
                logger.warning(f"[VECTOR][company_researcher] answer failed: {e}")
                answer = ""
            return {"status": "ok", "response": answer or "\n".join(self._get_generic_tips())}
        return {"status": "ok", "agent": self.name}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import asyncio

    async def test():
        researcher = CompanyResearcher()

        tips = researcher.get_interview_tips("Google")
        print(f"Got {len(tips)} interview tips")

        print("✅ company_researcher.py OK")

    asyncio.run(test())
