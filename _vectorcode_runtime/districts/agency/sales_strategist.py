"""
Sales Strategist — outbound prospecting, pipeline management, deal coaching.

Helps Arghyadeep's agency find clients for AI/ML/Backend projects.
Combines outbound-strategist + sales-coach + pipeline-analyst from agency-agents.
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

_ICP = {
    "industry": ["SaaS", "AI/ML startups", "tech companies", "developer tools"],
    "company_size": "5-50 employees",
    "signals": ["recently funded", "hiring AI engineers", "post about automation", "building LLM products"],
    "pain_points": ["need AI features fast", "no in-house ML team", "want local LLM integration"],
    "offer": "Python AI/ML development, FastAPI backends, LangChain/LangGraph agents, autonomous AI systems",
}

class SalesStrategist(AgentBase):
    """
    Outbound prospecting, ICE-scored pipeline, deal strategy, outreach sequences.
    For Arghyadeep's agency acquiring AI/ML development clients.
    """

    def __init__(self):
        super().__init__(agent_id="sales_strategist_001", name="SalesStrategist", district="agency")
        self.capabilities = ["agency", "outbound", "outreach", "pipeline", "qualify", "sales"]
        self._memory: EpisodicMemory | None = None
        self._context = ContextEngine()
        self._model = CONFIG.get("models", {}).get("focus", "vector-focus")
        logger.info("[VECTOR][sales] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def qualify_lead(self, company: str, signals: list[str], budget_hint: str = "") -> dict:
        """BANT + ICP scoring for a prospect."""
        icp_match = sum(
            1 for signal in signals
            if any(kw.lower() in signal.lower() for kw in _ICP["signals"])
        )
        icp_score = min(10, icp_match * 2 + (3 if budget_hint else 0))
        budget_map = {"low": 2, "medium": 5, "high": 8, "unknown": 3}
        budget_score = budget_map.get(budget_hint.lower(), 3)

        total = (icp_score * 0.6 + budget_score * 0.4)
        tier = "A" if total >= 7 else "B" if total >= 4 else "C"
        return {
            "company": company,
            "icp_score": icp_score,
            "budget_score": budget_score,
            "total_score": round(total, 1),
            "tier": tier,
            "matched_signals": [s for s in signals if any(kw.lower() in s.lower() for kw in _ICP["signals"])],
            "recommended_action": {
                "A": "Priority outreach — personalize deeply, fast follow-up",
                "B": "Standard sequence — semi-personalized, 5-touch",
                "C": "Low priority — add to newsletter, revisit in 90 days",
            }[tier],
        }

    def analyze_pipeline(self, deals: list[dict]) -> dict:
        """Stage conversion, velocity, weighted pipeline, at-risk deals."""
        if not deals:
            return {"error": "No deals to analyze"}

        stage_counts: dict[str, int] = {}
        weighted_total = 0.0
        at_risk = []
        unparseable = []
        stage_probabilities = {
            "prospecting": 0.1, "qualified": 0.25, "proposal": 0.5,
            "negotiation": 0.75, "closed_won": 1.0, "closed_lost": 0.0,
        }
        for deal in deals:
            stage = deal.get("stage", "prospecting").lower()
            value = deal.get("value", 0)
            prob = stage_probabilities.get(stage, 0.1)
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
            weighted_total += value * prob

            # Flag deals stale > 14 days in same stage
            last_updated = deal.get("last_updated", "")
            if last_updated:
                try:
                    last_dt = datetime.datetime.fromisoformat(str(last_updated))
                    now = datetime.datetime.now(last_dt.tzinfo)  # tz-aware stamps ("...Z") must not crash the subtraction
                    if (now - last_dt).days > 14:
                        at_risk.append(deal.get("name", "Unknown deal"))
                except ValueError:
                    # Staleness unknown -- must not be reported as "healthy".
                    unparseable.append(deal.get("name", "Unknown deal"))
                    logger.warning("[VECTOR][sales] unparseable last_updated {!r} on deal {!r}", last_updated, deal.get("name"))

        total_value = sum(d.get("value", 0) for d in deals)
        return {
            "total_deals": len(deals),
            "total_pipeline_value": round(total_value, 2),
            "weighted_pipeline": round(weighted_total, 2),
            "stage_distribution": stage_counts,
            "at_risk_deals": at_risk,
            "avg_deal_value": round(total_value / len(deals), 2) if deals else 0,
            "unparseable_dates": unparseable,
            "health": (
                f"{len(at_risk)} deals need attention" if at_risk
                else f"unknown: {len(unparseable)} deals have unparseable last_updated" if unparseable
                else "healthy"
            ),
        }

    async def write_outreach(self, prospect_name: str, company: str,
                              trigger: str, role: str = "Founder") -> str:
        """Generate personalized cold outreach (email/LinkedIn)."""
        prompt = (
            f"Write a cold outreach message from Arghyadeep Deb (KIIT CSE student, AI/Python developer)\n"
            f"to {prospect_name} ({role} at {company}).\n"
            f"Trigger/signal: {trigger}\n"
            f"Offer: Python AI/ML development, autonomous AI systems, FastAPI + LangChain.\n"
            f"Rules: Under 100 words. Specific to their signal. No generic pitches. "
            f"One specific observation about their company. Clear ask at the end."
        )
        try:
            from core.prompt_library import get_library as _gl
            hydration = self._context.session_hydration_prompt({"task": "outreach"})
            _sys = _gl().get_for_agent("sales_strategist") or ""
            _msgs = [{"role": "system", "content": hydration}]
            if _sys:
                _msgs.append({"role": "system", "content": _sys})
            _msgs.append({"role": "user", "content": prompt})
            return chat(model=self._model, messages=_msgs, timeout=20.0)
        except Exception as e:
            logger.warning("[VECTOR][sales] outreach LLM failed: {}", e)
            return (
                f"Hi {prospect_name},\n\n"
                f"Noticed {company} {trigger.lower()} — exactly the kind of challenge "
                f"I help early-stage teams solve with Python AI systems.\n\n"
                f"I'm Arghyadeep, a KIIT CSE student who built VECTOR — an autonomous AI "
                f"running 25+ specialized agents locally. I take on AI/ML development projects.\n\n"
                f"Worth a 15-min call to see if I can help?\n\nArghyadeep"
            )

    async def answer_sales_question(self, query: str) -> str:
        """Answer a free-text/unmatched-task_type question grounded in the
        agency's real ICP, instead of always dumping the raw ICP dict
        regardless of what was actually asked (KNOWN_ISSUES bug pattern —
        'dumps an unrelated hardcoded default')."""
        context = (
            f"Target ICP: {', '.join(_ICP['industry'])}, {_ICP['company_size']}. "
            f"Signals: {', '.join(_ICP['signals'])}. "
            f"Offer: {_ICP['offer']}."
        )
        prompt = (
            "You are VECTOR's SalesStrategist in the agency district — "
            "you handle outbound prospecting, pipeline analysis, and deal "
            "coaching for Arghyadeep's AI/ML development agency. Answer "
            "the owner's question using this real context; do not invent "
            f"data you don't have:\n\n{context}\n\nQuestion: {query}"
        )
        try:
            hydration = self._context.session_hydration_prompt({"task": "answer_sales_question"})
            result = chat(model=self._model, messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ], timeout=20.0)
            return (result or "").strip() or context
        except Exception as e:
            logger.warning("[VECTOR][sales] answer_sales_question failed: {}", e)
            return context

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "pipeline")
        # Governor dispatch nests arguments under task["params"]; accept both shapes.
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "qualify":
                result = self.qualify_lead(
                    task.get("company", ""), task.get("signals", []),
                    task.get("budget", "unknown"),
                )
                self.award_points(15, "lead_qualified")
                return {"status": "ok", "qualification": result}

            elif task_type == "pipeline":
                result = self.analyze_pipeline(task.get("deals", []))
                if "error" in result:
                    # 2026-10-31: a chat-originated dispatch (Governor.dispatch()
                    # from a plain natural-language question like "what's my
                    # pipeline health") only ever carries
                    # {query, content, source, district} -- never a "deals" key
                    # at all, since nothing extracts one from free text. The old
                    # bare "error" status silently degraded this to the dead
                    # "Processed: pipeline" stub in commands.py. Only THAT case
                    # (the key genuinely absent) gets this honest, helpful
                    # redirect -- an explicit `{"deals": []}` from a real caller
                    # (test_sales_run_reads_params_and_empty_pipeline_is_error)
                    # still means "I tried to send data and it came back empty",
                    # worth a real error, and is unchanged.
                    if result["error"] == "No deals to analyze" and "deals" not in task:
                        return {
                            "status": "ok",
                            "response": (
                                "I don't have deal data loaded to analyze your pipeline against "
                                "right now. If you tell me the deals (stage, value, days in stage) "
                                "I can run stage conversion, weighted pipeline, and at-risk analysis."
                            ),
                            "agent": self.name,
                        }
                    return {"status": "error", "error": result["error"]}
                self._get_memory().store(
                    event_type="pipeline_analysis",
                    content=f"Pipeline: {result.get('total_deals',0)} deals, weighted={result.get('weighted_pipeline',0):,.0f}",
                    tags=["agency", "sales", "pipeline"],
                    source="sales_strategist",
                )
                self.award_points(25, "pipeline_analyzed")
                return {"status": "ok", "pipeline": result}

            elif task_type == "outreach":
                msg = await self.write_outreach(
                    task.get("prospect_name", "Founder"),
                    task.get("company", "Company"),
                    task.get("trigger", "recently posted about AI automation"),
                    task.get("role", "Founder"),
                )
                self.award_points(20, "outreach_written")
                return {"status": "ok", "message": msg}

            else:
                # KNOWN_ISSUES bug pattern: any unmatched task_type (e.g. a
                # stray conversational question routed here) used to always
                # get the static ICP config dumped back, regardless of
                # what was actually asked. Real free text now gets
                # answered; a genuinely content-free structured call still
                # gets the identical ICP dump.
                query = (
                    (task.get("params") or {}).get("query")
                    or task.get("query")
                    or task.get("text")
                    or ""
                ).strip()
                if query:
                    answer = await self.answer_sales_question(query)
                    if answer:
                        self.award_points(15, "sales_question_answered")
                        return {"status": "ok", "response": answer}

                return {"status": "ok", "icp": _ICP, "message": "SalesStrategist ready"}

        except Exception as e:
            logger.error("[VECTOR][sales] {}", e)
            self.deduct_points(30, "sales_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = SalesStrategist()
        qual = agent.qualify_lead("AI Startup Co",
                                  ["recently funded Series A", "hiring ML engineers", "building LLM chatbot"],
                                  "medium")
        print(f"[OK] qualify: tier={qual['tier']} score={qual['total_score']} signals={len(qual['matched_signals'])}")
        pipeline = agent.analyze_pipeline([
            {"name": "Deal A", "stage": "qualified", "value": 50000, "last_updated": "2026-05-01"},
            {"name": "Deal B", "stage": "proposal", "value": 30000, "last_updated": "2026-05-10"},
            {"name": "Deal C", "stage": "prospecting", "value": 20000, "last_updated": "2026-04-20"},
        ])
        print(f"[OK] pipeline: weighted={pipeline['weighted_pipeline']:,.0f} at_risk={len(pipeline['at_risk_deals'])}")
        msg = await agent.write_outreach("Sarah Chen", "TechCorp", "posted about needing AI automation")
        print(f"[OK] outreach: {len(msg)} chars generated")
        result = await agent.run({"type": "qualify", "company": "DataCo",
                                  "signals": ["building AI product", "no ML team"]})
        print(f"[OK] run: status={result['status']}")
        print("sales_strategist.py OK")

    asyncio.run(_smoke())
