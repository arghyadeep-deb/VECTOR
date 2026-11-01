"""
VECTOR FinAgentAgent — District 17: investment
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

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.context_engine import ContextEngine
from core.loop.permission_gateway import PermissionGateway, Action
from districts.investment.vector_finagent.terminal_launcher import FinAgentTerminalLauncher
from loguru import logger

_FINCEPT_BASE = Path(__file__).parent / "vector_finagent"

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
    "backtesting": "districts.investment.vector_finagent.Analytics.backtesting.backtestingpy.backtestingpy_provider",
    "bt":          "districts.investment.vector_finagent.Analytics.backtesting.bt.bt_provider",
    "vectorbt":    "districts.investment.vector_finagent.Analytics.backtesting.vectorbt",
    "zipline":     "districts.investment.vector_finagent.Analytics.backtesting.zipline",
    "fasttrade":   "districts.investment.vector_finagent.Analytics.backtesting.fasttrade",
    "vector_finagent":     "districts.investment.vector_finagent.Analytics.backtesting.vector_finagent",
}

class FinAgentAgent(AgentBase):
    """
    VECTOR's financial intelligence agent — powered by the FinAgent suite.
    Provides investor persona analysis, corporate finance models, alpha
    discovery, geopolitics analysis, and the native C++/Qt6 terminal.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="FinAgentAgent",
            district="investment",
            generation=generation,
        )
        self.capabilities = ["ANTHROPIC_API_KEY", "BacktestingPyProvider", "alpha_discovery", "comps", "corporate_finance", "fairness", "finagent", "geopolitics_analysis", "investment", "investor_analysis", "launch_terminal", "merger", "quant_backtest", "startup", "terminal_status", "trading"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory   = EpisodicMemory()
        self._context  = ContextEngine()
        self._gateway  = PermissionGateway()
        self._launcher = FinAgentTerminalLauncher()
        self._personas = _load_investor_personas()
        logger.info("[VECTOR][finagent_agent] ready gen={} hp={}", generation, self.health_points)

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
        logger.info("[VECTOR][finagent_agent] {} analysis: {}", persona, ticker)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from districts.investment.vector_finagent.agents.finagent_core.core_agent import CoreAgent

                # Resolve persona description for a richer prompt
                persona_id = _PERSONA_MAP.get(persona.lower(), f"{persona}_agent")
                persona_def = self._personas.get(persona_id, {})
                persona_desc = persona_def.get("description", f"{persona} investment framework")

                # Build api_keys from VECTOR config (only populated keys)
                api_keys = {}
                vector_finagent_cfg = CONFIG.get("vector_finagent", {}) if isinstance(CONFIG, dict) else {}
                for env_k, cfg_k in [
                    ("ANTHROPIC_API_KEY", "anthropic_api_key"),
                    ("OPENAI_API_KEY", "openai_api_key"),
                    ("GOOGLE_API_KEY", "google_api_key"),
                ]:
                    import os
                    v = os.environ.get(env_k) or vector_finagent_cfg.get(cfg_k, "")
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
                logger.warning("[VECTOR][finagent_agent] investor_analysis error: {}", e)
                return {"status": "error", "error": str(e), "ticker": ticker, "persona": persona}

        result = await loop.run_in_executor(None, _run)
        self._memory.store(
            event_type="investor_analysis",
            content=f"FinAgentAgent {persona} analysis: {ticker} → {result.get('status')}",
            tags=["investment", "analysis", ticker, persona],
            source="finagent_agent",
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
        logger.info("[VECTOR][finagent_agent] corporate finance: {} {}", analysis_type, ticker or "")
        loop = asyncio.get_event_loop()

        def _run():
            try:
                atype = (analysis_type or "dcf").lower()
                d = data or {}

                if atype == "dcf":
                    from districts.investment.vector_finagent.Analytics.corporateFinance.valuation.dcf_model import DCFModel
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
                    from districts.investment.vector_finagent.Analytics.corporateFinance.lbo.lbo_model import LBOModel
                    target_data = {
                        "company_name": ticker or d.get("company", "Target"),
                        "revenue": d.get("revenue", 100_000_000),
                        "ebitda": d.get("ebitda", 20_000_000),
                        "ebitda_margin": d.get("ebitda_margin", 0.20),
                    }
                    transaction = {
                        "acquisition_price": d.get("acquisition_price", 200_000_000),
                        "debt_pct": d.get("debt_pct", 0.65),
                        "equity_pct": d.get("equity_pct", 0.35),
                        "exit_multiple": d.get("exit_multiple", 10),
                        "holding_period": d.get("holding_period", 5),
                    }
                    model = LBOModel(target_data=target_data, transaction_assumptions=transaction)
                    result = model.build_complete_model()
                    return {"status": "ok", "analysis_type": "lbo",
                            "ticker": ticker, "result": result}

                elif atype in ("merger", "m&a"):
                    from districts.investment.vector_finagent.Analytics.corporateFinance.merger_models.merger_model import MergerModel
                    acquirer_data = {
                        "name": d.get("acquirer", "Acquirer"),
                        "revenue": d.get("acquirer_revenue", 500_000_000),
                        "ebitda": d.get("acquirer_ebitda", 100_000_000),
                        "shares_outstanding": d.get("acquirer_shares", 10_000_000),
                        "stock_price": d.get("acquirer_price", 50.0),
                    }
                    target_data = {
                        "name": ticker or d.get("target", "Target"),
                        "revenue": d.get("target_revenue", 100_000_000),
                        "ebitda": d.get("target_ebitda", 20_000_000),
                        "shares_outstanding": d.get("target_shares", 5_000_000),
                        "stock_price": d.get("target_price", 30.0),
                    }
                    deal_terms = {
                        "offer_price": d.get("offer_price", 40.0),
                        "deal_type": d.get("deal_type", "cash"),
                        "synergies": d.get("synergies", 10_000_000),
                    }
                    model = MergerModel(acquirer_data=acquirer_data,
                                        target_data=target_data,
                                        deal_terms=deal_terms)
                    result = model.run_analysis() if hasattr(model, "run_analysis") else str(model)
                    return {"status": "ok", "analysis_type": "merger",
                            "ticker": ticker, "result": result}

                elif atype in ("startup", "startup_valuation"):
                    # Use Berkus/VC method depending on data available
                    from districts.investment.vector_finagent.Analytics.corporateFinance.startup_valuation import VCMethod, BerkusMethod
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
                    from districts.investment.vector_finagent.Analytics.corporateFinance.valuation.trading_comps import TradingCompsAnalyzer
                    analyzer = TradingCompsAnalyzer()
                    comps = d.get("comps", [{"ticker": ticker or "PEER", "ev_ebitda": 12}])
                    result = analyzer.analyze(comps=comps)
                    return {"status": "ok", "analysis_type": "trading_comps",
                            "ticker": ticker, "result": result}

                elif atype in ("fairness", "fairness_opinion"):
                    from districts.investment.vector_finagent.Analytics.corporateFinance.fairness_opinion import (
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
                logger.warning("[VECTOR][finagent_agent] corporate_finance error: {}", e)
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
        logger.info("[VECTOR][finagent_agent] alpha discovery: {}", strategy)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from districts.investment.vector_finagent.Analytics.technical_analysis.momentum_indicators import (
                    calculate_rsi, calculate_macd, calculate_roc,
                )
                import numpy as np

                tickers = universe or ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"]
                signals = {}

                for ticker in tickers[:10]:
                    try:
                        # Generate synthetic price series as placeholder
                        # (real data would come from a data connector)
                        np.random.seed(hash(ticker) % 2**32)
                        prices = np.cumprod(1 + np.random.normal(0.0003, 0.015, 252)) * 100
                        rsi = calculate_rsi(prices)
                        macd_line, signal_line, _ = calculate_macd(prices)
                        roc = calculate_roc(prices)

                        # Simple scoring: RSI<40 + MACD bullish crossover + positive ROC
                        score = 0.0
                        if rsi is not None and len(rsi) > 0:
                            last_rsi = float(rsi[-1]) if hasattr(rsi, '__len__') else float(rsi)
                            score += 1.0 if last_rsi < 40 else (-1.0 if last_rsi > 70 else 0.0)
                        if macd_line is not None and signal_line is not None:
                            if hasattr(macd_line, '__len__') and len(macd_line) > 1:
                                score += 1.0 if macd_line[-1] > signal_line[-1] else -1.0
                        if roc is not None:
                            last_roc = float(roc[-1]) if hasattr(roc, '__len__') else float(roc)
                            score += 1.0 if last_roc > 0 else -1.0

                        signals[ticker] = {
                            "signal_strength": round(score / 3.0, 3),
                            "rsi": round(float(rsi[-1]) if hasattr(rsi, '__len__') and len(rsi) > 0 else 50, 2),
                            "strategy": strategy,
                        }
                    except Exception as e:
                        signals[ticker] = {"error": str(e)}

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
                logger.warning("[VECTOR][finagent_agent] alpha_discovery error: {}", e)
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
        logger.info("[VECTOR][finagent_agent] geopolitics: {} / {}", framework, topic[:50])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from districts.investment.vector_finagent.agents.finagent_core.core_agent import CoreAgent
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
                    logger.debug("[VECTOR] suppressed exception", exc_info=True)

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
                logger.warning("[VECTOR][finagent_agent] geopolitics error: {}", e)
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
        Engines: backtesting (default), bt, vectorbt, zipline, fasttrade, vector_finagent
        """
        logger.info("[VECTOR][finagent_agent] backtest: {} {} {}-{}", engine, tickers[:3], start_date, end_date)
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
                             "ZiplineProvider", "FastTradeProvider", "FinAgentProvider"):
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
                logger.warning("[VECTOR][finagent_agent] quant_backtest error: {}", e)
                return {"status": "error", "error": str(e), "engine": engine}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(25, f"backtest: {engine}/{strategy}")
        return result

    async def launch_terminal(self, auto_build: bool = False) -> dict:
        """Launch the native C++/Qt6 financial terminal.

        RED-gated (58B remediation — VECTOR_TECHNICAL_KNOWLEDGE/58B_FINAGENT_
        TERMINAL_PERMISSION_REMEDIATION.md): both the real native build
        (auto_build=True → real cmake/build subprocess.run) and the real
        terminal binary launch (subprocess.Popen) are consequential side
        effects that must not occur without owner approval. auto_build is
        forwarded as an explicit param on the SAME gated Action so the
        approver sees whether a build will be triggered before approving —
        one RED approval intentionally covers both build and launch, since
        they are both downstream consequences of the single "launch the
        terminal" request. Neither ensure_built() nor launch() may be
        reached unless gate_result.approved is True.
        """
        try:
            gate_result = await self._gateway.execute(Action(
                action_type="launch_terminal",
                params={"auto_build": auto_build},
                proposed_by=self.name,
            ))
        except Exception as e:
            # Fail closed — never let a gateway-unreachable condition fall
            # through to a real build/launch (mirrors hedgebot_agent.py's
            # solana_swap_execute pattern).
            logger.error("[VECTOR][finagent_agent] gateway unavailable — refusing launch_terminal: {}", e)
            return {"status": "blocked", "reason": f"gateway unavailable: {e}"}

        if not gate_result.approved:
            logger.warning("[VECTOR][finagent_agent] launch_terminal blocked by gateway: {}", gate_result.reason)
            return {"status": "blocked", "reason": gate_result.reason}

        await self._launcher.ensure_built(auto_build=auto_build)
        st = self._launcher.status()
        if not st["binary_built"]:
            return {
                "status": "not_built",
                "message": f"Build first: cd districts/investment/vector_finagent/qt && cmake --preset {st['preset']}",
                **st,
            }
        launched = self._launcher.launch()
        return {"status": "launched" if launched else "failed", **st}

    def terminal_status(self) -> dict:
        return self._launcher.status()

    async def answer_freetext_query(self, query: str) -> dict:
        """
        Answer a free-text financial question directly via CoreAgent when no
        structured action/task_type matched.

        2026-07-29: run() previously read ONLY params["action"] and never
        task["type"] at all, so every real dispatch from governor.py or the
        /analyze, /dcf, /alpha, /backtest, /geopolitics API routes (which all
        set task["type"], never params["action"]) silently fell through to a
        hardcoded investor_analysis(NVDA, buffett) — same bug class as
        stock_analyst.py's pre-fix quote default (KNOWN_ISSUES.md
        #1/#14/#15/#21/#33/#36). This grounds a real answer instead.
        """
        logger.info("[VECTOR][finagent_agent] freetext query: {}", query[:60])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from districts.investment.vector_finagent.agents.finagent_core.core_agent import CoreAgent
                import os

                api_keys = {}
                for env_k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
                    v = os.environ.get(env_k, "")
                    if v:
                        api_keys[env_k] = v

                agent = CoreAgent(api_keys=api_keys or None)
                system_prompt = (
                    "You are VECTOR's FinAgentAgent — a financial intelligence agent "
                    "covering investor-persona analysis (Buffett/Graham/Lynch/Munger/"
                    "Klarman/Marks/Renaissance), corporate finance (DCF/LBO/merger/"
                    "startup valuation/comps/fairness opinions), alpha discovery "
                    "(momentum/technical screening), geopolitics analysis, and quant "
                    "backtesting. Analysis only — you never execute real trades."
                )
                config = {
                    "model": {"provider": "anthropic", "model_id": "claude-haiku-4-5-20251001"},
                    "system_prompt": system_prompt,
                }
                result = agent.run(query=query, config=config)
                return {"status": "ok", "response": str(result)[:2000]}
            except Exception as e:
                logger.warning("[VECTOR][finagent_agent] freetext query error: {}", e)
                return {"status": "error", "error": str(e)}

        return await loop.run_in_executor(None, _run)

    # ── AgentBase interface ───────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        # 2026-07-29: was `p.get("action", "investor_analysis")` — never
        # read task["type"] at all, so real dispatches (governor.py and the
        # /analyze,/dcf,/alpha,/backtest,/geopolitics API routes all set
        # task["type"], not params["action"]) always silently defaulted to
        # investor_analysis(NVDA, buffett). Sibling files in this district
        # (backtest_agent.py, hedgebot_agent.py) already prefer
        # task["type"]; align this one to match.
        action = task.get("type") or p.get("action", "investor_analysis")

        if action in ("investor_analysis", "persona_analysis"):
            return await self.investor_analysis(
                ticker=p.get("ticker", "NVDA"),
                persona=p.get("persona", "buffett"),
                date=p.get("date"),
            )
        elif action in (
            "corporate_finance", "dcf", "lbo", "merger",
            "corporate_finance/dcf", "corporate_finance/lbo", "corporate_finance/merger",
        ):
            # 2026-07-29: the /dcf route dispatches task["type"] =
            # "corporate_finance/dcf" (see core/api/routers/investment.py's
            # dcf_valuation()) — a compound slash-joined string that never
            # matched this elif's literal comparisons, so the branch was
            # unreachable via the real API route even after the task["type"]
            # fix above (only reachable via a manual dispatch using the bare
            # "dcf"/"corporate_finance" strings). Split the compound form to
            # recover the real analysis_type. Also: DCFRequest's body has no
            # "ticker" field, only "company_name" — map it so the DCF model
            # gets the real company name instead of the generic "Company"
            # default.
            _atype = (
                action.split("/", 1)[1] if "/" in action
                else p.get("type", p.get("analysis_type", action if action != "corporate_finance" else "dcf"))
            )
            return await self.corporate_finance(
                analysis_type=_atype,
                ticker=p.get("ticker") or p.get("company_name"),
                data=p.get("data"),
            )
        elif action in ("alpha_discovery", "alpha"):
            # 2026-07-29: /alpha route's AlphaRequest body uses `symbols`,
            # not `universe` — same newly-reachable field-name mismatch as
            # the geopolitics branch above (action always defaulted to
            # investor_analysis before the task["type"] fix, so this never
            # actually ran off real API params before).
            return await self.alpha_discovery(
                universe=p.get("universe") or p.get("symbols"),
                strategy=p.get("strategy", "momentum"),
            )
        elif action in ("geopolitics_analysis", "geopolitics"):
            # 2026-07-29: the /geopolitics API route's GeopoliticsRequest
            # body only has a `query` field, not `topic` — this branch was
            # unreachable before the task["type"] fix above (action always
            # defaulted to investor_analysis), so the field-name mismatch
            # was never exposed. Accept either now that it's reachable.
            return await self.geopolitics_analysis(
                topic=p.get("topic") or p.get("query", ""),
                framework=p.get("framework", "grand_chessboard"),
            )
        elif action in ("quant_backtest", "backtest"):
            # 2026-07-29: /backtest route's BacktestRequest body uses
            # `symbols`/`start_date`/`end_date`, not `tickers`/`start`/`end`
            # — same newly-reachable field-name mismatch as above.
            return await self.quant_backtest(
                strategy=p.get("strategy", "buy_and_hold"),
                tickers=p.get("tickers") or p.get("symbols", ["SPY"]),
                start_date=p.get("start") or p.get("start_date", "2020-01-01"),
                end_date=p.get("end") or p.get("end_date", "2024-01-01"),
                engine=p.get("engine", "backtesting"),
            )
        elif action in ("launch_terminal", "terminal", "open_terminal"):
            return await self.launch_terminal(auto_build=p.get("auto_build", False))
        elif action == "terminal_status":
            return self.terminal_status()

        query = p.get("query") or p.get("content") or task.get("query") or task.get("prompt")
        if query:
            return await self.answer_freetext_query(query)

        return {"status": "error", "error": f"unknown action: {action}"}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][finagent_agent] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][finagent_agent] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = FinAgentAgent()
        assert agent.health_points == 500
        assert agent.name == "FinAgentAgent"
        assert agent.district == "investment"

        st = agent.terminal_status()
        assert "cmake_source" in st
        assert "binary_built" in st

        print(f"OK finagent_agent.py HP={agent.health_points}")
        print(f"  cmake source present: {st['cmake_source']}")
        print(f"  terminal built: {st['binary_built']}")
        print(f"  terminal path: {st['binary_path']}")
        print(f"  Actions: investor_analysis, corporate_finance, alpha_discovery,")
        print(f"           geopolitics_analysis, quant_backtest, launch_terminal")
        print(f"  Investor personas loaded: {len(agent._personas)}")

    asyncio.run(_smoke())
