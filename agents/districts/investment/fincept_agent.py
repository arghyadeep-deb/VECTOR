"""
VECTOR FinceptAgent — District 17: investment
Financial intelligence suite — investor personas, corporate finance, alpha discovery,
geopolitics analysis, and the native C++/Qt6 financial terminal.

Governor routes: investor_analysis, corporate_finance, alpha_discovery,
                 geopolitics_analysis, quant_backtest, launch_terminal

ANALYSIS ONLY for financial decisions — never executes real trades autonomously.
"""
from __future__ import annotations

import asyncio
import importlib
import json
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

_FINCEPT_BASE = Path(__file__).parent.parent.parent.parent / "core" / "fincept"

# ── Investor persona map (id → description from agent_definitions.json) ──────

def _load_investor_personas() -> dict:
    cfg_path = _FINCEPT_BASE / "agents" / "TraderInvestorsAgent" / "configs" / "agent_definitions.json"
    try:
        with open(cfg_path) as f:
            defs = json.load(f)
        return {a["id"]: a for a in defs.get("agents", [])}
    except Exception:
        return {}

_PERSONA_MAP = {
    "buffett":    "warren_buffett_agent",
    "graham":     "benjamin_graham_agent",
    "lynch":      "peter_lynch_agent",
    "munger":     "charlie_munger_agent",
    "klarman":    "seth_klarman_agent",
    "marks":      "howard_marks_agent",
    "renaissance": "renaissance_agent",
}

# ── Backtest engine → provider module map ─────────────────────────────────────

_BACKTEST_ENGINE_MAP = {
    "backtesting": "core.fincept.Analytics.backtesting.backtestingpy.backtestingpy_provider",
    "bt":          "core.fincept.Analytics.backtesting.bt.bt_provider",
    "vectorbt":    "core.fincept.Analytics.backtesting.vectorbt",
    "zipline":     "core.fincept.Analytics.backtesting.zipline",
    "fasttrade":   "core.fincept.Analytics.backtesting.fasttrade",
    "fincept":     "core.fincept.Analytics.backtesting.fincept",
}


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
        self._personas = _load_investor_personas()
        logger.info("[VECTOR][fincept_agent] ready gen={} hp={}", generation, self.health_points)

    # ── Actions ───────────────────────────────────────────────────────────────

    async def investor_analysis(
        self,
        ticker: str,
        persona: str = "buffett",
        date: str | None = None,
    ) -> dict:
        """
        Run an investor persona analysis on a ticker using CoreAgent.run_stock_analysis().
        Personas: buffett, graham, lynch, munger, klarman, marks, renaissance
        """
        logger.info("[VECTOR][fincept_agent] {} analysis: {}", persona, ticker)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from core.fincept.agents.finagent_core.core_agent import CoreAgent

                # Resolve persona description for a richer prompt
                persona_id = _PERSONA_MAP.get(persona.lower(), f"{persona}_agent")
                persona_def = self._personas.get(persona_id, {})
                persona_desc = persona_def.get("description", f"{persona} investment framework")

                # Build api_keys from VECTOR config (only populated keys)
                api_keys = {}
                fincept_cfg = CONFIG.get("fincept", {}) if isinstance(CONFIG, dict) else {}
                for env_k, cfg_k in [
                    ("ANTHROPIC_API_KEY", "anthropic_api_key"),
                    ("OPENAI_API_KEY", "openai_api_key"),
                    ("GOOGLE_API_KEY", "google_api_key"),
                ]:
                    import os
                    v = os.environ.get(env_k) or fincept_cfg.get(cfg_k, "")
                    if v:
                        api_keys[env_k] = v

                agent = CoreAgent(api_keys=api_keys or None)

                # run_stock_analysis does a structured financial workflow
                config = {
                    "persona": persona,
                    "persona_description": persona_desc,
                    "date": date,
                }
                result = agent.run_stock_analysis(symbol=ticker, config=config)
                return {"status": "ok", "ticker": ticker, "persona": persona,
                        "result": result}
            except Exception as e:
                logger.warning("[VECTOR][fincept_agent] investor_analysis error: {}", e)
                return {"status": "error", "error": str(e), "ticker": ticker, "persona": persona}

        result = await loop.run_in_executor(None, _run)
        self._memory.store(
            event_type="investor_analysis",
            content=f"FinceptAgent {persona} analysis: {ticker} → {result.get('status')}",
            tags=["investment", "analysis", ticker, persona],
            source="fincept_agent",
        )
        if result.get("status") == "ok":
            self.award_points(25, f"investor analysis: {persona}/{ticker}")
        return result

    async def corporate_finance(
        self,
        analysis_type: str = "dcf",
        ticker: str | None = None,
        data: dict | None = None,
    ) -> dict:
        """
        Corporate finance analytics. analysis_type: dcf, lbo, merger, startup, comps, fairness.
        """
        logger.info("[VECTOR][fincept_agent] corporate finance: {} {}", analysis_type, ticker or "")
        loop = asyncio.get_event_loop()

        def _run():
            try:
                atype = (analysis_type or "dcf").lower()
                d = data or {}

                if atype == "dcf":
                    from core.fincept.Analytics.corporateFinance.valuation.dcf_model import DCFModel
                    model = DCFModel(company_name=ticker or d.get("company", "Company"))
                    wacc = model.calculate_wacc(
                        risk_free_rate=d.get("risk_free_rate", 0.045),
                        market_risk_premium=d.get("mrp", 0.055),
                        beta=d.get("beta", 1.0),
                        cost_of_debt=d.get("cost_of_debt", 0.04),
                        tax_rate=d.get("tax_rate", 0.21),
                        market_value_equity=d.get("equity_value", 1_000_000),
                        market_value_debt=d.get("debt_value", 200_000),
                    )
                    return {"status": "ok", "analysis_type": "dcf",
                            "ticker": ticker, "wacc": wacc,
                            "note": "DCF WACC computed; provide cash_flows for full valuation"}

                elif atype == "lbo":
                    from core.fincept.Analytics.corporateFinance.lbo.lbo_model import LBOModel
                    model = LBOModel(
                        company_name=ticker or d.get("company", "Target"),
                        acquisition_price=d.get("acquisition_price", 100_000_000),
                        debt_pct=d.get("debt_pct", 0.65),
                        equity_pct=d.get("equity_pct", 0.35),
                    )
                    returns = model.calculate_returns(
                        exit_multiple=d.get("exit_multiple", 10),
                        holding_period=d.get("holding_period", 5),
                        ebitda_growth=d.get("ebitda_growth", 0.05),
                    )
                    return {"status": "ok", "analysis_type": "lbo",
                            "ticker": ticker, "returns": returns}

                elif atype in ("merger", "m&a"):
                    from core.fincept.Analytics.corporateFinance.merger_models.merger_model import MergerModel
                    model = MergerModel(
                        acquirer_name=d.get("acquirer", "Acquirer"),
                        target_name=ticker or d.get("target", "Target"),
                    )
                    result = model.run_analysis(data=d)
                    return {"status": "ok", "analysis_type": "merger",
                            "ticker": ticker, "result": result}

                elif atype in ("startup", "startup_valuation"):
                    # Use Berkus/VC method depending on data available
                    from core.fincept.Analytics.corporateFinance.startup_valuation import VCMethod, BerkusMethod
                    if d.get("revenue_multiple"):
                        model = VCMethod(
                            company_name=ticker or d.get("company", "Startup"),
                            projected_revenue=d.get("projected_revenue", 1_000_000),
                            revenue_multiple=d.get("revenue_multiple", 3.0),
                            investment_amount=d.get("investment", 500_000),
                            expected_roi=d.get("roi", 10),
                        )
                    else:
                        model = BerkusMethod(company_name=ticker or d.get("company", "Startup"))
                    result = model.calculate()
                    return {"status": "ok", "analysis_type": "startup_valuation",
                            "ticker": ticker, "result": result}

                elif atype in ("comps", "trading_comps"):
                    from core.fincept.Analytics.corporateFinance.valuation.trading_comps import TradingCompsAnalyzer
                    analyzer = TradingCompsAnalyzer()
                    comps = d.get("comps", [{"ticker": ticker or "PEER", "ev_ebitda": 12}])
                    result = analyzer.analyze(comps=comps)
                    return {"status": "ok", "analysis_type": "trading_comps",
                            "ticker": ticker, "result": result}

                elif atype in ("fairness", "fairness_opinion"):
                    from core.fincept.Analytics.corporateFinance.fairness_opinion import (
                        FairnessOpinionFramework, ValuationRange, ValuationMethod,
                    )
                    framework = FairnessOpinionFramework(
                        target_name=ticker or d.get("target", "Target Co"),
                        offer_price=d.get("offer_price", 100.0),
                    )
                    valuation = ValuationRange(
                        method=ValuationMethod.DCF,
                        low=d.get("val_low", 90.0),
                        high=d.get("val_high", 120.0),
                        midpoint=d.get("val_mid", 105.0),
                    )
                    framework.add_valuation(valuation)
                    result = framework.generate_opinion()
                    return {"status": "ok", "analysis_type": "fairness_opinion",
                            "ticker": ticker, "result": result}

                else:
                    return {"status": "error", "error": f"unknown analysis_type: {atype}. "
                            "Valid: dcf, lbo, merger, startup, comps, fairness"}

            except Exception as e:
                logger.warning("[VECTOR][fincept_agent] corporate_finance error: {}", e)
                return {"status": "error", "error": str(e), "analysis_type": analysis_type}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(20, f"corporate finance: {analysis_type}")
        return result

    async def alpha_discovery(
        self,
        universe: list[str] | None = None,
        strategy: str = "momentum",
    ) -> dict:
        """
        Alpha discovery using technical analysis and momentum screening.
        Runs momentum/mean-reversion/vol signals over a ticker universe.
        """
        logger.info("[VECTOR][fincept_agent] alpha discovery: {}", strategy)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from core.fincept.Analytics.technical_analysis.momentum_indicators import (
                    MomentumIndicators,
                )

                tickers = universe or ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"]
                signals = {}

                for ticker in tickers[:10]:  # cap at 10 to avoid rate limits
                    try:
                        ind = MomentumIndicators(ticker=ticker)
                        sig = ind.compute(strategy=strategy)
                        signals[ticker] = sig
                    except Exception as e:
                        signals[ticker] = {"error": str(e)}

                # Rank by signal strength
                ranked = sorted(
                    [(t, s) for t, s in signals.items() if "error" not in s],
                    key=lambda x: x[1].get("signal_strength", 0),
                    reverse=True,
                )
                return {
                    "status": "ok",
                    "strategy": strategy,
                    "universe_size": len(tickers),
                    "signals": signals,
                    "top_picks": [t for t, _ in ranked[:3]],
                }
            except Exception as e:
                logger.warning("[VECTOR][fincept_agent] alpha_discovery error: {}", e)
                return {"status": "error", "error": str(e), "strategy": strategy}

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
        Geopolitical analysis using CoreAgent with framework-specific personas.
        Frameworks: grand_chessboard, prisoners_of_geography
        """
        logger.info("[VECTOR][fincept_agent] geopolitics: {} / {}", framework, topic[:50])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from core.fincept.agents.finagent_core.core_agent import CoreAgent
                import os

                # Load geopolitics agent config
                geo_cfg_path = (_FINCEPT_BASE / "agents" / "GeopoliticsAgents" /
                                "configs" / "agent_definitions.json")
                framework_desc = ""
                try:
                    with open(geo_cfg_path) as f:
                        geo_defs = json.load(f)
                    agents = geo_defs.get("agents", [])
                    match = next((a for a in agents if framework.replace("-", "_") in a.get("id", "")), None)
                    if match:
                        framework_desc = match.get("description", "")
                except Exception:
                    pass

                api_keys = {}
                for env_k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
                    v = os.environ.get(env_k, "")
                    if v:
                        api_keys[env_k] = v

                agent = CoreAgent(api_keys=api_keys or None)

                fw_prompts = {
                    "grand_chessboard": (
                        "You are a geopolitical analyst using Brzezinski's Grand Chessboard framework. "
                        "Analyze the geopolitical dynamics, power struggles, and strategic implications."
                    ),
                    "prisoners_of_geography": (
                        "You are a geopolitical analyst using Tim Marshall's Prisoners of Geography framework. "
                        "Analyze how geography, terrain, rivers, and natural barriers shape political outcomes."
                    ),
                }
                system_prompt = fw_prompts.get(framework, fw_prompts["grand_chessboard"])
                if framework_desc:
                    system_prompt += f"\n\nFramework context: {framework_desc}"

                query = f"Analyze the following geopolitical topic: {topic}"
                config = {
                    "model": {"provider": "anthropic", "model_id": "claude-haiku-4-5-20251001"},
                    "system_prompt": system_prompt,
                }
                result = agent.run(query=query, config=config)
                return {
                    "status": "ok",
                    "framework": framework,
                    "topic": topic,
                    "analysis": str(result)[:2000],
                }
            except Exception as e:
                logger.warning("[VECTOR][fincept_agent] geopolitics error: {}", e)
                return {"status": "error", "error": str(e),
                        "framework": framework, "topic": topic}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
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
        Run a backtest using one of the available engines.
        Engines: backtesting (default), bt, vectorbt, zipline, fasttrade, fincept
        """
        logger.info("[VECTOR][fincept_agent] backtest: {} {} {}-{}", engine, tickers[:3], start_date, end_date)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                eng = engine.lower()
                module_path = _BACKTEST_ENGINE_MAP.get(eng)
                if not module_path:
                    return {"status": "error",
                            "error": f"unknown engine '{engine}'. Valid: {list(_BACKTEST_ENGINE_MAP)}"}

                mod = importlib.import_module(module_path)

                # BacktestingPyProvider pattern (matches backtestingpy and bt providers)
                provider_cls = None
                for attr in ("BacktestingPyProvider", "BtProvider", "VectorBtProvider",
                             "ZiplineProvider", "FastTradeProvider", "FinceptProvider"):
                    if hasattr(mod, attr):
                        provider_cls = getattr(mod, attr)
                        break

                if provider_cls is None:
                    return {"status": "error",
                            "error": f"no provider class found in {module_path}"}

                provider = provider_cls()
                request = {
                    "symbols": tickers,
                    "strategy": {"name": strategy, "type": strategy},
                    "startDate": start_date,
                    "endDate": end_date,
                    "initialCapital": 10_000,
                }
                result = provider.run_backtest(request)
                return {"status": "ok", "engine": engine, "strategy": strategy,
                        "tickers": tickers, "result": result}

            except ImportError as e:
                return {"status": "deps_missing", "engine": engine,
                        "note": str(e)}
            except Exception as e:
                logger.warning("[VECTOR][fincept_agent] quant_backtest error: {}", e)
                return {"status": "error", "error": str(e), "engine": engine}

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
                analysis_type=p.get("type", p.get("analysis_type", action if action != "corporate_finance" else "dcf")),
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

        st = agent.terminal_status()
        assert "cmake_source" in st
        assert "binary_built" in st

        print(f"OK fincept_agent.py HP={agent.health_points}")
        print(f"  cmake source present: {st['cmake_source']}")
        print(f"  terminal built: {st['binary_built']}")
        print(f"  terminal path: {st['binary_path']}")
        print(f"  Actions: investor_analysis, corporate_finance, alpha_discovery,")
        print(f"           geopolitics_analysis, quant_backtest, launch_terminal")
        print(f"  Investor personas loaded: {len(agent._personas)}")

    asyncio.run(_smoke())
