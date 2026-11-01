"""
Financial Analyst — financial modeling, forecasting, scenario analysis.

Provides professional-grade financial analysis for Arghyadeep's startup/agency
projects and investment decisions. DCF, three-statement basics, scenario modeling.
"""

import asyncio
import json
import re
import math
import datetime

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

class FinancialAnalyst(AgentBase):
    """
    Financial modeling, DCF valuation, scenario analysis, break-even modeling.
    Analysis only — never executes financial transactions (VECTOR critical rule).
    """

    def __init__(self):
        super().__init__(agent_id="financial_analyst_001", name="FinancialAnalyst", district="finance")
        self.capabilities = ["analysis", "break_even", "business_model", "dcf", "finance", "financial", "money"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info("[VECTOR][financial_analyst] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def dcf_valuation(self, fcf_projections: list[float], wacc: float,
                      terminal_growth: float = 0.03) -> dict:
        """Discounted Cash Flow valuation. fcf_projections in INR/USD."""
        if not fcf_projections or wacc <= terminal_growth:
            return {"error": "Invalid inputs: need projections and WACC > terminal growth rate"}

        pv_fcfs = []
        for i, fcf in enumerate(fcf_projections, 1):
            pv = fcf / ((1 + wacc) ** i)
            pv_fcfs.append(round(pv, 2))

        terminal_value = fcf_projections[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
        pv_terminal = terminal_value / ((1 + wacc) ** len(fcf_projections))
        enterprise_value = sum(pv_fcfs) + pv_terminal

        return {
            "pv_free_cash_flows": pv_fcfs,
            "sum_pv_fcf": round(sum(pv_fcfs), 2),
            "terminal_value": round(terminal_value, 2),
            "pv_terminal_value": round(pv_terminal, 2),
            "enterprise_value": round(enterprise_value, 2),
            "wacc": wacc,
            "terminal_growth_rate": terminal_growth,
            "projection_years": len(fcf_projections),
            "note": "ANALYSIS ONLY — no investment decisions automated",
        }

    def break_even_analysis(self, fixed_costs: float, variable_cost_per_unit: float,
                            price_per_unit: float) -> dict:
        """Break-even point in units and revenue."""
        if price_per_unit <= variable_cost_per_unit:
            return {"error": "Price must exceed variable cost per unit"}
        contribution_margin = price_per_unit - variable_cost_per_unit
        break_even_units = math.ceil(fixed_costs / contribution_margin)
        break_even_revenue = break_even_units * price_per_unit
        margin_of_safety_pct = 0.0
        return {
            "fixed_costs": fixed_costs,
            "variable_cost_per_unit": variable_cost_per_unit,
            "price_per_unit": price_per_unit,
            "contribution_margin": round(contribution_margin, 2),
            "contribution_margin_pct": round(contribution_margin / price_per_unit * 100, 1),
            "break_even_units": break_even_units,
            "break_even_revenue": round(break_even_revenue, 2),
        }

    def run_scenario_analysis(self, base_revenue: float, base_costs: float,
                              scenarios: dict | None = None) -> dict:
        """Bull/base/bear scenario P&L analysis."""
        if scenarios is None:
            scenarios = {
                "bull": {"revenue_multiplier": 1.3, "cost_multiplier": 1.1},
                "base": {"revenue_multiplier": 1.0, "cost_multiplier": 1.0},
                "bear": {"revenue_multiplier": 0.7, "cost_multiplier": 1.15},
            }
        results = {}
        for name, mults in scenarios.items():
            rev = base_revenue * mults["revenue_multiplier"]
            cost = base_costs * mults["cost_multiplier"]
            profit = rev - cost
            margin = profit / rev * 100 if rev > 0 else 0
            results[name] = {
                "revenue": round(rev, 2),
                "costs": round(cost, 2),
                "profit": round(profit, 2),
                "margin_pct": round(margin, 1),
                "profitable": profit > 0,
            }
        return {
            "base_inputs": {"revenue": base_revenue, "costs": base_costs},
            "scenarios": results,
            "recommendation": (
                "Viable even in bear case" if results.get("bear", {}).get("profitable")
                else "Bear case shows losses — validate cost assumptions"
            ),
        }

    async def analyze_business_model(self, description: str) -> dict:
        """LLM analysis of a business model's financial viability."""
        prompt = (
            f"Analyze this business model financially:\n{description}\n\n"
            f"Return JSON:\n"
            f'{{"revenue_streams": [], "cost_structure": [], "unit_economics": {{}}, '
            f'"key_assumptions": [], "risks": [], "viability_score": 1-10, '
            f'"recommendation": "proceed/validate/pivot"}}'
        )
        try:
            response = chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=25.0)
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning("[VECTOR][financial_analyst] LLM failed: {}", e)

        return {
            "revenue_streams": ["Subscription", "One-time service fee"],
            "cost_structure": ["Infrastructure", "Labor", "Marketing"],
            "unit_economics": {"ltv_cac_ratio": "unknown — gather data first"},
            "key_assumptions": ["Customer acquisition cost < LTV", "Churn < 5% monthly"],
            "risks": ["Market size validation needed", "Competition from incumbents"],
            "viability_score": 6,
            "recommendation": "validate",
        }

    async def answer_finance_question(self, query: str) -> str:
        """Answer a free-text question about VECTOR's financial-analysis
        capabilities, instead of always running a scenario analysis
        against fully hardcoded placeholder revenue/cost figures
        regardless of what was actually asked."""
        prompt = (
            "You are VECTOR's FinancialAnalyst in the finance district — "
            "you do DCF valuation, break-even analysis, business-model "
            "review, and scenario modeling. Analysis only — you never "
            "execute financial transactions. Answer the owner's question "
            "directly and concretely. Do not invent hypothetical revenue/"
            f"cost figures unless the question actually asks for a "
            f"scenario model.\n\nQuestion: {query}"
        )
        try:
            result = chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=20.0)
            return (result or "").strip()
        except Exception as e:
            logger.warning("[VECTOR][financial_analyst] answer_finance_question failed: {}", e)
            return ""

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "scenario")
        try:
            if task_type == "dcf":
                result = self.dcf_valuation(
                    task.get("fcf_projections", [100000, 150000, 200000, 250000, 300000]),
                    task.get("wacc", 0.12),
                    task.get("terminal_growth", 0.03),
                )
                self.award_points(30, "dcf_completed")
                return {"status": "ok", "dcf": result}

            elif task_type == "break_even":
                result = self.break_even_analysis(
                    task.get("fixed_costs", 50000),
                    task.get("variable_cost", 100),
                    task.get("price", 500),
                )
                self.award_points(20, "break_even_analyzed")
                return {"status": "ok", "break_even": result}

            elif task_type == "business_model":
                result = await self.analyze_business_model(task.get("description", ""))
                self.award_points(35, "business_model_analyzed")
                return {"status": "ok", "analysis": result}

            else:  # scenario, or an unmatched task_type carrying a free-text question
                # KNOWN_ISSUES bug pattern (same shape as governance's
                # product_manager fix): a conversational question with no
                # real revenue/cost figures used to still get a scenario
                # analysis run against fully hardcoded placeholder numbers
                # (base_revenue=500000, base_costs=350000) instead of an
                # answer.
                query = (
                    (task.get("params") or {}).get("query")
                    or task.get("query")
                    or task.get("text")
                    or ""
                ).strip()
                if query and "base_revenue" not in task:
                    answer = await self.answer_finance_question(query)
                    if answer:
                        self.award_points(15, "finance_question_answered")
                        return {"status": "ok", "response": answer}

                result = self.run_scenario_analysis(
                    task.get("base_revenue", 500000),
                    task.get("base_costs", 350000),
                    task.get("scenarios", None),
                )
                self._get_memory().store(
                    event_type="scenario_analysis",
                    content=f"Scenario analysis: base_rev={task.get('base_revenue',0)}",
                    tags=["finance", "analysis"],
                    source="financial_analyst",
                )
                self.award_points(25, "scenario_analyzed")
                return {"status": "ok", "scenario": result}

        except Exception as e:
            logger.error("[VECTOR][financial_analyst] {}", e)
            self.deduct_points(30, "financial_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = FinancialAnalyst()
        dcf = agent.dcf_valuation([50000, 80000, 120000, 180000, 250000], wacc=0.15)
        print(f"[OK] dcf: enterprise_value={dcf['enterprise_value']:,.0f} years={dcf['projection_years']}")
        be = agent.break_even_analysis(100000, 200, 800)
        print(f"[OK] break_even: units={be['break_even_units']} revenue={be['break_even_revenue']:,.0f}")
        sc = agent.run_scenario_analysis(500000, 350000)
        print(f"[OK] scenario: base_profit={sc['scenarios']['base']['profit']:,.0f} bear={sc['scenarios']['bear']['profitable']}")
        result = await agent.run({"type": "scenario"})
        print(f"[OK] run: status={result['status']}")
        print("financial_analyst.py OK")

    asyncio.run(_smoke())
