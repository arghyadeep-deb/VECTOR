"""
VECTOR BacktestAgent — District 17: investment
Quant research, 9-engine backtesting, shadow account analysis, and
29-preset LangGraph swarm teams — all from natural language.

Governor routes:
  vt_research, vt_backtest, shadow_account, vt_swarm, vt_skills, vt_export

Requires: OPENAI_API_KEY (or LANGCHAIN_PROVIDER + matching key) in .env
for the ReAct agent and swarms. Backtest data loaders work without API keys.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

# Ensure districts/investment/vector_backtest/ is on sys.path so src.* and backtest.* resolve.
# 2026-07-30 (KNOWN_ISSUES #5, vendored-subproject audit): this had one
# `.parent` too many (resolved to <one-above-repo-root>/core/vector_backtest,
# which doesn't exist) — every `from src...`/`from backtest...` import below
# has always raised ModuleNotFoundError, silently caught by each method's own
# broad `except Exception`, so all 6 of this agent's governor routes
# (vt_research, vt_backtest, shadow_account, vt_swarm, vt_skills, vt_export)
# have been failing closed with a generic error instead of actually running.
# Not a safety bug (fails closed), but a real, previously-unnoticed dead
# feature. Correct path is the sibling directory next to this file.
_VIBE_DIR = Path(__file__).parent / "vector_backtest"
if str(_VIBE_DIR) not in sys.path:
    sys.path.insert(0, str(_VIBE_DIR))

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.loop.permission_gateway import PermissionGateway, Action
from loguru import logger

class BacktestAgent(AgentBase):
    """
    VECTOR's quant research and backtesting agent.
    Wraps the Vibe-Trading ReAct loop, 9-engine backtest system,
    shadow account pipeline, and 29 LangGraph swarm presets.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None) -> None:
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="BacktestAgent",
            district="investment",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._gateway = PermissionGateway()
        self.capabilities = [
            "vt_research", "quant_research", "vt_backtest", "shadow_account",
            "vt_swarm", "vt_skills", "vt_export",
        ]
        logger.info("[VECTOR][vt_agent] ready gen={} hp={}", generation, self.health_points)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _cfg(self) -> dict:
        return CONFIG.get("vector_backtest", {}) if isinstance(CONFIG, dict) else {}

    def _runs_dir(self) -> Path:
        d = Path(self._cfg().get("runs_dir", Path.home() / ".vector" / "vector_backtest" / "runs"))
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── Actions ───────────────────────────────────────────────────────────────

    async def vt_research(self, task: str) -> dict:
        """
        Run the ReAct finance research agent on a plain-English task.

        Examples:
          "Analyse momentum signals for NVDA and TSLA this month"
          "Generate a pairs trading strategy for AAPL vs MSFT"
          "What does the ichimoku cloud say about BTC/USDT?"
          "Run a shadow account analysis on my trade journal at /path/to/journal.csv"
        """
        logger.info("[VECTOR][vt_agent] vt_research: {}", task[:70])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from src.agent.loop import AgentLoop
                from src.providers.chat import ChatLLM
                from src.tools import build_registry
                from src.memory.persistent import PersistentMemory

                cfg = self._cfg()
                mem_dir = Path(cfg.get("memory_dir", Path.home() / ".vector" / "vector_backtest" / "memory"))
                mem_dir.mkdir(parents=True, exist_ok=True)
                persistent_mem = PersistentMemory(mem_dir)

                llm = ChatLLM(model_name=cfg.get("langchain_model") or None)
                registry = build_registry(
                    persistent_memory=persistent_mem,
                    include_shell_tools=cfg.get("enable_shell_tools", False),
                )
                agent_loop = AgentLoop(
                    registry=registry,
                    llm=llm,
                    persistent_memory=persistent_mem,
                    max_iterations=50,
                )
                result = agent_loop.run(user_message=task)
                return {"status": "ok", "task": task, "result": result}
            except Exception as e:
                logger.warning("[VECTOR][vt_agent] vt_research error: {}", e)
                return {"status": "error", "error": str(e), "task": task}

        result = await loop.run_in_executor(None, _run)
        self._memory.store(
            event_type="vt_research",
            content=f"BacktestAgent research: {task[:80]} -> {result.get('status')}",
            tags=["investment", "quant", "research"],
            source="backtest_agent",
        )
        if result.get("status") == "ok":
            self.award_points(35, f"quant research: {task[:40]}")
        return result

    async def vt_backtest(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        strategy_code: str | None = None,
        source: str = "auto",
        engine: str = "daily",
        interval: str = "1D",
    ) -> dict:
        """
        Run a backtest using the 9-engine system with auto-fallback data loading.

        engines: daily, china_a, global_equity, crypto, forex,
                 china_futures, global_futures, options_portfolio, composite
        sources: auto (recommended), tushare, yfinance, akshare, ccxt, okx, futu

        RED-gated (58E remediation — VECTOR_TECHNICAL_KNOWLEDGE/58E_VECTOR_
        BACKTEST_STRATEGY_PERMISSION_REMEDIATION.md): strategy_code, when
        supplied, is real caller-controlled Python that the vendored backtest
        runner dynamically imports and instantiates as a SignalEngine — no
        sandbox. Gated unconditionally, not only when strategy_code is
        truthy: the runner unconditionally requires code/signal_engine.py to
        exist with no default/fallback engine, so every functional call to
        this method depends on code reaching that path one way or another.
        Neither the strategy-code write nor bt_main() may be reached unless
        gate_result.approved is True.
        """
        logger.info("[VECTOR][vt_agent] vt_backtest: {} {} {}-{}", engine, codes[:3], start_date, end_date)

        try:
            gate_result = await self._gateway.execute(Action(
                action_type="vt_backtest",
                params={
                    "codes": codes,
                    "start_date": start_date,
                    "end_date": end_date,
                    "source": source,
                    "engine": engine,
                    "interval": interval,
                    "has_strategy_code": bool(strategy_code),
                    "strategy_code": strategy_code or "",
                    "summary": (
                        f"Run backtest engine={engine!r} source={source!r} on "
                        f"{codes} ({start_date}..{end_date})"
                        + (
                            f" — executes {len(strategy_code)} chars of caller-"
                            f"supplied Python as the trading signal engine "
                            f"(dynamically imported and instantiated by the "
                            f"backtest runner, no sandbox)."
                            if strategy_code else
                            " — no caller-supplied strategy code for this call."
                        )
                    ),
                },
                proposed_by=self.name,
            ))
        except Exception as e:
            # Fail closed — never let a gateway-unreachable condition fall
            # through to a real strategy-code write/execution (mirrors
            # hedgebot_agent.py's solana_swap_execute pattern).
            logger.error("[VECTOR][vt_agent] gateway unavailable — refusing vt_backtest: {}", e)
            return {"status": "blocked", "reason": f"gateway unavailable: {e}"}

        if not gate_result.approved:
            logger.warning("[VECTOR][vt_agent] vt_backtest blocked by gateway: {}", gate_result.reason)
            return {"status": "blocked", "reason": gate_result.reason}

        loop = asyncio.get_event_loop()

        def _run():
            try:
                import json, tempfile, os
                # 2026-08-04 fix: BacktestConfigSchema doesn't live in
                # backtest.models (that file only has Position/TradeRecord/
                # EquitySnapshot) -- it's defined in backtest.runner itself,
                # right next to `main`. This import always raised
                # ImportError, so vt_backtest always failed closed.
                from backtest.runner import main as bt_main, BacktestConfigSchema

                run_dir = self._runs_dir() / f"bt_{uuid.uuid4().hex[:8]}"
                run_dir.mkdir(parents=True, exist_ok=True)

                config = BacktestConfigSchema(
                    codes=codes,
                    start_date=start_date,
                    end_date=end_date,
                    source=source,
                    interval=interval,
                    engine=engine,
                )
                (run_dir / "config.json").write_text(
                    json.dumps(config.model_dump(), default=str), encoding="utf-8"
                )

                # Write strategy code if provided
                if strategy_code:
                    (run_dir / "signal_engine.py").write_text(strategy_code, encoding="utf-8")

                bt_main(run_dir)

                # Collect artifacts
                artifacts = {}
                for f in run_dir.iterdir():
                    if f.suffix in (".json", ".csv", ".html", ".png"):
                        artifacts[f.name] = str(f)

                return {
                    "status": "ok", "engine": engine, "codes": codes,
                    "run_dir": str(run_dir), "artifacts": artifacts,
                }
            except Exception as e:
                logger.warning("[VECTOR][vt_agent] vt_backtest error: {}", e)
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(30, f"backtest: {engine}/{codes[:2]}")
        return result

    async def shadow_account(self, journal_path: str) -> dict:
        """
        Analyse a broker trade journal: extract trading behavior patterns,
        synthesise rules, run shadow backtest, generate HTML/PDF report.

        journal_path: path to broker CSV export (支持同花顺/东财/富途/generic CSV).
        """
        logger.info("[VECTOR][vt_agent] shadow_account: {}", journal_path[:60])
        loop = asyncio.get_event_loop()

        def _run():
            try:
                import dataclasses
                # 2026-08-04 fix: this used to manually read the journal
                # with pandas, hand-build an empty ShadowProfile with fields
                # that don't exist on it (`source_path` isn't a field --
                # ShadowProfile is a frozen dataclass requiring every one of
                # its 11 real fields), and call `extract_rules(trades_df,
                # profile=profile)`, which has never existed (only a private
                # `_extract_rules(features_df, ...)` does). The real,
                # single public entry point is `extract_shadow_profile
                # (journal_path, ...)` -- it does the entire pipeline itself
                # (parse -> pair roundtrips -> feature-engineer -> extract
                # rules -> build ShadowProfile) and returns one fully-formed
                # ShadowProfile. This always raised before any of that
                # mismatch even mattered, since the import itself failed.
                from src.shadow_account.extractor import extract_shadow_profile

                path = Path(journal_path)
                if not path.exists():
                    return {"status": "error", "error": f"Journal file not found: {journal_path}"}

                profile = extract_shadow_profile(path)
                rules = [dataclasses.asdict(r) for r in profile.rules]

                return {
                    "status": "ok",
                    "journal": journal_path,
                    "shadow_id": profile.shadow_id,
                    "profile_text": profile.profile_text,
                    "rules_extracted": len(rules),
                    "rules": rules,
                    "note": "Call vt_research with shadow_account tool for full HTML/PDF report",
                }
            except Exception as e:
                logger.warning("[VECTOR][vt_agent] shadow_account error: {}", e)
                return {"status": "error", "error": str(e)}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(25, "shadow account analysis")
        return result

    async def vt_swarm(
        self,
        preset: str,
        variables: dict | None = None,
    ) -> dict:
        """
        Launch one of 29 LangGraph swarm team presets.

        presets: investment_committee, quant_strategy_desk, crypto_research_lab,
                 geopolitical_war_room, ml_quant_lab, factor_research_committee,
                 macro_strategy_forum, risk_committee, sector_rotation_team, ...
        """
        logger.info("[VECTOR][vt_agent] vt_swarm: preset={}", preset)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from src.swarm.runtime import SwarmRuntime
                from src.swarm.store import SwarmStore

                store_dir = self._runs_dir() / "swarms"
                store_dir.mkdir(parents=True, exist_ok=True)
                store = SwarmStore(store_dir)
                runtime = SwarmRuntime(store=store, max_workers=4)
                swarm_run = runtime.start_run(
                    preset_name=preset,
                    user_vars=variables or {},
                    include_shell_tools=self._cfg().get("enable_shell_tools", False),
                )
                return {
                    "status": "ok",
                    "preset": preset,
                    "run_id": swarm_run.run_id,
                    "status_msg": f"Swarm '{preset}' started (run_id={swarm_run.run_id}). Check status via vt_research with swarm tools.",
                }
            except Exception as e:
                logger.warning("[VECTOR][vt_agent] vt_swarm error: {}", e)
                return {"status": "error", "error": str(e), "preset": preset}

        result = await loop.run_in_executor(None, _run)
        if result.get("status") == "ok":
            self.award_points(20, f"swarm: {preset}")
        return result

    async def vt_skills(self, search: str | None = None) -> dict:
        """List or search the 74 available finance skills."""
        loop = asyncio.get_event_loop()

        def _run():
            try:
                from src.agent.skills import SkillsLoader
                cfg = self._cfg()
                user_dir = Path(cfg.get("skills_user_dir", Path.home() / ".vector" / "vector_backtest" / "skills"))
                loader = SkillsLoader(user_skills_dir=user_dir if user_dir.exists() else None)
                descriptions = loader.get_descriptions()
                if search:
                    lines = [l for l in descriptions.splitlines() if search.lower() in l.lower()]
                    return {"status": "ok", "search": search, "matches": lines}
                return {"status": "ok", "skills": descriptions}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        return await loop.run_in_executor(None, _run)

    async def vt_export(self, strategy_code: str, target: str = "pine") -> dict:
        """
        Export a strategy to another platform.
        targets: pine (TradingView Pine Script v6), mql5 (MetaTrader 5), vnpy (vn.py CTA)
        """
        logger.info("[VECTOR][vt_agent] vt_export: target={}", target)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                # Use the research agent to do the export via load_skill + write
                from src.agent.loop import AgentLoop
                from src.providers.chat import ChatLLM
                from src.tools import build_registry

                cfg = self._cfg()
                llm = ChatLLM(model_name=cfg.get("langchain_model") or None)
                registry = build_registry(include_shell_tools=False)
                agent_loop = AgentLoop(registry=registry, llm=llm, max_iterations=10)

                skill_map = {"pine": "pine-script", "mql5": "vnpy-export", "vnpy": "vnpy-export"}
                skill = skill_map.get(target, "pine-script")
                task = f"Load the {skill} skill and convert this strategy to {target} format:\n\n{strategy_code}"
                result = agent_loop.run(user_message=task)
                return {"status": "ok", "target": target, "result": result}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        return await loop.run_in_executor(None, _run)

    # ── AgentBase interface ───────────────────────────────────────────────────

    SUPPORTED_TYPES = (
        "vt_research", "quant_research", "vt_backtest", "shadow_account",
        "vt_swarm", "vt_skills", "vt_export",
    )

    async def run(self, task: dict) -> dict:
        # Governor's real dispatch contract is task["type"]; params["action"]
        # is kept only as a back-compat alias for direct/manual invocations.
        p = task.get("params", task)
        task_type = task.get("type") or p.get("action", "vt_research")

        if task_type in ("vt_research", "quant_research"):
            return await self.vt_research(task=p.get("task", p.get("query", "")))
        elif task_type == "vt_backtest":
            return await self.vt_backtest(
                codes=p.get("codes", p.get("tickers", ["AAPL"])),
                start_date=p.get("start_date", p.get("start", "2022-01-01")),
                end_date=p.get("end_date", p.get("end", "2024-01-01")),
                strategy_code=p.get("strategy_code"),
                source=p.get("source", "auto"),
                engine=p.get("engine", "daily"),
                interval=p.get("interval", "1D"),
            )
        elif task_type == "shadow_account":
            return await self.shadow_account(journal_path=p.get("journal_path", ""))
        elif task_type == "vt_swarm":
            return await self.vt_swarm(
                preset=p.get("preset", "investment_committee"),
                variables=p.get("variables", {}),
            )
        elif task_type == "vt_skills":
            return await self.vt_skills(search=p.get("search"))
        elif task_type == "vt_export":
            return await self.vt_export(
                strategy_code=p.get("strategy_code", ""),
                target=p.get("target", "pine"),
            )

        query = p.get("query") or p.get("content") or task.get("query") or task.get("prompt")
        if query:
            # 2026-07-29: unmatched/free-text task_type previously fell
            # straight through to an error stub with no real content —
            # same bug class as stock_analyst.py's pre-fix quote default
            # (KNOWN_ISSUES.md #1/#14/#15/#21/#33/#36). vt_research already
            # handles arbitrary free-text finance questions via the ReAct
            # research agent, so route real chat queries there directly
            # instead of erroring.
            return await self.vt_research(task=query)

        return {
            "status": "error",
            "error": f"unhandled type '{task_type}'",
            "supported": list(self.SUPPORTED_TYPES),
        }

    async def run_forever(self) -> None:
        logger.info("[VECTOR][vt_agent] ready — waiting for tasks")
        while self.is_alive:
            await asyncio.sleep(60)
        logger.warning("[VECTOR][vt_agent] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = BacktestAgent()
        assert agent.health_points == 500
        assert agent.name == "BacktestAgent"
        assert agent.district == "investment"

        # Verify key imports work
        tools_ok = True
        try:
            from src.agent.skills import SkillsLoader
            from src.swarm.runtime import SwarmRuntime
            from src.shadow_account.scanner import scan_today_signals
            from backtest.runner import main as bt_main
            from backtest.engines.base import BaseEngine
            from backtest.loaders.registry import LOADER_REGISTRY
        except ImportError as e:
            tools_ok = False
            print(f"  Import error: {e}")

        # Skills count
        skills_count = 0
        if tools_ok:
            try:
                from src.agent.skills import SkillsLoader
                loader = SkillsLoader()
                descriptions = loader.get_descriptions()
                skills_count = len([l for l in descriptions.splitlines() if l.strip().startswith("-")])
            except Exception:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)

        print(f"OK backtest_agent.py HP={agent.health_points}")
        print(f"  district: {agent.district}")
        print(f"  core imports OK: {tools_ok}")
        print(f"  skills available: ~{skills_count}")
        print(f"  actions: vt_research, vt_backtest, shadow_account, vt_swarm, vt_skills, vt_export")

    asyncio.run(_smoke())
