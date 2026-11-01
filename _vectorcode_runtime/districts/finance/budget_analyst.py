
import sys
import uuid
import asyncio
import datetime
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger

_REASONING = CONFIG["models"]["reasoning"]

# Monthly budget targets (INR) — defaults, overridable via CONFIG
_DEFAULT_BUDGETS: dict[str, float] = {
    "food": 3000,
    "transport": 1000,
    "education": 2000,
    "utilities": 800,
    "shopping": 1500,
    "health": 500,
    "entertainment": 500,
    "other": 1000,
}

class BudgetAnalyst(AgentBase):
    """
    Compares actual spending vs budget targets.
    Generates over-budget alerts and savings recommendations.
    RULE 11: vector-reasoning (local), not Claude API.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="BudgetAnalyst",
            district="finance",
            generation=generation,
        )
        self.capabilities = ["budget", "budget_check", "budget_status", "finance", "money"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        self._budgets: dict[str, float] = dict(
            CONFIG.get("finance", {}).get("budgets", _DEFAULT_BUDGETS)
        )
        logger.info(f"[VECTOR][budget_analyst] ready gen={generation}")
        # Phase 2B: subscribe to finance events
        self.subscribe_to("task_completed")
        self.subscribe_to("memory_stored")

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: Flag large transactions from event data."""
        await super().handle_event(event)
        et = event.get("event_type", "")
        data = event.get("data", {})
        if "finance" in str(data).lower() or "transaction" in str(data).lower():
            try:
                logger.info(f"[VECTOR][budget_analyst] event-triggered review: {et}")
                await self.run({"type": "analyze_spending", "params": {"context": str(data)[:200]}})
            except Exception as e:
                logger.debug(f"[VECTOR][budget_analyst] handle_event failed: {e}")
        return {"status": "handled", "agent": self.name, "event": et}

    def _fetch_category_spend(self, days: int = 30) -> dict[str, float] | None:
        import re
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        try:
            cur = self._memory.conn.cursor()
            cur.execute(
                "SELECT content FROM episodic_memory "
                "WHERE event_type = 'upi_transaction' AND timestamp > ?",
                (cutoff,),
            )
            rows = cur.fetchall()
        except Exception as e:
            logger.warning(f"[VECTOR][budget_analyst] fetch failed: {e}")
            return None

        by_cat: dict[str, float] = {}
        for (content,) in rows:
            if "DEBIT" not in content:
                continue
            m_amt = re.search(r"Rs\.([\d.]+)", content)
            m_cat = re.search(r"\[(\w+)\]", content)
            if m_amt and m_cat:
                cat = m_cat.group(1)
                amt = float(m_amt.group(1))
                by_cat[cat] = by_cat.get(cat, 0.0) + amt
        return {k: round(v, 2) for k, v in by_cat.items()}

    def _over_budget_categories(self, spend: dict[str, float]) -> list[dict]:
        over = []
        for cat, budget in self._budgets.items():
            actual = spend.get(cat, 0.0)
            if actual > budget:
                over.append({
                    "category": cat,
                    "budget": budget,
                    "actual": actual,
                    "overage": round(actual - budget, 2),
                    "pct": round((actual - budget) / budget * 100, 1),
                })
        return sorted(over, key=lambda x: -x["overage"])

    def _get_recommendations(self, over_budget: list[dict], hydration: str) -> str:
        if not over_budget:
            return "All categories within budget."
        cats = ", ".join(f"{o['category']} (+Rs.{o['overage']})" for o in over_budget[:3])
        prompt = (
            f"Arghyadeep overspent in: {cats}.\n"
            "Give 3 specific, practical tips to reduce spending in these categories. "
            "He is a student on a tight budget. Be direct."
        )
        try:
            from core.inference.vectorcode_llm import chat
            text = chat(model=_REASONING, messages=[{"role": "system", "content": hydration}, {"role": "user", "content": prompt}], timeout=60.0)
            if not text:
                raise ValueError("empty response")
            return text
        except Exception as e:
            logger.warning(f"[VECTOR][budget_analyst] LLM unavailable: {e}")
            return "Cook at home. Use student discounts. Audit subscriptions."

    async def analyse(self) -> str | None:
        month_label = datetime.date.today().strftime("%Y-%m")
        spend = self._fetch_category_spend(days=30)
        if spend is None:
            logger.error(
                "[VECTOR][budget_analyst] analysis unavailable: transaction fetch failed"
            )
            self.deduct_points(5, "transaction fetch failed")
            return None
        over_budget = self._over_budget_categories(spend)

        hydration = self._context.session_hydration_prompt()
        recommendations = self._get_recommendations(over_budget, hydration)

        total_budget = sum(self._budgets.values())
        total_spent = sum(spend.values())

        budget_rows = "\n".join(
            f"| {cat.capitalize()} | Rs.{self._budgets.get(cat, 0):.0f} | "
            f"Rs.{spend.get(cat, 0):.2f} | "
            f"{'OVER' if spend.get(cat, 0) > self._budgets.get(cat, 0) else 'OK'} |"
            for cat in sorted(set(list(self._budgets.keys()) + list(spend.keys())))
        )

        report = (
            f"# Budget Analysis — {month_label}\n\n"
            f"**Total budget:** Rs.{total_budget:.0f}\n"
            f"**Total spent:** Rs.{total_spent:.2f}\n"
            f"**Status:** {'OVER BUDGET' if total_spent > total_budget else 'Within budget'}\n\n"
            f"## Category vs Budget\n"
            f"| Category | Budget | Spent | Status |\n"
            f"|----------|--------|-------|--------|\n"
            f"{budget_rows}\n\n"
        )
        if over_budget:
            report += f"## Over-Budget Alerts\n"
            for o in over_budget:
                report += f"- **{o['category'].capitalize()}**: Rs.{o['actual']:.2f} vs Rs.{o['budget']:.0f} (+{o['pct']}%)\n"
            report += f"\n## Recommendations\n{recommendations}\n"
        report += f"\n---\n*auto-generated by BudgetAnalyst*"

        try:
            self._obsidian.write_note(
                title=f"Budget Analysis — {month_label}",
                content=report,
                folder="Finance",
                tags=["finance", "budget", "vector"],
            )
            self._memory.store(
                event_type="budget_analysis",
                content=f"Budget analysis {month_label}: spent Rs.{total_spent:.2f} / Rs.{total_budget:.0f}",
                tags=["finance", "budget"],
                source="budget_analyst",
            )
            for o in over_budget:
                self._memory.remember(
                    key=f"over_budget:{month_label}:{o['category']}",
                    value=f"+Rs.{o['overage']} ({o['pct']}%)",
                    category="finance_alert",
                    confidence=0.9,
                )
            self._memory.store_chain(
                situation="budget_analysis",
                goal_ids=["financial_awareness"],
                steps=["fetch_spend", "compare_budgets", "llm_recommendations", "obsidian_write"],
                action="analyse",
                outcome=f"Rs.{total_spent:.2f} spent; {len(over_budget)} over-budget categories",
                reward=0.8,
            )
            self.award_points(25, f"budget analysis {month_label}")
            logger.info(f"[VECTOR][budget_analyst] done: Rs.{total_spent:.2f} spent, {len(over_budget)} over-budget")
            return report
        except Exception as e:
            logger.error(f"[VECTOR][budget_analyst] write failed: {e}")
            self.deduct_points(5, "write failed")
            return None

    async def run(self, task: dict) -> dict:
        # 2026-07-22: analyse() always built a full markdown report (spend
        # vs budget, over-budget alerts, LLM recommendations) but run() used
        # to discard it and return a bare {"status": "ok"} — none of the 6
        # keys avatar/avatar_voice.py::_extract_text() checks, so every
        # dispatch here rendered as a "Task completed — status: ok." stub
        # even though real analysis had just been computed and written to
        # Obsidian (KNOWN_ISSUES.md #1 pattern). Now returns the report text
        # itself via `response`.
        report = await self.analyse()
        if report:
            return {"status": "ok", "response": report, "agent": self.name}
        return {"status": "error", "agent": self.name}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][budget_analyst] run_forever — monthly on 1st at 09:30")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.day == 1 and now.hour == 9 and 30 <= now.minute < 35:
                    await self.analyse()
            except Exception as e:
                logger.error(f"[VECTOR][budget_analyst] tick: {e}")
                self.deduct_points(5, "tick error")
            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(60)
        logger.warning("[VECTOR][budget_analyst] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    async def _smoke():
        bot = BudgetAnalyst()
        assert bot.health_points == 500
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Finance").mkdir()
            bot._obsidian._vault = vault
            ok = await bot.analyse()
        print(f"OK budget_analyst.py HP={bot.health_points} ok={ok}")

    asyncio.run(_smoke())
