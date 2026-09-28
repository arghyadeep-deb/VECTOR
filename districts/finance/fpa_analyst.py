"""
FP&A Analyst — rolling forecasts, variance analysis, OKR-linked budgeting.

Financial Planning & Analysis for Arghyadeep's projects and agency work.
Bridges numbers to business narrative — month-end close, forecast vs actuals.
"""

import asyncio
import json
import re
import datetime

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat
from core.loop.context_engine import ContextEngine

class FPAAnalyst(AgentBase):
    """
    Rolling forecasts, variance analysis, budget vs actuals, OKR-linked budgets.
    Analysis only — no financial transactions executed.
    """

    def __init__(self):
        super().__init__(agent_id="fpa_analyst_001", name="FPAAnalyst", district="finance")
        self.capabilities = ["analysis", "budget", "finance", "forecast", "fpa", "narrative", "okr_budget", "variance"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info("[VECTOR][fpa] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def variance_analysis(self, actuals: dict, budget: dict) -> dict:
        """Compare actuals vs budget, flag significant variances (>10%)."""
        variances = {}
        alerts = []
        for key in budget:
            actual_val = actuals.get(key, 0)
            budget_val = budget[key]
            diff = actual_val - budget_val
            pct = (diff / budget_val * 100) if budget_val != 0 else 0
            favorable = diff > 0  # revenue: positive = favorable; cost: positive = unfavorable
            variances[key] = {
                "actual": actual_val,
                "budget": budget_val,
                "variance": round(diff, 2),
                "variance_pct": round(pct, 1),
                "favorable": favorable,
            }
            if abs(pct) > 10:
                direction = "above" if diff > 0 else "below"
                alerts.append(f"{key}: {abs(pct):.1f}% {direction} budget ({diff:+,.0f})")

        total_actual = sum(actuals.values())
        total_budget = sum(budget.values())
        return {
            "variances": variances,
            "total_actual": round(total_actual, 2),
            "total_budget": round(total_budget, 2),
            "total_variance": round(total_actual - total_budget, 2),
            "total_variance_pct": round((total_actual - total_budget) / total_budget * 100, 1) if total_budget else 0,
            "alerts": alerts,
            "status": "on_track" if not alerts else "attention_needed",
        }

    def rolling_forecast(self, monthly_actuals: list[float], months_to_forecast: int = 3,
                         growth_rate: float = 0.05) -> dict:
        """Extend actuals into a rolling forecast using trend + growth rate."""
        if not monthly_actuals:
            return {"error": "Need at least 1 month of actuals"}

        # Simple trend: average of last 3 months + growth
        recent = monthly_actuals[-3:] if len(monthly_actuals) >= 3 else monthly_actuals
        base = sum(recent) / len(recent)
        forecast = []
        now = datetime.datetime.now()
        for i in range(1, months_to_forecast + 1):
            month = (now + datetime.timedelta(days=30 * i)).strftime("%Y-%m")
            projected = round(base * ((1 + growth_rate) ** i), 2)
            forecast.append({"month": month, "projected": projected})

        return {
            "historical_months": len(monthly_actuals),
            "base_monthly_avg": round(base, 2),
            "assumed_growth_rate_pct": growth_rate * 100,
            "forecast": forecast,
            "total_forecast": round(sum(f["projected"] for f in forecast), 2),
        }

    def budget_vs_okr(self, budget_items: list[dict], okrs: list[dict]) -> dict:
        """Link budget line items to OKRs — shows how spending maps to goals."""
        linked = []
        unlinked_budget = []
        for item in budget_items:
            matched_okr = None
            for okr in okrs:
                if any(kw.lower() in item.get("name", "").lower()
                       for kw in okr.get("keywords", [])):
                    matched_okr = okr.get("objective", "")
                    break
            if matched_okr:
                linked.append({**item, "linked_okr": matched_okr})
            else:
                unlinked_budget.append(item)

        total_linked = sum(i.get("amount", 0) for i in linked)
        total_budget = sum(i.get("amount", 0) for i in budget_items)
        return {
            "linked_items": linked,
            "unlinked_items": unlinked_budget,
            "total_budget": round(total_budget, 2),
            "okr_aligned_spend": round(total_linked, 2),
            "alignment_pct": round(total_linked / total_budget * 100, 1) if total_budget else 0,
            "recommendation": (
                "Good OKR alignment" if total_linked / max(total_budget, 1) > 0.7
                else "Review unlinked spend — ensure it supports strategic goals"
            ),
        }

    async def generate_monthly_narrative(self, month: str, variance_data: dict) -> str:
        """LLM generates exec-ready narrative for month-end close."""
        alerts_str = "; ".join(variance_data.get("alerts", []))
        body = (
            f"Write a concise (150-word) financial narrative for {month} month-end close.\n"
            f"Total variance: {variance_data.get('total_variance_pct', 0):+.1f}% vs budget\n"
            f"Key variances: {alerts_str or 'None significant'}\n"
            f"Status: {variance_data.get('status', 'on_track')}\n\n"
            f"Format: [Headline]. [2-3 sentences on key drivers]. [Forward-looking sentence].\n"
            f"Be direct, use business language, no fluff."
        )
        try:
            # RULE 1: session hydration before every LLM call.
            hydration = ContextEngine().session_hydration_prompt({"query": f"FP&A narrative {month}"})
            prompt = f"{hydration}\n\n{body}"
            return chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=20.0)
        except Exception as e:
            logger.warning("[VECTOR][fpa] narrative LLM failed: {}", e)
            status = variance_data.get("status", "on_track")
            return (
                f"{month} results: {status.upper().replace('_',' ')}. "
                f"Total variance {variance_data.get('total_variance_pct', 0):+.1f}% vs budget. "
                f"{'; '.join(variance_data.get('alerts', ['No major variances'])) or 'Performance on track.'}. "
                f"Monitoring continues into next month."
            )

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "variance")
        try:
            if task_type == "variance":
                result = self.variance_analysis(
                    task.get("actuals", {}), task.get("budget", {})
                )
                self.award_points(25, "variance_analyzed")
                return {"status": "ok", "variance": result}

            elif task_type == "forecast":
                result = self.rolling_forecast(
                    task.get("monthly_actuals", []),
                    task.get("months_to_forecast", 3),
                    task.get("growth_rate", 0.05),
                )
                self.award_points(25, "forecast_generated")
                return {"status": "ok", "forecast": result}

            elif task_type == "okr_budget":
                result = self.budget_vs_okr(
                    task.get("budget_items", []), task.get("okrs", [])
                )
                self.award_points(20, "okr_budget_linked")
                return {"status": "ok", "okr_alignment": result}

            elif task_type == "narrative":
                variance = task.get("variance_data", self.variance_analysis({}, {}))
                narrative = await self.generate_monthly_narrative(
                    task.get("month", datetime.datetime.now().strftime("%B %Y")), variance
                )
                self._get_memory().store(
                    event_type="fpa_narrative",
                    content=f"FP&A narrative: {task.get('month', 'current month')}",
                    tags=["finance", "fpa"],
                    source="fpa_analyst",
                )
                self.award_points(30, "narrative_generated")
                return {"status": "ok", "narrative": narrative}

            else:
                return {"status": "ok", "message": "FPAAnalyst ready. Tasks: variance, forecast, okr_budget, narrative"}

        except Exception as e:
            logger.error("[VECTOR][fpa] {}", e)
            self.deduct_points(30, "fpa_task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = FPAAnalyst()
        var = agent.variance_analysis(
            {"revenue": 45000, "salaries": 28000, "infrastructure": 5500},
            {"revenue": 50000, "salaries": 25000, "infrastructure": 5000},
        )
        print(f"[OK] variance: total_pct={var['total_variance_pct']}% alerts={len(var['alerts'])}")
        fc = agent.rolling_forecast([30000, 35000, 40000, 42000], months_to_forecast=3, growth_rate=0.08)
        print(f"[OK] forecast: base={fc['base_monthly_avg']:,.0f} total_3m={fc['total_forecast']:,.0f}")
        okr_res = agent.budget_vs_okr(
            [{"name": "AI infra", "amount": 10000}, {"name": "marketing", "amount": 5000}],
            [{"objective": "Ship AI product", "keywords": ["AI", "infra", "compute"]}],
        )
        print(f"[OK] okr_budget: alignment={okr_res['alignment_pct']}%")
        result = await agent.run({"type": "forecast", "monthly_actuals": [20000, 25000, 30000]})
        print(f"[OK] run: status={result['status']}")
        print("fpa_analyst.py OK")

    asyncio.run(_smoke())
