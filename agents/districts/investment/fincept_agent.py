"""
VECTOR FinceptAgent — District 17: investment
Financial intelligence suite — investor personas, corporate finance, alpha discovery,
geopolitics analysis, and the native C++/Qt6 financial terminal.

Governor routes: investor_analysis, corporate_finance, alpha_discovery,
                 geopolitics_analysis, quant_backtest, launch_terminal

ANALYSIS ONLY for financial decisions — never executes real trades autonomously.

Usage:
    agent = FinceptAgent()
    result = asyncio.run(agent.run({
        "params": {"action": "investor_analysis",
                   "ticker": "NVDA", "persona": "buffett"}
    }))
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from core.fincept.terminal_launcher import FinceptTerminalLauncher
from loguru import logger


class FinceptAgent(AgentBase):
    """
    VECTOR's financial intelligence agent — powered by the Fincept suite.
    Provides investor persona analysis, corporate finance models, alpha
    discovery, geopolitics analysis, and the native C++/Qt6 terminal.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="FinceptAgent",
            district="investment",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory   = EpisodicMemory()
        self._context  = ContextEngine()
        self._launcher = FinceptTerminalLauncher()
        logger.info("[VECTOR][fincept_agent] ready gen={} hp={}", generation, self.health_points)

    # ── Actions ───────────────────────────────────────────────────────────────

    async def investor_analysis(
        self,
        ticker: str,
        persona: str = "buffett",
        date: str | None = None,
    ) -> dict:
        """
        Run an investor persona analysis on a ticker.
        Personas: buffett, graham, lynch, munger, klarman, marks, renaissance
        """
        logger.info("[VECTOR][fincept_agent] {} analysis: {}", persona, ticker)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                # Try to load the specific investor agent from TraderInvestorsAgent
                sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
                from core.fincept.agents.finagent_core.core_agent import CoreAgent
                cfg = CONFIG.get("fincept", {})
                agent = CoreAgent(persona=persona, config=cfg)
                return agent.analyze(ticker=ticker, date=date)
            except ImportError:
                return {"status": "deps_missing", "ticker": ticker, "persona": persona,
                        "note": "Install finagent dependencies: pip install agno phidata"}
            except Exception as e:
                return {"status": "error", "error": str(e), "ticker": ticker}

        result = await loop.run_in_executor(None, _run)
        self._memory.store(
            event_type="investor_analysis",
            content=f"FinceptAgent {persona} analysis: {ticker} → {result.get('status', 'ok')}",
            tags=["investment", "analysis", ticker, persona],
            source="fincept_agent",
        )
        if result.get("status") not in ("error", "deps_missing"):
            self.award_points(25, f"investor analysis: {persona}/{ticker}")
        return result

    async def corporate_finance(
        self,
        analysis_type: str = "dcf",
        ticker: str | None = None,
        data: dict | None = None,
    ) -> dict:
        """
        Corporate finance analytics: dcf, lbo, merger, startup_valuation, fairness_opinion.
        """
        logger.info("[VECTOR][fincept_agent] corporate finance: {} {}", analysis_type, ticker or "")
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from core.fincept.Analytics.corporateFinance import valuation
                result = valuation.run(analysis_type=analysis_type, ticker=ticker, data=data or {})
                return {"status": "ok", "analysis_type": analysis_type, "result": result}
            except ImportError:
                # Try DCF from equityInvestment as fallback
                try:
                    from core.fincept.Analytics.equityInvestment.equity_valuation import dcf_model
                    result = dcf_model(ticker=ticker)
                    return {"status": "ok", "analysis_type": "dcf", "result": result}
                except Exception as e2:
                    return {"status": "error", "error": str(e2)}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(20, f"corporate finance: {analysis_type}")
        return result

    async def alpha_discovery(
        self,
        universe: list[str] | None = None,
        strategy: str = "momentum",
    ) -> dict:
        """Run alpha arena to discover and rank alpha signals."""
        logger.info("[VECTOR][fincept_agent] alpha discovery: {}", strategy)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from core.fincept.alpha_arena.core import AlphaArena
                arena = AlphaArena(universe=universe or [], strategy=strategy)
                return arena.run()
            except ImportError:
                return {"status": "deps_missing", "note": "alpha_arena requires additional deps"}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(30, f"alpha discovery: {strategy}")
        return result

    async def geopolitics_analysis(
        self,
        topic: str,
        framework: str = "grand_chessboard",
    ) -> dict:
        """
        Geopolitical analysis using structured frameworks.
        Frameworks: grand_chessboard, prisoners_of_geography
        """
        logger.info("[VECTOR][fincept_agent] geopolitics: {} / {}", framework, topic[:50])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                if framework == "grand_chessboard":
                    from core.fincept.agents.GeopoliticsAgents.GrandChessboardAgents import agent as geo_agent
                    return geo_agent.analyze(topic=topic)
                elif framework == "prisoners_of_geography":
                    from core.fincept.agents.GeopoliticsAgents.PrisonersOfGeographyAgents import agent as geo_agent
                    return geo_agent.analyze(topic=topic)
                else:
                    return {"status": "error", "error": f"unknown framework: {framework}"}
            except ImportError:
                # Fallback: use VECTOR's own LLM for geopolitical analysis
                return {"status": "deps_missing", "framework": framework, "topic": topic}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") not in ("error", "deps_missing"):
            self.award_points(20, f"geopolitics: {framework}")
        return result

    async def quant_backtest(
        self,
        strategy: str,
        tickers: list[str],
        start_date: str,
        end_date: str,
        engine: str = "backtesting",
    ) -> dict:
        """
        Run a backtest using one of the 6 available engines.
        Engines: backtesting, bt, vectorbt, zipline, fasttrade, fincept
        """
        logger.info("[VECTOR][fincept_agent] backtest: {} {} {}-{}", engine, tickers[:3], start_date, end_date)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                engine_mod = f"core.fincept.Analytics.backtesting.{engine}"
                import importlib
                mod = importlib.import_module(engine_mod)
                result = mod.run(strategy=strategy, tickers=tickers,
                                 start=start_date, end=end_date)
                return {"status": "ok", "engine": engine, "result": result}
            except ImportError:
                return {"status": "deps_missing", "engine": engine,
                        "note": f"Install {engine} first"}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(25, f"backtest: {engine}/{strategy}")
        return result

    async def launch_terminal(self, auto_build: bool = False) -> dict:
        """Launch the native C++/Qt6 financial terminal."""
        await self._launcher.ensure_built(auto_build=auto_build)
        st = self._launcher.status()
        if not st["binary_built"]:
            return {
                "status": "not_built",
                "message": f"Build first: cd core/fincept/qt && cmake --preset {st['preset']}",
                **st,
            }
        launched = self._launcher.launch()
        return {"status": "launched" if launched else "failed", **st}

    def terminal_status(self) -> dict:
        return self._launcher.status()

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        action = p.get("action", "investor_analysis")

        if action in ("investor_analysis", "persona_analysis"):
            return await self.investor_analysis(
                ticker=p.get("ticker", "NVDA"),
                persona=p.get("persona", "buffett"),
                date=p.get("date"),
            )
        elif action in ("corporate_finance", "dcf", "lbo", "merger"):
            return await self.corporate_finance(
                analysis_type=p.get("type", p.get("analysis_type", "dcf")),
                ticker=p.get("ticker"),
                data=p.get("data"),
            )
        elif action in ("alpha_discovery", "alpha"):
            return await self.alpha_discovery(
                universe=p.get("universe"),
                strategy=p.get("strategy", "momentum"),
            )
        elif action in ("geopolitics_analysis", "geopolitics"):
            return await self.geopolitics_analysis(
                topic=p.get("topic", ""),
                framework=p.get("framework", "grand_chessboard"),
            )
        elif action in ("quant_backtest", "backtest"):
            return await self.quant_backtest(
                strategy=p.get("strategy", "buy_and_hold"),
                tickers=p.get("tickers", ["SPY"]),
                start_date=p.get("start", "2020-01-01"),
                end_date=p.get("end", "2024-01-01"),
                engine=p.get("engine", "backtesting"),
            )
        elif action in ("launch_terminal", "terminal", "open_terminal"):
            return await self.launch_terminal(auto_build=p.get("auto_build", False))
        elif action == "terminal_status":
            return self.terminal_status()

        return {"status": "error", "error": f"unknown action: {action}"}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][fincept_agent] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][fincept_agent] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = FinceptAgent()
        assert agent.health_points == 500
        assert agent.name == "FinceptAgent"
        assert agent.district == "investment"

        # Terminal status (no build needed)
        st = agent.terminal_status()
        assert "cmake_source" in st
        assert "binary_built" in st

        print(f"OK fincept_agent.py HP={agent.health_points}")
        print(f"  cmake source present: {st['cmake_source']}")
        print(f"  terminal built: {st['binary_built']}")
        print(f"  terminal path: {st['binary_path']}")
        print(f"  Actions: investor_analysis, corporate_finance, alpha_discovery,")
        print(f"           geopolitics_analysis, quant_backtest, launch_terminal")

    asyncio.run(_smoke())
