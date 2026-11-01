"""
VECTOR CompetitorIntelAgent — Competitive intelligence district agent.

Profiles competitors from URLs, generates intelligence dossiers, tracks
market positioning, and surfaces strategic opportunities.

Governor routes: competitor, competitive, market research, market intelligence
CLI tools: exa (web search), g2, trustpilot, clearbit, similarweb, ahrefs
Skill prompts: competitor-profiling, competitors
"""

import sys
import asyncio
import json
import re

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from districts.marketing._skill_loader import load_skill, SkillMixin

class CompetitorIntelAgent(AgentBase, SkillMixin):
    """
    Competitive intelligence specialist.
    Profiles competitors, maps the market landscape, surfaces strategic gaps.
    Uses competitor-profiling + competitors skill prompts for expert analysis.
    """

    def __init__(self):
        super().__init__(agent_id="competitor_intel_001", name="CompetitorIntelAgent", district="marketing")
        self.capabilities = ["competitor", "intel", "marketing"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._skill_prompt = load_skill("competitor-profiling", "competitors")
        logger.info("[VECTOR][competitor_intel] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def profile_competitor(self, competitor: str, context: str = "") -> dict:
        """Build a comprehensive profile of a competitor from name/URL."""
        prompt = (
            f"Create a comprehensive competitive intelligence profile for: {competitor}\n"
            f"Context: {context}\n\n"
            "Profile should cover:\n"
            "1. Business model and revenue streams\n"
            "2. Target audience and ICP\n"
            "3. Key product features and differentiators\n"
            "4. Pricing strategy and positioning\n"
            "5. Content and marketing strategy\n"
            "6. Strengths (what they do well)\n"
            "7. Weaknesses (gaps we can exploit)\n"
            "8. Strategic opportunities for VECTOR\n\n"
            "Return as JSON: {"
            "name: str, business_model: str, target_audience: str, "
            "key_features: [], pricing: str, strengths: [], weaknesses: [], "
            "opportunities: [], threat_level: low|medium|high"
            "}"
        )
        try:
            response = self._chat(prompt, timeout=35.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][competitor_intel] profile_competitor failed: {}", e)
        return {"name": competitor, "error": "Could not generate profile"}

    def map_market_landscape(self, category: str, competitors: list[str]) -> dict:
        """Map the competitive landscape and identify positioning opportunities."""
        prompt = (
            f"Map the competitive landscape for: {category}\n"
            f"Key players: {', '.join(competitors)}\n\n"
            "Provide:\n"
            "1. Market positioning map (price vs quality axes)\n"
            "2. Whitespace opportunities (underserved segments)\n"
            "3. The most vulnerable competitor and why\n"
            "4. Recommended positioning for VECTOR in this market\n"
            "5. Three differentiation angles with highest potential\n\n"
            "Return as JSON: {"
            "positioning_map: {}, whitespace: [], most_vulnerable: str, "
            "recommended_position: str, differentiation_angles: []"
            "}"
        )
        try:
            response = self._chat(prompt, timeout=30.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][competitor_intel] map_landscape failed: {}", e)
        return {}

    def find_strategic_gaps(self, our_strengths: list[str], competitor: str) -> dict:
        """Find strategic gaps vs a specific competitor."""
        prompt = (
            f"Find strategic gaps and opportunities vs {competitor}.\n"
            f"Our key strengths: {', '.join(our_strengths)}\n\n"
            "Identify:\n"
            "1. Features/capabilities they lack that we have or could build\n"
            "2. Market segments they under-serve\n"
            "3. Messaging angles they ignore\n"
            "4. Customer pain points their reviews mention\n"
            "5. The single biggest strategic advantage we should emphasize\n\n"
            "Return as JSON: {"
            "feature_gaps: [], market_gaps: [], messaging_gaps: [], "
            "customer_pain_points: [], top_advantage: str"
            "}"
        )
        try:
            response = self._chat(prompt, timeout=25.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][competitor_intel] find_gaps failed: {}", e)
        return {}

    def build_xray_brief(self, target: str, context: str = "") -> dict:
        """Convert profile_competitor()'s free-form LLM findings into the
        Competitor X-Ray evidence-tiered brief schema (districts/marketing/
        competitor_xray.py) — structured claims, normalized target,
        threat ranking. LLM-derived findings are tagged INFERRED (not
        CONFIRMED — no independent source verification happens here)."""
        from districts.marketing.competitor_xray import build_empty_brief, make_claim, score_threat

        profile = self.profile_competitor(target, context)
        brief = build_empty_brief(target, confidence="medium" if "error" not in profile else "low")

        for strength in profile.get("strengths", []):
            brief.funnel.append(make_claim(f"Strength: {strength}", tier="INFERRED"))
        for weakness in profile.get("weaknesses", []):
            brief.funnel.append(make_claim(f"Weakness: {weakness}", tier="INFERRED"))
        for opportunity in profile.get("opportunities", []):
            brief.monetization.append(make_claim(f"Opportunity: {opportunity}", tier="INFERRED"))
        if profile.get("pricing"):
            brief.monetization.append(make_claim(f"Pricing: {profile['pricing']}", tier="INFERRED"))

        threat_map = {"low": 20.0, "medium": 55.0, "high": 85.0}
        threat_level = str(profile.get("threat_level", "medium")).lower()
        maturity = threat_map.get(threat_level, 50.0)
        evidence_quality = 60.0 if "error" not in profile else 10.0
        brief.threat_score = score_threat(maturity=maturity, momentum=maturity, evidence_quality=evidence_quality)

        return brief.to_dict()

    async def run(self, task: dict) -> dict:
        action = task.get("type", "")
        params = task.get("params", {})

        if "xray" in action or "x-ray" in action or "x_ray" in action:
            competitor = params.get("competitor", params.get("query", ""))
            context = params.get("context", "")
            result = self.build_xray_brief(competitor, context)
            return {
                "message": f"X-Ray brief complete. Threat score: {result.get('threat_score', 0)}.",
                "data": result,
            }

        elif "profile" in action or "competitor" in action:
            competitor = params.get("competitor", params.get("query", ""))
            context = params.get("context", "")
            result = self.profile_competitor(competitor, context)
            threat = result.get("threat_level", "unknown")
            return {
                "message": f"Competitor profile complete. Threat level: {threat}. "
                           f"Found {len(result.get('opportunities', []))} strategic opportunities.",
                "data": result,
            }

        elif "landscape" in action or "market" in action:
            category = params.get("category", params.get("query", ""))
            competitors = params.get("competitors", [])
            result = self.map_market_landscape(category, competitors)
            return {
                "message": f"Market landscape mapped. Recommended position: {result.get('recommended_position', 'See analysis')}",
                "data": result,
            }

        elif "gap" in action or "advantage" in action:
            strengths = params.get("strengths", ["AI-powered", "local-first", "privacy-focused"])
            competitor = params.get("competitor", params.get("query", ""))
            result = self.find_strategic_gaps(strengths, competitor)
            return {
                "message": f"Gap analysis complete. Top advantage: {result.get('top_advantage', 'See analysis')}",
                "data": result,
            }

        else:
            return {
                "message": "CompetitorIntelAgent capabilities: profile_competitor, map_market_landscape, find_strategic_gaps. "
                           "Skills: competitor-profiling + competitors. "
                           "CLI tools: exa, g2, trustpilot, clearbit, similarweb, ahrefs (via marketing_cli MCP).",
            }

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = CompetitorIntelAgent()
    print(f"✅ CompetitorIntelAgent OK — skill_prompt loaded ({len(agent._skill_prompt)} chars)")
    print(f"   Skills: competitor-profiling + competitors")
