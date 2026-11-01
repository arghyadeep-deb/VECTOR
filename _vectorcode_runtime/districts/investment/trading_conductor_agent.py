"""
VECTOR TradingConductorAgent — District 17: investment
Multi-agent investment analysis pipeline. ANALYSIS ONLY — never executes real trades.

Orchestrates 12 specialized agents:
  Analysts:    market (technical) + sentiment + news + fundamentals
  Researchers: bull vs bear debate
  Manager:     research synthesis → investment plan
  Trader:      concrete proposal (entry/exit levels)
  Risk:        aggressive vs conservative vs neutral debate
  Portfolio:   final 5-tier decision (Buy/Overweight/Hold/Underweight/Sell)

Governor routes: investment_analysis, trading_analysis, market_research

Usage:
    agent = TradingConductorAgent()
    result = asyncio.run(agent.run({
        "params": {"action": "investment_analysis", "ticker": "NVDA", "date": "2026-05-18"}
    }))
    print(result["decision"])
"""

from __future__ import annotations

import asyncio
import sys
import uuid
import concurrent.futures as _cf
from datetime import datetime
from typing import Optional

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from loguru import logger


def _llm(prompt: str, max_tokens: int = 700, temperature: float = 0.6) -> str:
    from core.inference.provider_client import ProviderClient as _PC
    async def _call():
        r = await _PC().chat(
            messages=[{"role": "user", "content": prompt}],
            model="domain:finance.analysis",   # gpt-5 → zai-glm-4.7 → DeepSeek-R1 → ollama
            tier="reasoning", temperature=temperature, max_tokens=max_tokens,
            caller_id="trading_conductor_agent",
        )
        return r.content
    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _call()).result(timeout=90)

class TradingConductorAgent(AgentBase):
    """
    VECTOR's multi-agent investment analysis conductor.
    Mirrors a real trading desk: analysts → debate → risk assessment → portfolio decision.
    ANALYSIS ONLY — never executes real trades (per VECTOR investment district rules).
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="TradingConductorAgent",
            district="investment",
            generation=generation,
        )
        self.capabilities = ["execute_trade", "investment", "investment_analysis", "market_research", "paper_trade", "past_performance", "place_order", "trading"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory  = EpisodicMemory()
        self._context = ContextEngine()
        self._graph   = None   # lazy-loaded VectorTradingGraph
        logger.info("[VECTOR][trading_conductor] ready gen={} hp={}", generation, self.health_points)

    def _get_graph(self):
        """Lazy-load the VectorTradingGraph (avoids LangChain import at module load)."""
        if self._graph is None:
            try:
                from core.trading.graph.trading_graph import VectorTradingGraph
                trading_cfg = CONFIG.get("trading", {})
                cfg = {
                    "llm_provider":          trading_cfg.get("llm_provider", "openai"),
                    "deep_think_llm":        trading_cfg.get("deep_think_llm", "gpt-5.4"),
                    "quick_think_llm":       trading_cfg.get("quick_think_llm", "gpt-5.4-mini"),
                    "max_debate_rounds":     trading_cfg.get("max_debate_rounds", 1),
                    "max_risk_discuss_rounds": trading_cfg.get("max_risk_rounds", 1),
                    "checkpoint_enabled":    trading_cfg.get("checkpoint_enabled", False),
                    "output_language":       trading_cfg.get("output_language", "English"),
                    "data_vendors":          trading_cfg.get("data_vendors", {}),
                    "results_dir":           trading_cfg.get("results_dir", ""),
                    "data_cache_dir":        trading_cfg.get("cache_dir", ""),
                    "memory_log_path":       trading_cfg.get("memory_log_path", ""),
                }
                self._graph = VectorTradingGraph(config=cfg)
            except ImportError as e:
                logger.error("[VECTOR][trading_conductor] import error: {} — install langgraph, langchain", e)
                raise
        return self._graph

    # ── Actions ───────────────────────────────────────────────────────────────

    async def run_analysis(
        self,
        ticker: str,
        date: str | None = None,
        analysts: list[str] | None = None,
    ) -> dict:
        """
        Run full multi-agent investment analysis for a ticker.
        ANALYSIS ONLY — returns recommendation, never executes trades.

        Args:
            ticker: Stock ticker symbol (e.g. NVDA, RELIANCE.NS)
            date: Trade date YYYY-MM-DD (defaults to today)
            analysts: Subset of ["market", "social", "news", "fundamentals"]

        Returns:
            {ticker, date, decision, rating, rationale, analysts_used}
        """
        trade_date = date or datetime.now().strftime("%Y-%m-%d")
        analysts_used = analysts or ["market", "social", "news", "fundamentals"]
        logger.info("[VECTOR][trading_conductor] analyzing {} on {}", ticker, trade_date)

        loop = asyncio.get_event_loop()
        try:
            graph = self._get_graph()
            # VectorTradingGraph.propagate() is sync — run in executor
            final_state, decision = await loop.run_in_executor(
                None, graph.propagate, ticker, trade_date
            )
        except Exception as e:
            logger.error("[VECTOR][trading_conductor] analysis failed: {}", e)
            return {"status": "error", "ticker": ticker, "date": trade_date, "error": str(e)}

        # Extract structured result
        portfolio_decision = final_state.get("final_trade_decision", {})
        rating = getattr(portfolio_decision, "rating", None)
        rationale = getattr(portfolio_decision, "rationale", decision or "")

        result = {
            "status":        "ok",
            "ticker":        ticker,
            "date":          trade_date,
            "decision":      decision or str(rating),
            "rating":        str(rating) if rating else "Hold",
            "rationale":     rationale,
            "analysts_used": analysts_used,
            "note":          "ANALYSIS ONLY — not financial advice, never real trade execution",
        }

        # Store in episodic memory
        self._memory.store(
            event_type="investment_analysis",
            content=f"TradingConductor: {ticker} {trade_date} → {result['rating']} ({result['decision'][:60]})",
            tags=["investment", "analysis", ticker, result["rating"]],
            source="trading_conductor_agent",
        )
        self.award_points(30, f"investment analysis: {ticker}")
        return result

    async def get_past_performance(self, ticker: str) -> dict:
        """Retrieve past analysis decisions and outcomes for a ticker."""
        try:
            from core.trading.agents.utils.memory import TradingMemoryLog
            trading_cfg = CONFIG.get("trading", {})
            mem = TradingMemoryLog(log_path=trading_cfg.get("memory_log_path", ""))
            context = mem.get_past_context(ticker, n_same=10, n_cross=3)
            return {"ticker": ticker, "past_context": context}
        except Exception as e:
            return {"ticker": ticker, "error": str(e)}

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        # 2026-07-29: was `p.get("action", "investment_analysis")` — never
        # read task["type"] at all (governor.py's real dispatch contract),
        # so every real chat/governor dispatch silently ran the full
        # LangGraph multi-agent debate pipeline for a hardcoded NVDA ticker
        # regardless of what was actually asked — same bug class as
        # stock_analyst.py's pre-fix quote default (KNOWN_ISSUES.md
        # #1/#14/#15/#21/#33/#36), and more expensive since it triggers a
        # full deep-think LLM debate for the wrong ticker every time.
        action = task.get("type") or p.get("action", "investment_analysis")

        if action in ("investment_analysis", "trading_analysis"):
            return await self.run_analysis(
                ticker=p.get("ticker", p.get("symbol", "NVDA")),
                date=p.get("date"),
                analysts=p.get("analysts"),
            )
        elif action == "market_research":
            # Quick analysis — analysts only, no debate rounds
            return await self.run_analysis(
                ticker=p.get("ticker", p.get("symbol", "NVDA")),
                date=p.get("date"),
                analysts=p.get("analysts", ["market", "fundamentals"]),
            )
        elif action == "past_performance":
            return await self.get_past_performance(p.get("ticker", "NVDA"))

        query = p.get("query") or p.get("content") or task.get("query") or task.get("prompt")
        if query:
            # Free-text chat query with no ticker/action specified: answer
            # conversationally rather than guessing a ticker and burning a
            # full multi-agent LangGraph debate run on the wrong stock.
            try:
                prompt = (
                    "You are VECTOR's TradingConductorAgent, an investment-district "
                    "agent that orchestrates a 12-agent research desk (technical/"
                    "sentiment/news/fundamentals analysts, bull-vs-bear researchers, "
                    "risk debate, portfolio committee) to produce a Buy/Overweight/"
                    "Hold/Underweight/Sell rating for a named ticker. ANALYSIS ONLY "
                    "— you never execute real trades. If the user wants a full "
                    "multi-agent report, tell them to name a specific ticker.\n\n"
                    f"Answer the user's question directly and specifically:\n{query}"
                )
                answer = _llm(prompt, max_tokens=700, temperature=0.6)
                return {"status": "ok", "response": answer}
            except Exception as e:
                logger.error("[VECTOR][trading_conductor] free-text fallback failed: {}", e)

        return {"status": "error", "error": f"unknown action: {action}"}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][trading_conductor] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][trading_conductor] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = TradingConductorAgent()
        assert agent.health_points == 500
        assert agent.name == "TradingConductorAgent"
        assert agent.district == "investment"

        # Config check (no LLM call needed)
        trading_cfg = CONFIG.get("trading", {})
        assert "llm_provider" in trading_cfg
        assert "data_vendors" in trading_cfg

        print(f"OK trading_conductor_agent.py HP={agent.health_points}")
        print(f"  provider={trading_cfg['llm_provider']}")
        print(f"  debate_rounds={trading_cfg['max_debate_rounds']}")
        print(f"  data_vendors={trading_cfg['data_vendors']}")
        print(f"  Full analysis: await agent.run({{'params': {{'action': 'investment_analysis', 'ticker': 'NVDA'}}}})")
        print(f"  (requires langgraph + langchain + yfinance installed)")

    asyncio.run(_smoke())
