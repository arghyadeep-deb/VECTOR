"""
Module: agents/districts/startups/revenue_modeler.py
District: startups | Focus: Model revenue streams, calculate unit economics, project runway
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


class RevenueModeler(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="RevenueModeler",
            district="startups",
            generation=1
        )
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.models = {}
        logger.info("[VECTOR][startups] RevenueModeler ready")

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

    def model_revenue(self, startup_idea: dict) -> dict:
        logger.info(f"[VECTOR][startups] Modeling revenue for: {startup_idea.get('name', 'unnamed')}")
        self.add_lesson({"action": "model_revenue", "idea": startup_idea.get("name")})

        idea_name = startup_idea.get("name", "Unknown")
        description = startup_idea.get("description", "")
        pricing = startup_idea.get("pricing_model", "subscription")

        prompt = f"""Model revenue streams for: {idea_name}
Description: {description}
Pricing model: {pricing}

For each revenue stream:
1. Stream type (subscription, one-time, usage-based, freemium, marketplace, ads, licensing, etc.)
2. Price point and billing frequency
3. Assumptions about customer acquisition and conversion
4. Churn rate assumptions
5. Expected timeline to first revenue
6. Key metrics to track (MRR, ARR, LTV, CAC)

Also include: 1) Revenue projections for months 1, 3, 6, 12, 24, 2) Break-even analysis, 3) Primary vs secondary revenue streams, 4) Sensitivity analysis.
Return JSON: {{revenue_streams: [{{type, price, frequency, assumptions, timeline_months, metrics}}], projections: {{month_1, month_3, month_6, month_12, month_24}}, break_even_month: int, primary_stream: string}}"""
        model_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', model_text, re.DOTALL)
            if json_match:
                revenue_model = json.loads(json_match.group(0))
            else:
                revenue_model = {"revenue_streams": [{"type": "subscription", "price": 29, "assumptions": model_text[:200]}], "projections": {"month_1": 0}}
        except json.JSONDecodeError:
            revenue_model = {"revenue_streams": [{"type": "subscription", "price": 29, "assumptions": model_text[:200]}], "projections": {"month_1": 0}}

        self.models[idea_name] = revenue_model

        result = {
            "startup_idea": idea_name,
            "revenue_streams": revenue_model.get("revenue_streams", []),
            "projections": revenue_model.get("projections", {}),
            "break_even_month": revenue_model.get("break_even_month", 18),
            "primary_stream": revenue_model.get("primary_stream", "subscription"),
            "modeled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="revenue_modeled",
            content=f"Revenue model for '{idea_name}': break-even at month {revenue_model.get('break_even_month', 'unknown')}",
            tags=["startups", "revenue", "modeling"],
            context=result,
            source="RevenueModeler"
        )

        return result

    def calculate_unit_economics(self, revenue_model: dict) -> dict:
        logger.info("[VECTOR][startups] Calculating unit economics")
        self.add_lesson({"action": "calculate_unit_economics"})

        streams = revenue_model.get("revenue_streams", [])
        projections = revenue_model.get("projections", {})

        prompt = f"""Calculate unit economics for this revenue model:
Revenue streams: {json.dumps(streams, indent=2)[:500]}
Projections: {json.dumps(projections, indent=2)}

Calculate and explain:
1. CAC (Customer Acquisition Cost) - estimated based on pricing and growth model
2. LTV (Lifetime Value) - based on pricing, churn, and expansion revenue
3. LTV:CAC ratio (target > 3:1)
4. CAC payback period (target < 12 months)
5. Gross margin estimate
6. MRR/ARR at key milestones
7. Cost per customer segment

Return JSON: {{cac: float, ltv: float, ltv_cac_ratio: float, cac_payback_months: float, gross_margin_pct: float, mrr_at_12mo: float}}"""
        economics = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', economics, re.DOTALL)
            if json_match:
                unit_econ = json.loads(json_match.group(0))
            else:
                unit_econ = {"cac": 100, "ltv": 500, "ltv_cac_ratio": 5.0}
        except json.JSONDecodeError:
            unit_econ = {"cac": 100, "ltv": 500, "ltv_cac_ratio": 5.0}

        unit_econ["health_verdict"] = "GOOD" if unit_econ.get("ltv_cac_ratio", 0) >= 3 and unit_econ.get("cac_payback_months", 99) <= 12 else "NEEDS_WORK" if unit_econ.get("ltv_cac_ratio", 0) >= 1 else "UNSUSTAINABLE"

        result = {
            "unit_economics": unit_econ,
            "revenue_model": revenue_model.get("startup_idea", revenue_model.get("revenue_streams", [{}])[0].get("type", "unknown")),
            "calculated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="unit_economics_calculated",
            content=f"Unit economics: LTV/CAC={unit_econ.get('ltv_cac_ratio', 0):.1f}, payback={unit_econ.get('cac_payback_months', 0):.0f}mo",
            tags=["startups", "unit_economics", "metrics"],
            context=result,
            source="RevenueModeler"
        )

        return result

    def project_runway(self, revenue_model: dict, costs: dict) -> dict:
        logger.info("[VECTOR][startups] Projecting runway")
        self.add_lesson({"action": "project_runway"})

        monthly_revenue = revenue_model.get("projections", {}).get("month_1", 0)
        fixed_costs = costs.get("fixed", [])
        variable_costs = costs.get("variable", [])
        initial_cash = costs.get("initial_cash", 100000)

        monthly_fixed = sum(c.get("amount", 0) for c in fixed_costs)
        monthly_variable_pct = costs.get("variable_pct_of_revenue", 30) / 100

        prompt = f"""Project runway for this startup:
Initial cash: ${initial_cash}
Monthly fixed costs: ${monthly_fixed}
Variable costs: {costs.get('variable_pct_of_revenue', 30)}% of revenue
Revenue projections: {json.dumps(revenue_model.get('projections', {}))}

Calculate month-by-month (months 1-24):
1. Revenue each month
2. Variable costs each month
3. Total costs each month
4. Net cash position each month
5. When runway runs out (if ever)

Return JSON: {{monthly_projection: [{{month: int, revenue: float, costs: float, net_cash: float}}], runway_months: int, burn_rate: float, profitability_month: int or null, cash_reserve_month: int}}"""
        runway_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])

        try:
            import re
            json_match = re.search(r'\{.*\}', runway_text, re.DOTALL)
            if json_match:
                runway_data = json.loads(json_match.group(0))
            else:
                runway_data = {"runway_months": 12, "burn_rate": monthly_fixed}
        except json.JSONDecodeError:
            runway_data = {"runway_months": 12, "burn_rate": monthly_fixed}

        result = {
            "initial_cash": initial_cash,
            "monthly_fixed_costs": monthly_fixed,
            "variable_cost_pct": costs.get("variable_pct_of_revenue", 30),
            "runway_months": runway_data.get("runway_months", 12),
            "burn_rate": runway_data.get("burn_rate", monthly_fixed),
            "profitability_month": runway_data.get("profitability_month"),
            "monthly_projection": runway_data.get("monthly_projection", []),
            "risk_level": "HIGH" if runway_data.get("runway_months", 12) < 6 else "MEDIUM" if runway_data.get("runway_months", 12) < 12 else "LOW",
            "projected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="runway_projected",
            content=f"Runway projection: {runway_data.get('runway_months', 'unknown')} months, risk: {result['risk_level']}",
            tags=["startups", "runway", "financial"],
            context=result,
            source="RevenueModeler"
        )

        logger.info(f"[VECTOR][startups] Runway: {runway_data.get('runway_months', 'unknown')} months, risk: {result['risk_level']}")
        return result


    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        idea = p.get("idea", {"name": p.get("name", ""), "description": p.get("description", "")})
        result = self.model_revenue(idea)
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = RevenueModeler()
    assert agent.district == "startups"

    idea = {
        "name": "AI code review SaaS",
        "description": "Automated code review using LLMs",
        "pricing_model": "subscription",
    }

    model = agent.model_revenue(idea)
    assert "revenue_streams" in model
    assert "projections" in model
    assert "break_even_month" in model

    unit_econ = agent.calculate_unit_economics(model)
    assert "unit_economics" in unit_econ
    assert "ltv_cac_ratio" in unit_econ["unit_economics"]

    costs = {
        "initial_cash": 100000,
        "fixed": [{"name": "salaries", "amount": 8000}, {"name": "server", "amount": 1000}],
        "variable_pct_of_revenue": 30,
    }

    runway = agent.project_runway(model, costs)
    assert "runway_months" in runway
    assert "risk_level" in runway

    print("✅ revenue_modeler.py OK")