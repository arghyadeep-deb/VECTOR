"""
LLM Cost Tracker — token usage and cost tracking for all VECTOR LLM calls.

Wraps vectorcode/src/agent/usage_pricing.py concept.
Tracks per-district token consumption, costs by provider, budget alerts.
Plugs into vectorcode_llm's session usage accumulator.
"""

import asyncio
import datetime

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory

# Budget limit — alert when session cost exceeds this (USD)
DEFAULT_BUDGET_USD = CONFIG.get("cost", {}).get("max_budget_usd", 1.0)

# Pricing per 1M tokens (USD) — mirrors vectorcode_llm._PRICING
_PRICING = {
    "ollama":             {"input": 0.0,    "output": 0.0},
    "gemini-2.0-flash":   {"input": 0.10,   "output": 0.40},
    "gemini-1.5-flash":   {"input": 0.075,  "output": 0.30},
    "claude-haiku-4-5":   {"input": 0.80,   "output": 4.0},
    "claude-sonnet-4-6":  {"input": 3.0,    "output": 15.0},
    "claude-opus-4-7":    {"input": 15.0,   "output": 75.0},
}

class LLMCostTracker(AgentBase):
    """
    Tracks LLM token usage and costs across all VECTOR providers.
    Issues budget alerts, generates cost reports, projects monthly spend.
    """

    def __init__(self):
        super().__init__(agent_id="llm_cost_tracker_001",
                         name="LLMCostTracker", district="finance")
        self.capabilities = ["budget", "budget_check", "budget_record", "cost", "estimate", "finance", "project"]
        self._memory: EpisodicMemory | None = None
        self._budget_usd = DEFAULT_BUDGET_USD
        logger.info("[VECTOR][cost_tracker] initialized, budget=${}", self._budget_usd)

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def get_session_report(self) -> dict:
        """Pull live session usage from vectorcode_llm accumulator."""
        try:
            from core.inference.vectorcode_llm import get_session_usage
            usage = get_session_usage()
        except Exception as e:
            logger.warning("[VECTOR][cost_tracker] could not read session usage: {}", e)
            usage = {"total_calls": 0, "total_cost_usd": 0.0, "by_provider": {}}

        total_cost = usage.get("total_cost_usd", 0.0)
        budget_used_pct = (total_cost / self._budget_usd * 100) if self._budget_usd > 0 else 0
        alert = budget_used_pct >= 80

        return {
            "session": usage,
            "budget_usd": self._budget_usd,
            "budget_used_pct": round(budget_used_pct, 1),
            "budget_alert": alert,
            "cheapest_provider": self._cheapest_available_provider(),
            "recommendation": (
                f"⚠️ {budget_used_pct:.0f}% of ${self._budget_usd} budget used — switch to Ollama"
                if alert
                else f"${total_cost:.4f} used of ${self._budget_usd} budget"
            ),
        }

    def _cheapest_available_provider(self) -> str:
        """Return the cheapest available provider (for cost-sensitive routing)."""
        import os
        if True:  # Ollama always available
            return "ollama"
        if CONFIG.get("api_keys", {}).get("gemini_key"):
            return "gemini"
        return "ollama"

    def estimate_call_cost(self, model: str, prompt_chars: int,
                           expected_output_chars: int = 500) -> dict:
        """Pre-flight cost estimate before making a LLM call."""
        input_tok = max(1, prompt_chars // 4)
        output_tok = max(1, expected_output_chars // 4)
        pricing = _PRICING.get(model, {"input": 1.0, "output": 3.0})
        cost = (input_tok * pricing["input"] + output_tok * pricing["output"]) / 1_000_000
        return {
            "model": model,
            "input_tokens_est": input_tok,
            "output_tokens_est": output_tok,
            "cost_usd_est": round(cost, 8),
            "cost_inr_est": round(cost * 84, 6),  # approximate INR
            "is_free": pricing["input"] == 0.0,
        }

    def generate_cost_report(self) -> str:
        """Markdown cost report for current session."""
        report = self.get_session_report()
        session = report["session"]
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# VECTOR LLM Cost Report — {ts}",
            f"\n**Session total:** ${session.get('total_cost_usd', 0):.6f} "
            f"({report['budget_used_pct']}% of ${report['budget_usd']} budget)",
            f"**Total calls:** {session.get('total_calls', 0)}",
            f"\n## By Provider",
        ]
        for provider, data in session.get("by_provider", {}).items():
            lines.append(
                f"- **{provider}**: {data['calls']} calls, "
                f"{data['tokens']:,} tokens, ${data['cost_usd']:.6f}"
            )
        if not session.get("by_provider"):
            lines.append("- No cloud provider calls this session (all local Ollama)")
        lines.append(f"\n## Recommendation\n{report['recommendation']}")
        lines.append(f"\n## Pricing Reference")
        for model, p in _PRICING.items():
            if p["input"] > 0:
                lines.append(f"- {model}: ${p['input']}/M in, ${p['output']}/M out")
        return "\n".join(lines)

    def project_monthly_cost(self, daily_calls: int, avg_prompt_chars: int = 1000,
                              model: str = "gemini-2.0-flash") -> dict:
        """Project monthly cost based on call volume."""
        est = self.estimate_call_cost(model, avg_prompt_chars)
        daily_cost = est["cost_usd_est"] * daily_calls
        return {
            "model": model,
            "daily_calls": daily_calls,
            "daily_cost_usd": round(daily_cost, 4),
            "monthly_cost_usd": round(daily_cost * 30, 2),
            "monthly_cost_inr": round(daily_cost * 30 * 84, 0),
            "yearly_cost_usd": round(daily_cost * 365, 2),
            "is_within_free_tier": model.startswith("gemini") and daily_calls <= 1000,
            "recommendation": (
                "Within Gemini free tier (1M tokens/day)"
                if model.startswith("gemini") and daily_calls <= 1000
                else f"${daily_cost * 30:.2f}/month — consider switching to Ollama or Gemini free"
            ),
        }

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        # 2026-09-30 (Codex third independent review, same cycle): capture
        # task_type from the UNMERGED task first -- if a nested params dict
        # happens to carry its own "type" key (a real field name for some
        # capabilities, not just VECTOR's own dispatch key), merging params
        # over task before reading task_type would let params["type"]
        # silently hijack routing. See districts/communications/email_agent.py's
        # identical fix for the full evidence.
        task_type = task.get("type", "report")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "estimate":
                result = self.estimate_call_cost(
                    task.get("model", "ollama"),
                    task.get("prompt_chars", 1000),
                    task.get("output_chars", 500),
                )
                self.award_points(5, "cost_estimated")
                return {"status": "ok", "estimate": result}

            elif task_type == "project":
                result = self.project_monthly_cost(
                    task.get("daily_calls", 100),
                    task.get("avg_prompt_chars", 1000),
                    task.get("model", "gemini-2.0-flash"),
                )
                self.award_points(10, "cost_projected")
                return {"status": "ok", "projection": result}

            else:  # report
                report_dict = self.get_session_report()
                report_md = self.generate_cost_report()
                self._get_memory().store(
                    event_type="llm_cost_report",
                    content=f"LLM costs: {report_dict['session'].get('total_calls',0)} calls, "
                            f"${report_dict['session'].get('total_cost_usd',0):.4f}",
                    tags=["finance", "llm", "cost"],
                    source="llm_cost_tracker",
                )
                if report_dict["budget_alert"]:
                    logger.warning("[VECTOR][cost_tracker] BUDGET ALERT: {}% used",
                                   report_dict["budget_used_pct"])
                self.award_points(15, "cost_report_generated")
                return {"status": "ok", "report": report_dict, "markdown": report_md}

        except Exception as e:
            logger.error("[VECTOR][cost_tracker] {}", e)
            self.deduct_points(20, "cost_tracking_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = LLMCostTracker()
        est = agent.estimate_call_cost("claude-sonnet-4-6", prompt_chars=2000)
        print(f"[OK] estimate: model={est['model']} cost=${est['cost_usd_est']:.8f} free={est['is_free']}")
        proj = agent.project_monthly_cost(daily_calls=50, model="gemini-2.0-flash")
        print(f"[OK] project: monthly=${proj['monthly_cost_usd']} free_tier={proj['is_within_free_tier']}")
        report = agent.get_session_report()
        print(f"[OK] session: calls={report['session']['total_calls']} budget_pct={report['budget_used_pct']}%")
        result = await agent.run({"type": "report"})
        print(f"[OK] run: status={result['status']}")
        print("llm_cost_tracker.py OK")

    asyncio.run(_smoke())
