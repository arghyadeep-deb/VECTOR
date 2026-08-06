"""
Module: agents/startups/idea_validator.py
District: startups | Focus: Validate startup ideas, analyze market size, assess competition
"""
import sys
import asyncio

from loguru import logger

from core.config import CONFIG
from districts.startups._base import StartupAgentBase


class IdeaValidator(StartupAgentBase):
    def __init__(self):
        super().__init__("IdeaValidator")
        self.capabilities = ["STRONG", "idea", "startups", "validate", "venture_pipeline", "viability"]
        self.validated_ideas = {}
        logger.info("[VECTOR][startups] IdeaValidator ready")

    def validate_idea(self, idea: dict) -> dict:
        idea_name = idea.get("name", idea.get("concept", "Unknown idea"))
        logger.info(f"[VECTOR][startups] Validating idea: {idea_name}")
        self.add_lesson({"action": "validate_idea", "idea": idea_name})

        try:
            from core.brain.blueprint_doctrine import get_regime
            regime = get_regime()
        except Exception:
            regime = "NORMAL"

        prompt = f"""Validate this startup idea across 11 dimensions using the VECTOR framework:
Idea: {idea_name}
Description: {idea.get('description', '')}
Problem: {idea.get('problem', '')}
Solution: {idea.get('solution', '')}

Governing law — The Equation (Brain vault: Blueprint/(C) The Equation — Top 100 Wealth Pattern.md):
W = Σ O×R×M. Ownership × Revenue × Multiple, sequenced: a new product is only admitted
if the current one has passed the graduation gate (₹1L+/month × 3 months, ≤5 hrs/week
owner time, churn <10%). Revenue is mandatory — an idea with no path to a paying
stranger within 90 days contributes 0 regardless of how impressive it is to build.
Current market regime: {regime} (Downturn Playbook: NORMAL = standard gates;
CORRECTION/CRISIS = no new product starts — only retention, cost-saving pitches, and
harvesting existing products are admissible).

Score each dimension 1-10:
1. Viability: Can it work technically and commercially?
2. Edge: Is there a defensible moat?
3. Timing: Is the market ready now?
4. Recourse: How reversible are decisions?
5. Outlook: 3-year growth potential?
6. Team-fit: Does it match founder strengths?
7. Passion: Does it excite the founders?
8. Risk: What are the top 3 failure modes?
9. Revenue velocity (R): Can a paying stranger be reached within 90 days?
10. VECTOR operability (O): Can VECTOR run ops/content/support at ≤5 hrs/week owner time, so no dilution-forcing hires?
11. Distribution (M): Is there an existing channel to the buyer and a moat mechanism (data loop, network effect, switching cost)?

Return JSON: {{scores: {{viability, edge, timing, recourse, outlook, team_fit, passion, risk, revenue_velocity, vector_operability, distribution}}, overall_score: float, verdict: string, pros: string[], cons: string[], must_fix_before_launch: string[]}}"""
        validation = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        result_data = self._parse_json_response(validation, {
            "scores": {k: 5 for k in ("viability", "edge", "timing", "recourse", "outlook", "team_fit", "passion", "risk", "revenue_velocity", "vector_operability", "distribution")},
            "overall_score": 5.0,
        })

        scores = result_data.get("scores", {})
        overall = result_data.get("overall_score", sum(scores.values()) / max(len(scores), 1) if scores else 5.0)
        verdict = "STRONG" if overall >= 7 else "PROMISING" if overall >= 5 else "WEAK" if overall >= 3 else "REJECT"

        # Equation hard gate (W = Σ O×R×M): R=0 zeroes the term — no plausible path to a
        # paying stranger within 90 days caps the verdict at WEAK regardless of overall score.
        if scores.get("revenue_velocity", 5) < 4 and verdict in ("STRONG", "PROMISING"):
            logger.warning(f"[VECTOR][startups] Equation gate: '{idea_name}' capped to WEAK (revenue_velocity={scores.get('revenue_velocity')})")
            verdict = "WEAK"

        # Regime gate (Downturn Playbook): outside NORMAL, new product starts are frozen —
        # a strong idea is deferred, not rejected; revisit when the regime returns to NORMAL.
        if regime != "NORMAL" and verdict in ("STRONG", "PROMISING"):
            logger.warning(f"[VECTOR][startups] Regime gate ({regime}): '{idea_name}' deferred — no new starts outside NORMAL")
            verdict = "DEFERRED"

        validated = {
            "idea_name": idea_name,
            "scores": scores,
            "overall_score": round(overall, 2),
            "verdict": verdict,
            "regime": regime,
            "pros": result_data.get("pros", []),
            "cons": result_data.get("cons", []),
            "must_fix": result_data.get("must_fix_before_launch", []),
            "validation_details": result_data.get("verdict", ""),
            "validated_at": self._now_iso(),
        }
        self.validated_ideas[idea_name] = validated
        self._store_result(
            "idea_validated",
            f"Idea '{idea_name}' validated: {verdict} ({overall:.1f}/10)",
            ["startups", "validation", "idea"],
            validated,
        )
        logger.info(f"[VECTOR][startups] Idea '{idea_name}' validated: {verdict} ({overall:.1f})")
        return validated

    def analyze_market_size(self, idea: dict) -> dict:
        idea_name = idea.get("name", "Unknown")
        logger.info(f"[VECTOR][startups] Analyzing market size for: {idea_name}")
        self.add_lesson({"action": "analyze_market_size", "idea": idea_name})

        prompt = f"""Analyze market size for: {idea_name}
Description: {idea.get('description', idea.get('solution', ''))}
Target market: {idea.get('target_market', 'general consumers')}

Estimate: 1) TAM, 2) SAM, 3) SOM. Include growth rate, segments, pricing model.
Return JSON: {{tam: string, sam: string, som: string, growth_rate: string, segments: string[], pricing_model: string}}"""
        market = self._call_ollama(prompt)
        market_data = self._parse_json_response(market, {
            "tam": "Unable to estimate", "sam": "Unable to estimate", "som": "Unable to estimate",
        })

        result = {"idea_name": idea_name, "market_size": market_data, "analyzed_at": self._now_iso()}
        self._store_result("market_size_analyzed", f"Market size analysis for '{idea_name}'",
                           ["startups", "market", "analysis"], result)
        return result

    def assess_competition(self, idea: dict) -> dict:
        idea_name = idea.get("name", "Unknown")
        logger.info(f"[VECTOR][startups] Assessing competition for: {idea_name}")
        self.add_lesson({"action": "assess_competition", "idea": idea_name})

        prompt = f"""Assess competitive landscape for: {idea_name}
Solution: {idea.get('solution', '')}
Target market: {idea.get('target_market', '')}

Identify: direct/indirect competitors, substitutes, moat factors, differentiation.
Return JSON: {{direct_competitors: [{{name, strength, weakness, pricing, market_share}}], indirect: string[], substitutes: string[], moat_factors: string[], differentiation: string}}"""
        competition = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        comp_data = self._parse_json_response(competition, {
            "direct_competitors": [], "moat_factors": [competition[:300]],
        })

        result = {
            "idea_name": idea_name,
            "competition": comp_data,
            "competitive_intensity": "HIGH" if len(comp_data.get("direct_competitors", [])) >= 5 else "MEDIUM" if len(comp_data.get("direct_competitors", [])) >= 2 else "LOW",
            "assessed_at": self._now_iso(),
        }
        self._store_result("competition_assessed",
                           f"Competition assessment for '{idea_name}': {result['competitive_intensity']}",
                           ["startups", "competition", "analysis"], result)
        return result

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        # 2026-07-28: for free-text chat dispatch, p has no "idea"/"name"/
        # "description" keys, so this validated an idea named "" every
        # single time — same bug class as design district's #33.
        query = p.get("query") or p.get("content") or task.get("query")
        if query and not (p.get("idea") or p.get("name")):
            ctx = f"{len(self.validated_ideas)} idea(s) validated so far this session."
            return {"status": "ok", "response": await self.answer_startup_question(query, ctx)}
        idea = p.get("idea", {"name": p.get("name", ""), "description": p.get("description", "")})
        result = self.validate_idea(idea)
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = IdeaValidator()
    assert agent.district == "startups"
    idea = {"name": "AI-powered code review", "description": "LLM-based automated code review",
            "problem": "Developers spend 20% of time on code review", "solution": "AI agent"}
    v = agent.validate_idea(idea)
    assert "verdict" in v and "scores" in v and "overall_score" in v
    m = agent.analyze_market_size(idea)
    assert "market_size" in m
    c = agent.assess_competition(idea)
    assert "competition" in c
    print("OK idea_validator.py")
