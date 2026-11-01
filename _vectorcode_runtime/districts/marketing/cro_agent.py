"""
VECTOR CROAgent — Conversion Rate Optimization district agent.

Analyzes landing pages, suggests A/B tests, writes variant copy,
and diagnoses conversion drop-off using CRO best practices.

Governor routes: cro, conversion, landing page, a/b test, page not converting
CLI tools: hotjar, optimizely, pendo, ga4 (via marketing_cli MCP tool)
Skill prompts: cro, copywriting, analytics
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

class CROAgent(AgentBase, SkillMixin):
    """
    Conversion Rate Optimization specialist.
    Analyzes pages for friction, suggests A/B tests, writes variant copy.
    Uses cro + copywriting + analytics skill prompts for expert-level output.
    """

    def __init__(self):
        super().__init__(agent_id="cro_agent_001", name="CROAgent", district="marketing")
        self.capabilities = ["conversion", "cro", "marketing"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        self._skill_prompt = load_skill("cro", "copywriting", "analytics")
        logger.info("[VECTOR][cro] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def analyze_page(self, url: str, page_type: str = "landing") -> dict:
        """Analyze a page for CRO issues and suggest improvements."""
        prompt = (
            f"Analyze this {page_type} page for conversion rate optimization: {url}\n\n"
            "Provide a structured CRO audit covering:\n"
            "1. Above-the-fold analysis (headline, subheadline, CTA visibility)\n"
            "2. Trust signals (social proof, testimonials, guarantees)\n"
            "3. Friction points (form length, load speed, navigation distractions)\n"
            "4. Value proposition clarity (is the offer clear in <5 seconds?)\n"
            "5. CTA optimization (button copy, placement, contrast)\n"
            "6. Mobile experience issues\n"
            "7. Top 3 A/B test hypotheses with expected impact\n\n"
            "Return as JSON: {issues: [], ab_tests: [], quick_wins: [], priority_fix: str}"
        )
        try:
            response = self._chat(prompt, timeout=30.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][cro] analyze_page LLM failed: {}", e)
        return {"issues": [], "ab_tests": [], "quick_wins": [], "priority_fix": "Review manually"}

    def write_variant_copy(self, original: str, element: str = "headline") -> dict:
        """Write A/B test variant copy for a given page element."""
        prompt = (
            f"Write 3 A/B test variants for this {element}:\n\n"
            f"ORIGINAL: {original}\n\n"
            "For each variant explain:\n"
            "- The hypothesis (why this might convert better)\n"
            "- The psychological principle used\n"
            "- The expected lift range (%)\n\n"
            "Return as JSON: {variants: [{copy: str, hypothesis: str, principle: str, expected_lift: str}]}"
        )
        try:
            response = self._chat(prompt, timeout=25.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][cro] write_variant_copy LLM failed: {}", e)
        return {"variants": []}

    def diagnose_funnel_drop(self, funnel_data: list[dict]) -> dict:
        """Diagnose where and why users are dropping off a funnel."""
        prompt = (
            f"Diagnose conversion drop-off in this funnel:\n{json.dumps(funnel_data, indent=2)}\n\n"
            "Identify:\n"
            "1. The biggest drop-off stage and why it's happening\n"
            "2. Likely causes (UX friction, trust, price anchor, unclear value)\n"
            "3. Three specific fixes with effort vs impact estimates\n"
            "4. The single highest-ROI intervention\n\n"
            "Return as JSON: {biggest_drop: str, causes: [], fixes: [], top_intervention: str}"
        )
        try:
            response = self._chat(prompt, timeout=25.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][cro] diagnose_funnel_drop LLM failed: {}", e)
        return {}

    async def run(self, task: dict) -> dict:
        action = task.get("type", "")
        params = task.get("params", {})

        if "landing" in action or "page" in action or "conversion" in action:
            url = params.get("url", params.get("query", "unknown page"))
            result = self.analyze_page(url, params.get("page_type", "landing"))
            return {"message": f"CRO audit complete. Priority fix: {result.get('priority_fix', 'See analysis')}", "data": result}

        elif "variant" in action or "copy" in action or "ab_test" in action or "a/b" in action:
            original = params.get("copy", params.get("query", ""))
            element = params.get("element", "headline")
            result = self.write_variant_copy(original, element)
            count = len(result.get("variants", []))
            return {"message": f"Generated {count} A/B test variants for {element}.", "data": result}

        elif "funnel" in action or "drop" in action:
            funnel = params.get("funnel", [])
            result = self.diagnose_funnel_drop(funnel)
            return {"message": f"Funnel diagnosis: {result.get('top_intervention', 'See analysis')}", "data": result}

        else:
            return {
                "message": "CROAgent capabilities: analyze_page, write_variant_copy, diagnose_funnel_drop. "
                           "Skills: cro + copywriting + analytics. "
                           "CLI tools: hotjar, optimizely, pendo, ga4 (via marketing_cli MCP).",
            }

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = CROAgent()
    print(f"✅ CROAgent OK — skill_prompt loaded ({len(agent._skill_prompt)} chars)")
    print(f"   Skills: cro + copywriting + analytics")
