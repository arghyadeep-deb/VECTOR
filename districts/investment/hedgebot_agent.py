"""
VECTOR HedgeBotAgent — District 17: investment
Autonomous multi-agent hedge fund pipeline integrated into VECTOR.

Five-agent sequential pipeline:
  Trading Director → Quant-Analyst → Risk-Manager → Execution-Agent → Sentiment-Agent

Covers equities (Yahoo Finance, Polygon/Massive) and Solana DEX (Jupiter Protocol).
Live Solana execution requires SOLANA_PRIVATE_KEY + JUPITER_API_KEY in .env.

Governor routes:
  hedge_run, hedge_trade, solana_order, solana_execute,
  solana_holdings, token_search, token_price
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from loguru import logger


class HedgeBotAgent(AgentBase):
    """
    VECTOR's autonomous hedge fund agent.
    Runs a 5-agent pipeline to analyse markets, size positions, and
    optionally execute trades on Solana via Jupiter Protocol.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="HedgeBotAgent",
            district="investment",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        logger.info("[VECTOR][hedgebot_agent] ready gen={} hp={}", generation, self.health_points)

    # ── Actions ───────────────────────────────────────────────────────────────

    async def hedge_run(self, task: str, output_type: str = "str") -> dict:
        """
        Run the full 5-agent hedge fund pipeline on a plain-English task.
        The director discovers relevant tickers; no predefined list needed.

        task examples:
          "Analyse NVDA and TSLA for momentum play this week"
          "Find undervalued semiconductor stocks with strong earnings"
          "Should I buy SOL given current market conditions?"
        """
        logger.info("[VECTOR][hedgebot_agent] hedge_run: {}", task[:60])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from districts.investment.vector_hedgebot.orchestrator import VECTORHedge
                cfg = CONFIG.get("vector_hedgebot", {}) if isinstance(CONFIG, dict) else {}
                hedge = VECTORHedge(
                    output_dir=cfg.get("output_dir", "outputs"),
                    output_type=output_type,
                )
                result = hedge.run(task=task)
                return {"status": "ok", "task": task, "result": result}
            except Exception as e:
                logger.warning("[VECTOR][hedgebot_agent] hedge_run error: {}", e)
                return {"status": "error", "error": str(e), "task": task}

        result = await loop.run_in_executor(None, _run)
        self._memory.store(
            event_type="hedge_run",
            content=f"HedgeBotAgent pipeline: {task[:80]} → {result.get('status')}",
            tags=["investment", "hedge", "pipeline"],
            source="hedgebot_agent",
        )
        if result.get("status") == "ok":
            self.award_points(40, f"hedge pipeline: {task[:40]}")
        return result

    async def token_search(self, query: str) -> dict:
        """Search Solana tokens by symbol, name, or mint address via Jupiter."""
        logger.info("[VECTOR][hedgebot_agent] token_search: {}", query)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from districts.investment.vector_hedgebot.tools.jupiter_search import search_tokens
                result = search_tokens(query)
                return {"status": "ok", "query": query, "result": result}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        return await loop.run_in_executor(None, _run)

    async def token_price(self, mint_addresses: str | list) -> dict:
        """Get USD prices for Solana token mint addresses via Jupiter Price API."""
        logger.info("[VECTOR][hedgebot_agent] token_price: {}", mint_addresses)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from districts.investment.vector_hedgebot.tools.jupiter_price import get_token_price
                result = get_token_price(mint_addresses)
                return {"status": "ok", "result": result}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        return await loop.run_in_executor(None, _run)

    async def solana_holdings(self, wallet_address: str) -> dict:
        """Get token balances and SOL for a Solana wallet via Jupiter Ultra."""
        logger.info("[VECTOR][hedgebot_agent] solana_holdings: {}", wallet_address[:20])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from districts.investment.vector_hedgebot.tools.jupiter_ultra import get_holdings
                result = get_holdings(wallet_address)
                return {"status": "ok", "wallet": wallet_address, "result": result}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        return await loop.run_in_executor(None, _run)

    async def solana_order(
        self, input_mint: str, output_mint: str, amount: str
    ) -> dict:
        """
        Get an unsigned Solana swap order from Jupiter Ultra.
        Requires SOLANA_PRIVATE_KEY + JUPITER_API_KEY in .env.
        Pass the returned transaction + requestId to solana_execute().
        """
        logger.info("[VECTOR][hedgebot_agent] solana_order: {} -> {}", input_mint[:8], output_mint[:8])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                cfg = CONFIG.get("vector_hedgebot", {}) if isinstance(CONFIG, dict) else {}
                if not cfg.get("live_trading") and not cfg.get("solana_private_key"):
                    return {
                        "status": "disabled",
                        "note": "Set live_trading=True + SOLANA_PRIVATE_KEY to enable Solana execution",
                    }
                from districts.investment.vector_hedgebot.tools.jupiter_ultra import get_order
                result = get_order(input_mint, output_mint, amount)
                return {"status": "ok", "result": result}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        return await loop.run_in_executor(None, _run)

    async def solana_execute(self, unsigned_transaction: str, request_id: str) -> dict:
        """
        Sign and execute a Solana swap via Jupiter Ultra.
        Requires SOLANA_PRIVATE_KEY. Use solana_order() to get the transaction first.
        """
        logger.info("[VECTOR][hedgebot_agent] solana_execute: reqId={}", request_id[:12])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                cfg = CONFIG.get("vector_hedgebot", {}) if isinstance(CONFIG, dict) else {}
                if not cfg.get("live_trading") and not cfg.get("solana_private_key"):
                    return {
                        "status": "disabled",
                        "note": "Set live_trading=True + SOLANA_PRIVATE_KEY to enable Solana execution",
                    }
                from districts.investment.vector_hedgebot.tools.jupiter_ultra import execute_trade
                result = execute_trade(unsigned_transaction, request_id)
                return {"status": "ok", "result": result}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(50, "solana trade executed")
        return result

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        action = p.get("action", "hedge_run")

        if action in ("hedge_run", "hedge_trade"):
            return await self.hedge_run(
                task=p.get("task", p.get("query", "")),
                output_type=p.get("output_type", "str"),
            )
        elif action == "token_search":
            return await self.token_search(p.get("query", ""))
        elif action == "token_price":
            return await self.token_price(p.get("mint_addresses", p.get("ids", "")))
        elif action == "solana_holdings":
            return await self.solana_holdings(p.get("wallet_address", ""))
        elif action == "solana_order":
            return await self.solana_order(
                p.get("input_mint", ""),
                p.get("output_mint", ""),
                p.get("amount", ""),
            )
        elif action == "solana_execute":
            return await self.solana_execute(
                p.get("unsigned_transaction", ""),
                p.get("request_id", ""),
            )
        return {"status": "error", "error": f"unknown action: {action}"}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][hedgebot_agent] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][hedgebot_agent] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = HedgeBotAgent()
        assert agent.health_points == 500
        assert agent.name == "HedgeBotAgent"
        assert agent.district == "investment"

        # Verify tools can be imported (no API call)
        try:
            from districts.investment.vector_hedgebot.tools.jupiter_search import search_tokens
            from districts.investment.vector_hedgebot.tools.jupiter_price import get_token_price
            from districts.investment.vector_hedgebot.tools.jupiter_ultra import get_holdings, get_order, execute_trade
            from districts.investment.vector_hedgebot.tools.yahoo import get_stock_quote, get_all_stock_data
            from districts.investment.vector_hedgebot.tools.polygon import get_ticker_overview
            from districts.investment.vector_hedgebot.tools.exa_search import exa_search
            from districts.investment.vector_hedgebot.orchestrator import VECTORHedge
            from districts.investment.vector_hedgebot.agents import director_agent, quant_agent, risk_agent, execution_agent, sentiment_agent
            tools_ok = True
        except ImportError as e:
            tools_ok = False
            print(f"  Import error (swarms not installed?): {e}")

        print(f"OK hedgebot_agent.py HP={agent.health_points}")
        print(f"  district: {agent.district}")
        print(f"  tools importable: {tools_ok}")
        print(f"  actions: hedge_run, token_search, token_price,")
        print(f"           solana_holdings, solana_order, solana_execute")

    asyncio.run(_smoke())
