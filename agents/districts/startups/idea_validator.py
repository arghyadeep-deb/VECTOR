"""
Module: agents/districts/startups/idea_validator.py
District: startups | Focus: Validate startup ideas, analyze market size, assess competition
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


class IdeaValidator(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="IdeaValidator",
            district="startups",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.validated_ideas = {}
        logger.info("[VECTOR][startups] IdeaValidator ready")

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

    def validate_idea(self, idea: dict) -> dict:
        logger.info(f"[VECTOR][startups] Validating idea: {idea.get('name', 'unnamed')}")
        self.add_lesson({"action": "validate_idea", "idea": idea.get("name", "unknown")})

        idea_name = idea.get("name", idea.get("concept", "Unknown idea"))
        description = idea.get("description", "")
        problem = idea.get("problem", "")
        solution = idea.get("solution", "")

        prompt = f"""Validate this startup idea across 8 dimensions using the VECTOR framework:
Idea: {idea_name}
Description: {description}
Problem: {problem}
Solution: {solution}

Score each dimension 1-10:
1. Viability: Can it work technically and commercially?
2. Edge: Is there a defensible moat?
3. Timing: Is the market ready now?
4. Recourse: How reversible are decisions?
5. Outlook: 3-year growth potential?
6. Team-fit: Does it match founder strengths?
7. Passion: Does it excite the founders?
8. Risk: What are the top 3 failure modes?

Return JSON: {{scores: {{viability, edge, timing, recourse, outlook, team_fit, passion, risk}}, overall_score: float, verdict: string, pros: string[], cons: string[], must_fix_before_launch: string[]}}"""
        validation = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', validation, re.DOTALL)
            if json_match:
                result_data = json.loads(json_match.group(0))
            else:
                result_data = {"scores": {"viability": 5, "edge": 5, "timing": 5, "recourse": 5, "outlook": 5, "team_fit": 5, "passion": 5, "risk": 5}, "overall_score": 5.0}
        except json.JSONDecodeError:
            result_data = {"scores": {"viability": 5, "edge": 5, "timing": 5, "recourse": 5, "outlook": 5, "team_fit": 5, "passion": 5, "risk": 5}, "overall_score": 5.0}

        scores = result_data.get("scores", {})
        overall = result_data.get("overall_score", sum(scores.values()) / max(len(scores), 1) if scores else 5.0)
        verdict_text = result_data.get("verdict", "")
        verdict = "STRONG" if overall >= 7 else "PROMISING" if overall >= 5 else "WEAK" if overall >= 3 else "REJECT"

        validated = {
            "idea_name": idea_name,
            "scores": scores,
            "overall_score": round(overall, 2),
            "verdict": verdict,
            "pros": result_data.get("pros", []),
            "cons": result_data.get("cons", []),
            "must_fix": result_data.get("must_fix_before_launch", []),
            "validation_details": verdict_text,
            "validated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.validated_ideas[idea_name] = validated

        self.memory.store(
            event_type="idea_validated",
            content=f"Idea '{idea_name}' validated: {verdict} ({overall:.1f}/10)",
            tags=["startups", "validation", "idea"],
            context=validated,
            source="IdeaValidator"
        )

        logger.info(f"[VECTOR][startups] Idea '{idea_name}' validated: {verdict} ({overall:.1f})")
        return validated

    def analyze_market_size(self, idea: dict) -> dict:
        logger.info(f"[VECTOR][startups] Analyzing market size for: {idea.get('name', 'unnamed')}")
        self.add_lesson({"action": "analyze_market_size", "idea": idea.get("name")})

        idea_name = idea.get("name", "Unknown")

        prompt = f"""Analyze market size for: {idea_name}
Description: {idea.get('description', idea.get('solution', ''))}
Target market: {idea.get('target_market', 'general consumers')}

Estimate: 1) TAM (Total Addressable Market), 2) SAM (Serviceable Available Market), 3) SOM (Serviceable Obtainable Market).
Include: market growth rate, key segments, pricing strategy, revenue model, competitor pricing.
Return JSON: {{tam: string, sam: string, som: string, growth_rate: string, segments: string[], pricing_model: string}}"""
        market = self._call_ollama(prompt)

        try:
            import re
            json_match = re.search(r'\{.*\}', market, re.DOTALL)
            if json_match:
                market_data = json.loads(json_match.group(0))
            else:
                market_data = {"tam": "Unable to estimate", "sam": "Unable to estimate", "som": "Unable to estimate"}
        except json.JSONDecodeError:
            market_data = {"tam": "Parsing error", "sam": "Parsing error", "som": "Parsing error"}

        result = {
            "idea_name": idea_name,
            "market_size": market_data,
            "analyzed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="market_size_analyzed",
            content=f"Market size analysis for '{idea_name}'",
            tags=["startups", "market", "analysis"],
            context=result,
            source="IdeaValidator"
        )

        return result

    def assess_competition(self, idea: dict) -> dict:
        logger.info(f"[VECTOR][startups] Assessing competition for: {idea.get('name', 'unnamed')}")
        self.add_lesson({"action": "assess_competition", "idea": idea.get("name")})

        idea_name = idea.get("name", "Unknown")

        prompt = f"""Assess competitive landscape for: {idea_name}
Solution: {idea.get('solution', '')}
Target market: {idea.get('target_market', '')}

For each major competitor: name, strength, weakness, pricing, market share.
Identify: 1) Direct competitors, 2) Indirect competitors, 3) Substitute products, 4) Potential new entrants.
Provide: competitive advantages, barriers to entry, differentiation strategy.
Return JSON: {{direct_competitors: [{{name, strength, weakness, pricing, market_share}}], indirect: string[], substitutes: string[], moat_factors: string[], differentiation: string}}"""
        competition = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', competition, re.DOTALL)
            if json_match:
                comp_data = json.loads(json_match.group(0))
            else:
                comp_data = {"direct_competitors": [], "moat_factors": [competition[:300]]}
        except json.JSONDecodeError:
            comp_data = {"direct_competitors": [], "moat_factors": [competition[:300]]}

        result = {
            "idea_name": idea_name,
            "competition": comp_data,
            "competitive_intensity": "HIGH" if len(comp_data.get("direct_competitors", [])) >= 5 else "MEDIUM" if len(comp_data.get("direct_competitors", [])) >= 2 else "LOW",
            "assessed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="competition_assessed",
            content=f"Competition assessment for '{idea_name}': {result['competitive_intensity']}",
            tags=["startups", "competition", "analysis"],
            context=result,
            source="IdeaValidator"
        )

        return result


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = IdeaValidator()
    assert agent.district == "startups"

    idea = {
        "name": "AI-powered code review",
        "description": "Automated code review using LLMs",
        "problem": "Developers spend 20% of time on code review",
        "solution": "AI agent that reviews code and suggests fixes",
        "target_market": "software development teams",
    }

    validation = agent.validate_idea(idea)
    assert "verdict" in validation
    assert "scores" in validation
    assert "overall_score" in validation

    market = agent.analyze_market_size(idea)
    assert "market_size" in market

    comp = agent.assess_competition(idea)
    assert "competition" in comp

    print("✅ idea_validator.py OK")