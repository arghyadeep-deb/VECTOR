"""
Proposal Strategist — proposal writing, win themes, ROI calculators, exec summaries.

Creates compelling project proposals for Arghyadeep's agency and freelance work.
Transforms requirements into persuasive win narratives with clear value delivery.
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

_PROPOSAL_SECTIONS = [
    "executive_summary", "problem_statement", "proposed_solution",
    "technical_approach", "timeline", "pricing", "team", "next_steps",
]

class ProposalStrategist(AgentBase):
    """
    Proposal writing and win strategy specialist.
    Creates technical project proposals, SOWs, ROI calculators, exec summaries.
    """

    def __init__(self):
        super().__init__(agent_id="proposal_strategist_001",
                         name="ProposalStrategist", district="agency")
        self.capabilities = ["agency", "proposal", "roi", "sales", "structure"]
        self._memory: EpisodicMemory | None = None
        self._context = ContextEngine()
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        logger.info("[VECTOR][proposal] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def calculate_roi(self, current_cost_monthly: float, solution_cost: float,
                      time_saved_hours_monthly: float, hourly_rate: float = 2000.0) -> dict:
        """ROI calculator: monthly savings vs project investment."""
        monthly_savings = time_saved_hours_monthly * hourly_rate
        payback_months = solution_cost / monthly_savings if monthly_savings > 0 else float("inf")
        roi_12m = ((monthly_savings * 12) - solution_cost) / solution_cost * 100 if solution_cost > 0 else 0
        return {
            "solution_investment": solution_cost,
            "monthly_time_saved_hours": time_saved_hours_monthly,
            "monthly_savings_inr": round(monthly_savings, 2),
            "current_monthly_cost": current_cost_monthly,
            "payback_months": round(payback_months, 1) if payback_months != float("inf") else "Never (no savings)",
            "12_month_roi_pct": round(roi_12m, 1),
            "3_year_savings": round(monthly_savings * 36 - solution_cost, 2),
            "verdict": "Strong ROI" if roi_12m > 100 else "Moderate ROI" if roi_12m > 50 else "Low ROI — validate",
        }

    def build_proposal_structure(self, project_name: str, client: str,
                                  problem: str, solution: str, timeline_weeks: int,
                                  budget: float) -> dict:
        """Build structured proposal outline."""
        ts = datetime.datetime.now().strftime("%B %d, %Y")
        return {
            "metadata": {
                "project": project_name,
                "client": client,
                "prepared_by": "Arghyadeep Deb",
                "date": ts,
                "version": "1.0",
            },
            "executive_summary": (
                f"Proposal to build {project_name} for {client}. "
                f"Addressing: {problem[:100]}. "
                f"Delivered in {timeline_weeks} weeks for ₹{budget:,.0f}."
            ),
            "problem_statement": problem,
            "proposed_solution": solution,
            "technical_approach": {
                "stack": ["Python", "FastAPI", "LangChain/LangGraph", "SQLite/PostgreSQL", "Docker"],
                "architecture": "Modular, API-first design with clear separation of concerns",
                "quality": "Unit + integration tests, CI/CD pipeline, documentation included",
            },
            "timeline": {
                "total_weeks": timeline_weeks,
                "phases": [
                    {"phase": "Discovery & Architecture", "weeks": max(1, timeline_weeks // 5)},
                    {"phase": "Core Development", "weeks": timeline_weeks // 2},
                    {"phase": "Testing & QA", "weeks": timeline_weeks // 5},
                    {"phase": "Deployment & Handover", "weeks": max(1, timeline_weeks // 5)},
                ],
            },
            "investment": {
                "total": budget,
                "payment_structure": "40% upfront, 40% at milestone, 20% on delivery",
                "currency": "INR",
                "includes": ["Source code", "Documentation", "30-day post-launch support", "Knowledge transfer"],
            },
            "next_steps": [
                "Review and sign proposal",
                "Initial payment and project kickoff call",
                "Start Week 1: Discovery and architecture review",
            ],
        }

    async def write_executive_summary(self, problem: str, solution: str,
                                       roi_data: dict | None = None) -> str:
        """LLM-generated executive summary — the most-read section."""
        roi_str = f"ROI: {roi_data['12_month_roi_pct']}% in 12 months" if roi_data else ""
        prompt = (
            f"Write a compelling 150-word executive summary for a technical proposal.\n"
            f"Problem: {problem}\nSolution: {solution}\n{roi_str}\n"
            f"Author: Arghyadeep Deb, Python AI developer (KIIT CSE)\n\n"
            f"Structure: [Hook sentence]. [Problem statement]. [Our solution]. [Expected outcome + ROI]. "
            f"[Why us — 1 sentence]. Be specific, avoid buzzwords."
        )
        try:
            from core.prompt_library import get_library as _gl
            hydration = self._context.session_hydration_prompt({"task": "write_executive_summary"})
            _sys = _gl().get_for_agent("proposal_strategist") or ""
            _msgs = [{"role": "system", "content": hydration}]
            if _sys:
                _msgs.append({"role": "system", "content": _sys})
            _msgs.append({"role": "user", "content": prompt})
            return chat(model=self._model, messages=_msgs, timeout=20.0)
        except Exception as e:
            logger.warning("[VECTOR][proposal] exec summary LLM failed: {}", e)
            roi_sentence = f" Expected {roi_data['12_month_roi_pct']:.0f}% ROI in 12 months." if roi_data else ""
            return (
                f"{problem[:80]} — this is costing your team time and money every month. "
                f"We propose to {solution[:80]}, delivered in a modular Python architecture "
                f"with full documentation and 30-day support.{roi_sentence} "
                f"Built by Arghyadeep Deb, who has hands-on experience building autonomous AI systems "
                f"with exactly this stack. Next step: 30-minute discovery call."
            )

    async def generate_full_proposal(self, project_name: str, client: str,
                                      problem: str, solution: str,
                                      timeline_weeks: int, budget: float) -> str:
        """Generate complete markdown proposal document."""
        structure = self.build_proposal_structure(
            project_name, client, problem, solution, timeline_weeks, budget
        )
        exec_summary = await self.write_executive_summary(problem, solution)
        ts = structure["metadata"]["date"]
        doc = (
            f"# {project_name}\n**Proposal for {client}** | {ts} | Prepared by Arghyadeep Deb\n\n"
            f"---\n\n"
            f"## Executive Summary\n{exec_summary}\n\n"
            f"## Problem Statement\n{problem}\n\n"
            f"## Proposed Solution\n{solution}\n\n"
            f"## Technical Approach\n"
            f"**Stack:** {', '.join(structure['technical_approach']['stack'])}\n\n"
            f"**Architecture:** {structure['technical_approach']['architecture']}\n\n"
            f"**Quality:** {structure['technical_approach']['quality']}\n\n"
            f"## Project Timeline ({timeline_weeks} weeks)\n"
        )
        for phase in structure["timeline"]["phases"]:
            doc += f"- **{phase['phase']}**: {phase['weeks']} week(s)\n"
        doc += (
            f"\n## Investment\n"
            f"**Total:** ₹{budget:,.0f}\n\n"
            f"**Payment structure:** {structure['investment']['payment_structure']}\n\n"
            f"**Includes:** {', '.join(structure['investment']['includes'])}\n\n"
            f"## Next Steps\n"
        )
        for step in structure["next_steps"]:
            doc += f"1. {step}\n"
        return doc

    async def answer_proposal_question(self, query: str) -> str:
        """Answer a free-text question about VECTOR's proposal/win-strategy
        process, instead of always generating a fully hardcoded fake
        proposal for a nonexistent project/client regardless of what was
        actually asked."""
        prompt = (
            "You are VECTOR's ProposalStrategist in the agency district — "
            "you write project proposals, win themes, ROI calculators, and "
            "exec summaries for Arghyadeep's AI/ML development agency. "
            "Answer the owner's question directly and concretely. Do not "
            "invent a fake client, project, or proposal unless the "
            f"question actually asks for one.\n\nQuestion: {query}"
        )
        try:
            hydration = self._context.session_hydration_prompt({"task": "answer_proposal_question"})
            result = chat(model=self._model, messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ], timeout=20.0)
            return (result or "").strip()
        except Exception as e:
            logger.warning("[VECTOR][proposal] answer_proposal_question failed: {}", e)
            return ""

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "proposal")
        # Governor dispatch nests arguments under task["params"]; accept both shapes
        # (previously params were ignored and silent defaults were used).
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "roi":
                result = self.calculate_roi(
                    task.get("current_cost_monthly", 0),
                    task.get("solution_cost", 100000),
                    task.get("time_saved_hours_monthly", 20),
                    task.get("hourly_rate", 2000.0),
                )
                self.award_points(15, "roi_calculated")
                return {"status": "ok", "roi": result}

            elif task_type == "structure":
                result = self.build_proposal_structure(
                    task.get("project_name", "AI Automation Project"),
                    task.get("client", "Client"),
                    task.get("problem", "Manual process taking too long"),
                    task.get("solution", "Automated AI pipeline"),
                    task.get("timeline_weeks", 8),
                    task.get("budget", 150000),
                )
                self.award_points(20, "proposal_structured")
                return {"status": "ok", "structure": result}

            else:  # full proposal, or an unmatched task_type carrying a free-text question
                # KNOWN_ISSUES bug pattern (same shape as governance's
                # product_manager fix): a conversational question with no
                # real "project_name" used to still get a fully fabricated
                # proposal for a made-up "AI Automation Project"/"Client"
                # instead of an answer.
                query = (
                    task.get("query")
                    or task.get("text")
                    or ""
                ).strip()
                if query and not task.get("project_name"):
                    answer = await self.answer_proposal_question(query)
                    if answer:
                        self._get_memory().store(
                            event_type="proposal_question_answered",
                            content=f"ProposalStrategist answered: {query[:80]}",
                            tags=["agency", "proposal"],
                            source="proposal_strategist",
                        )
                        self.award_points(15, "proposal_question_answered")
                        return {"status": "ok", "response": answer}
                    # The LLM failed: do NOT fall through and fabricate a default
                    # "AI Automation Project" proposal as the answer to a question.
                    return {"status": "error", "error": "could not answer proposal question (LLM unavailable)"}

                doc = await self.generate_full_proposal(
                    task.get("project_name", "AI Automation Project"),
                    task.get("client", "Client"),
                    task.get("problem", "Manual processes consuming 40+ hours/month"),
                    task.get("solution", "Python AI automation pipeline with monitoring dashboard"),
                    task.get("timeline_weeks", 8),
                    task.get("budget", 150000),
                )
                self._get_memory().store(
                    event_type="proposal_generated",
                    content=f"Proposal for {task.get('client', 'client')}: {task.get('project_name', 'project')}",
                    tags=["agency", "proposal"],
                    source="proposal_strategist",
                )
                self.award_points(40, "proposal_generated")
                return {"status": "ok", "proposal": doc}

        except Exception as e:
            logger.error("[VECTOR][proposal] {}", e)
            self.deduct_points(30, "proposal_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = ProposalStrategist()
        roi = agent.calculate_roi(current_cost_monthly=50000, solution_cost=120000,
                                   time_saved_hours_monthly=30)
        print(f"[OK] roi: payback={roi['payback_months']}m roi_12m={roi['12_month_roi_pct']}% verdict={roi['verdict']}")
        struct = agent.build_proposal_structure("AI Chatbot", "StartupCo",
                                                 "Support team overwhelmed", "LLM-powered support bot",
                                                 6, 80000)
        print(f"[OK] structure: phases={len(struct['timeline']['phases'])} sections={len(struct)}")
        result = await agent.run({"type": "proposal", "client": "TechCo",
                                   "project_name": "AI Pipeline", "budget": 100000, "timeline_weeks": 8})
        print(f"[OK] run: status={result['status']} doc_len={len(result.get('proposal',''))}")
        print("proposal_strategist.py OK")

    asyncio.run(_smoke())
