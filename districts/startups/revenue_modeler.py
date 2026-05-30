"""
Module: agents/startups/revenue_modeler.py
District: startups | Focus: Model revenue streams, calculate unit economics, project runway
"""
import sys
import asyncio
import json

from loguru import logger

from core.config import CONFIG
from districts.startups._base import StartupAgentBase


class RevenueModeler(StartupAgentBase):
    def __init__(self):
        super().__init__("RevenueModeler")
        self.models: dict = {}
        logger.info("[VECTOR][startups] RevenueModeler ready")

    def model_revenue(self, startup_idea: dict) -> dict:
        idea_name = startup_idea.get("name", "Unknown")
        logger.info(f"[VECTOR][startups] Modeling revenue for: {idea_name}")
        self.add_lesson({"action": "model_revenue", "idea": idea_name})

        prompt = f"""Model revenue streams for: {idea_name}
Description: {startup_idea.get('description', '')}
Pricing model: {startup_idea.get('pricing_model', 'subscription')}

For each revenue stream: type, price, frequency, assumptions, churn, timeline, key metrics.
Include: projections for months 1/3/6/12/24, break-even analysis, primary vs secondary streams.
Return JSON: {{revenue_streams: [{{type, price, frequency, assumptions, timeline_months, metrics}}], projections: {{month_1, month_3, month_6, month_12, month_24}}, break_even_month: int, primary_stream: string}}"""
        model_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        revenue_model = self._parse_json_response(model_text, {
            "revenue_streams": [{"type": "subscription", "price": 29, "assumptions": model_text[:200]}],
            "projections": {"month_1": 0},
        })
        self.models[idea_name] = revenue_model

        result = {
            "startup_idea": idea_name,
            "revenue_streams": revenue_model.get("revenue_streams", []),
            "projections": revenue_model.get("projections", {}),
            "break_even_month": revenue_model.get("break_even_month", 18),
            "primary_stream": revenue_model.get("primary_stream", "subscription"),
            "modeled_at": self._now_iso(),
        }
        self._store_result("revenue_modeled",
                           f"Revenue model for '{idea_name}': break-even at month {revenue_model.get('break_even_month', 'unknown')}",
                           ["startups", "revenue", "modeling"], result)
        return result

    def calculate_unit_economics(self, revenue_model: dict) -> dict:
        logger.info("[VECTOR][startups] Calculating unit economics")
        self.add_lesson({"action": "calculate_unit_economics"})

        prompt = f"""Calculate unit economics for this revenue model:
Revenue streams: {json.dumps(revenue_model.get('revenue_streams', []), indent=2)[:500]}
Projections: {json.dumps(revenue_model.get('projections', {}), indent=2)}

Calculate: CAC, LTV, LTV:CAC ratio (target >3), CAC payback (target <12 months), gross margin, MRR at 12 months.
Return JSON: {{cac: float, ltv: float, ltv_cac_ratio: float, cac_payback_months: float, gross_margin_pct: float, mrr_at_12mo: float}}"""
        economics = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        unit_econ = self._parse_json_response(economics, {"cac": 100, "ltv": 500, "ltv_cac_ratio": 5.0})
        unit_econ["health_verdict"] = (
            "GOOD" if unit_econ.get("ltv_cac_ratio", 0) >= 3 and unit_econ.get("cac_payback_months", 99) <= 12
            else "NEEDS_WORK" if unit_econ.get("ltv_cac_ratio", 0) >= 1
            else "UNSUSTAINABLE"
        )

        result = {
            "unit_economics": unit_econ,
            "revenue_model": revenue_model.get("startup_idea", "unknown"),
            "calculated_at": self._now_iso(),
        }
        self._store_result("unit_economics_calculated",
                           f"Unit economics: LTV/CAC={unit_econ.get('ltv_cac_ratio', 0):.1f}, payback={unit_econ.get('cac_payback_months', 0):.0f}mo",
                           ["startups", "unit_economics", "metrics"], result)
        return result

    def project_runway(self, revenue_model: dict, costs: dict) -> dict:
        logger.info("[VECTOR][startups] Projecting runway")
        self.add_lesson({"action": "project_runway"})

        initial_cash = costs.get("initial_cash", 100000)
        monthly_fixed = sum(c.get("amount", 0) for c in costs.get("fixed", []))

        prompt = f"""Project runway:
Initial cash: ${initial_cash}
Monthly fixed costs: ${monthly_fixed}
Variable costs: {costs.get('variable_pct_of_revenue', 30)}% of revenue
Revenue projections: {json.dumps(revenue_model.get('projections', {}))}

Project month-by-month for months 1-24: revenue, costs, net cash. When does runway run out?
Return JSON: {{monthly_projection: [{{month: int, revenue: float, costs: float, net_cash: float}}], runway_months: int, burn_rate: float, profitability_month: int or null}}"""
        runway_text = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        runway_data = self._parse_json_response(runway_text, {"runway_months": 12, "burn_rate": monthly_fixed})

        result = {
            "initial_cash": initial_cash,
            "monthly_fixed_costs": monthly_fixed,
            "variable_cost_pct": costs.get("variable_pct_of_revenue", 30),
            "runway_months": runway_data.get("runway_months", 12),
            "burn_rate": runway_data.get("burn_rate", monthly_fixed),
            "profitability_month": runway_data.get("profitability_month"),
            "monthly_projection": runway_data.get("monthly_projection", []),
            "risk_level": "HIGH" if runway_data.get("runway_months", 12) < 6 else "MEDIUM" if runway_data.get("runway_months", 12) < 12 else "LOW",
            "projected_at": self._now_iso(),
        }
        self._store_result("runway_projected",
                           f"Runway: {result['runway_months']} months, risk: {result['risk_level']}",
                           ["startups", "runway", "financial"], result)
        logger.info(f"[VECTOR][startups] Runway: {result['runway_months']} months, risk: {result['risk_level']}")
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
    idea = {"name": "AI code review SaaS", "description": "LLM-based automated code review", "pricing_model": "subscription"}
    model = agent.model_revenue(idea)
    assert "revenue_streams" in model and "projections" in model and "break_even_month" in model
    ue = agent.calculate_unit_economics(model)
    assert "unit_economics" in ue and "ltv_cac_ratio" in ue["unit_economics"]
    costs = {"initial_cash": 100000, "fixed": [{"name": "salaries", "amount": 8000}, {"name": "server", "amount": 1000}], "variable_pct_of_revenue": 30}
    runway = agent.project_runway(model, costs)
    assert "runway_months" in runway and "risk_level" in runway
    print("OK revenue_modeler.py")
