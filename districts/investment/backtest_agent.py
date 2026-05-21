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

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Ensure districts/investment/vector_backtest/ is on sys.path so src.* and backtest.* resolve
_VIBE_DIR = Path(__file__).parent.parent.parent.parent / "core" / "vector_backtest"
if str(_VIBE_DIR) not in sys.path:
    sys.path.insert(0, str(_VIBE_DIR))

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
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
        """
        logger.info("[VECTOR][vt_agent] vt_backtest: {} {} {}-{}", engine, codes[:3], start_date, end_date)
        loop = asyncio.get_event_loop()

        def _run():
            try:
                import json, tempfile, os
                from backtest.runner import main as bt_main
                from backtest.models import BacktestConfigSchema

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
                import pandas as pd
                from src.shadow_account.scanner import scan_today_signals
                from src.shadow_account.extractor import extract_rules
                from src.shadow_account.models import ShadowProfile
                from src.shadow_account.storage import new_shadow_id, hash_journal

                path = Path(journal_path)
                if not path.exists():
                    return {"status": "error", "error": f"Journal file not found: {journal_path}"}

                trades_df = pd.read_csv(path)
                profile = ShadowProfile(
                    shadow_id=new_shadow_id(),
                    journal_hash=hash_journal(trades_df),
                    source_path=str(path),
                )
                rules = extract_rules(trades_df, profile=profile)

                return {
                    "status": "ok",
                    "journal": journal_path,
                    "rules_extracted": len(rules),
                    "rules": [r.__dict__ if hasattr(r, '__dict__') else str(r) for r in rules],
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

    async def run(self, task: dict) -> dict:
        p = task.get("params", task)
        action = p.get("action", "vt_research")

        if action in ("vt_research", "quant_research"):
            return await self.vt_research(task=p.get("task", p.get("query", "")))
        elif action == "vt_backtest":
            return await self.vt_backtest(
                codes=p.get("codes", p.get("tickers", ["AAPL"])),
                start_date=p.get("start_date", p.get("start", "2022-01-01")),
                end_date=p.get("end_date", p.get("end", "2024-01-01")),
                strategy_code=p.get("strategy_code"),
                source=p.get("source", "auto"),
                engine=p.get("engine", "daily"),
                interval=p.get("interval", "1D"),
            )
        elif action == "shadow_account":
            return await self.shadow_account(journal_path=p.get("journal_path", ""))
        elif action == "vt_swarm":
            return await self.vt_swarm(
                preset=p.get("preset", "investment_committee"),
                variables=p.get("variables", {}),
            )
        elif action == "vt_skills":
            return await self.vt_skills(search=p.get("search"))
        elif action == "vt_export":
            return await self.vt_export(
                strategy_code=p.get("strategy_code", ""),
                target=p.get("target", "pine"),
            )
        return {"status": "error", "error": f"unknown action: {action}"}

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
