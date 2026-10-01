"""
Module: agents/news_trends/opportunity_spotter.py
District: news_trends | Focus: Scan and evaluate market opportunities
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime
from typing import Optional


class OpportunitySpotter(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="OpportunitySpotter",
            district="news_trends",
            generation=1
        )
        self.capabilities = ["cluster_problems", "mine_social", "news_trends", "opportunity", "venture_pipeline"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.tracked_opportunities = {}
        logger.info("[VECTOR][news_trends] OpportunitySpotter ready")

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

    def scan_opportunities(self, industry: str) -> dict:
        logger.info(f"[VECTOR][news_trends] Scanning opportunities in: {industry}")
        self.add_lesson({"action": "scan_opportunities", "industry": industry})

        prompt = f"""Scan the {industry} industry for emerging opportunities. Focus on:
1. Underserved market segments
2. Technology gaps and pain points
3. Regulatory changes creating new space
4. Consumer behavior shifts
5. Emerging niches with low competition

Return a JSON list of opportunity objects with: name, description, market_size_estimate, timeline (immediate/short/medium), competition_level (low/medium/high), key_requirements."""
        response = self._call_ollama(prompt)
        if not (response or "").strip():
            # previously fabricated one "scanned_opportunities" entry with an empty description
            return {"status": "error", "error": "LLM returned no opportunity scan",
                    "industry": industry, "opportunities": [], "count": 0}

        opportunities = []
        try:
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                opportunities = [o for o in json.loads(json_match.group(0)) if isinstance(o, dict)]
            else:
                opportunities = [{"name": "scanned_opportunities", "description": response, "competition_level": "unknown"}]
        except json.JSONDecodeError:
            opportunities = [{"name": "scanned_opportunities", "description": response, "competition_level": "unknown"}]

        result = {
            "industry": industry,
            "opportunities": opportunities,
            "count": len(opportunities),
            "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="opportunities_scanned",
            content=f"Scanned {industry}: found {len(opportunities)} opportunities",
            tags=["opportunities", "scanning", industry],
            context=result,
            source="OpportunitySpotter"
        )

        logger.info(f"[VECTOR][news_trends] Found {len(opportunities)} opportunities in {industry}")
        return result

    def evaluate_opportunity(self, opportunity: dict) -> dict:
        logger.info(f"[VECTOR][news_trends] Evaluating opportunity: {opportunity.get('name', 'unknown')}")
        self.add_lesson({"action": "evaluate_opportunity", "opportunity": opportunity.get("name", "unknown")})

        prompt = f"""Evaluate this business opportunity using the VECTOR scoring framework:
Opportunity: {json.dumps(opportunity, ensure_ascii=False)}
Score across 5 dimensions (1-10 each):
1. Viability: Can it actually work technically and commercially?
2. Edge: What's the defensible advantage?
3. Timing: Is the market ready right now?
4. Recourse: How reversible are key decisions?
5. Outlook: 3-year growth potential?

Return JSON: {{scores: {{viability, edge, timing, recourse, outlook}}, weighted_score: float, pros: string[], cons: string[], verdict: string}}"""
        evaluation = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        scores = None
        try:
            import re
            json_match = re.search(r'\{.*\}', evaluation or "", re.DOTALL)
            if json_match:
                scores = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            scores = None
        if not isinstance(scores, dict) or not isinstance(scores.get("scores"), dict) or not scores["scores"]:
            # A failed/unparseable evaluation used to be invented as 5/5/5/5/5 (weighted 5.0).
            logger.warning("[VECTOR][news_trends] evaluation unparseable for {}", opportunity.get("name", "unknown"))
            return {"status": "error", "error": "LLM returned no parseable evaluation",
                    "opportunity": opportunity.get("name", "unknown"), "evaluation": None}

        result = {
            "opportunity": opportunity.get("name", "unknown"),
            "evaluation": scores,
            "evaluated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="opportunity_evaluated",
            content=f"Evaluated opportunity: {opportunity.get('name', 'unknown')}",
            tags=["opportunities", "evaluation"],
            context=result,
            source="OpportunitySpotter"
        )

        return result

    def track_opportunity(self, opportunity: dict) -> dict:
        logger.info(f"[VECTOR][news_trends] Tracking opportunity: {opportunity.get('name', 'unknown')}")
        self.add_lesson({"action": "track_opportunity"})

        opp_id = opportunity.get("name", str(uuid.uuid4()))
        if opp_id not in self.tracked_opportunities:
            self.tracked_opportunities[opp_id] = {"history": [], "latest": None}

        entry = {
            "opportunity": opportunity,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.tracked_opportunities[opp_id]["history"].append(entry)
        self.tracked_opportunities[opp_id]["latest"] = entry

        result = {
            "opportunity_name": opp_id,
            "tracking_since": self.tracked_opportunities[opp_id]["history"][0]["timestamp"],
            "data_points": len(self.tracked_opportunities[opp_id]["history"]),
            "latest_update": entry["timestamp"],
        }

        self.memory.store(
            event_type="opportunity_tracked",
            content=f"Tracking opportunity: {opp_id}",
            tags=["opportunities", "tracking"],
            context=result,
            source="OpportunitySpotter"
        )

        return result


    async def run(self, task: dict) -> dict:
        p = task.get("params") or {}
        result = self.scan_opportunities(p.get("industry", "AI/ML"))
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    bot = OpportunitySpotter()
    assert bot.district == "news_trends"

    result = bot.scan_opportunities("AI SaaS")
    assert "opportunities" in result
    assert result["count"] >= 1

    opp = {"name": "AI-powered code review", "description": "Automated code review using LLM", "market_size": "$5B"}
    eval_result = bot.evaluate_opportunity(opp)
    assert "evaluation" in eval_result

    track = bot.track_opportunity(opp)
    assert "opportunity_name" in track
    assert track["data_points"] == 1

    print("✅ opportunity_spotter.py OK")