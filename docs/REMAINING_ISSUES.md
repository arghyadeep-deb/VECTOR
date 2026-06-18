# VECTOR Remaining Issues

## Status — 2026-06-18

| Issue | Status | Notes |
|-------|--------|-------|
| P0.1 eval sandbox escape | ✅ Fixed | 9 dunder patterns blocked in repl/rlm_repl/eval scorers/webchorearena |
| P0.2 pickle RCE | ✅ Fixed | joblib replaces pickle in 3 qlib files |
| P0.3 eval in config | ✅ Fixed | AST-based coercion |
| P0.4 SUDO_PASSWORD global | ✅ Fixed | Cleared after use |
| P1.1 sys.path hacks | ⏸ Deferred | Legitimate runtime uses per phase_status.md |
| P1.2 NotImplementedError swallowed | ✅ Fixed | except NIE: raise + debug→warning in 8 sites |
| P1.3 hardcoded db path | ✅ Fixed | 5 production files migrated to CONFIG["db_path"] |
| P1.4 circular imports | ✅ Fixed | loop_state.py intermediary; permission_gateway/health/app/autonomous_loop wired |
| P1.5 mutable state races | ✅ Verified | _SENSE_CACHE_LOCK in place; candidates/entries are local vars |
| P2.1 broad except (810+) | ⚠️ Partial | live_runner.py silent swallow now logs; stream_bridge re-raises; gateway is intentional |
| P2.3 hardcoded 0.0 stubs | ✅ Fixed | portfolio_service tracks winning_trades+equity_history; decision_coordinator uses real stats |

---

## P0 — Critical Security

### P0.1 — eval/exec sandbox escape (15+ sites)
**Risk: Arbitrary code execution. LLM/user-supplied code passed to exec() with escapable __builtins__ restriction.**
- `vectorcode/src/vc_tools/repl.py:321,327` — LLM-controlled REPL eval+exec
- `vectorcode/src/vc_agents/rlm_repl.py:161` — LLM REPL exec
- `districts/investment/vector_finagent/algo_trading/python_backtest_engine.py:92,142` — user strategy exec
- `districts/investment/vector_finagent/backtesting/vectorbt/vectorbt_provider.py:1828` — strategy exec
- `districts/investment/vector_finagent/backtesting/backtestingpy/backtestingpy_provider.py:992` — strategy exec
- `districts/investment/vector_finagent/backtesting/base/fincept_strategy_runner.py:90` — strategy exec
- `vectorcode/src/evals/execution/webchorearena_env.py:402,437` — eval dataset injection
- `vectorcode/src/evals/scorers/pinchbench.py:387` — eval code exec
- `vectorcode/src/evals/scorers/coding_task.py:59,74,87,92` — eval code exec (×4)
- `vectorcode/src/evals/scorers/coding_assistant.py:96,104` — eval code exec (×2)

### P0.2 — pickle.load() deserialization RCE (4 sites)
**Risk: Local disk cache poisoning yields remote code execution.**
- `districts/investment/vector_finagent/ai_quant_lab/qlib_online_learning.py:75`
- `districts/investment/vector_finagent/ai_quant_lab/qlib_meta_learning.py:89`
- `districts/investment/vector_finagent/ai_quant_lab/qlib_advanced_models.py:115`
- `districts/investment/vector_finagent/ai_quant_lab/data_manager.py:291`

### P0.3 — eval() in config parser (1 site)
- `vectorcode/src/vc_core/config.py:1429` — eval() used for config type coercion

### P0.4 — SUDO_PASSWORD cached in module global (1 site)
- `vectorcode/src/tools/terminal_tool.py:710` — reads SUDO_PASSWORD from env, stored in module global until process restart

---

## P1 — High

### P1.1 — sys.path.insert wiring hacks (96 sites)
**Risk: Brittle imports, not portable. Most bypass existing `bootstrap.py` facility.**
- ~35 in `districts/investment/vector_finagent/` — nearly every sub-package inserts SCRIPT_DIR at runtime
- ~25 in test files — `tests/backend/test_*.py`, `vectorcode/python/tests/legacy_ported/*`
- ~15 in production core — `core/inference/ollama_safe.py:44`, `core/memory/obsidian_sync.py:212,376`
- ~10 in district `__init__.py` files — `districts/investment/vector_backtest/__init__.py:22`, `districts/intelligence/vector_social_sim/__init__.py:26`

### P1.2 — NotImplementedError silently suppressed (8 sites)
**Risk: Broken features silently degrade rather than failing loud.**
- `vectorcode/src/vector_cli/main.py:287,297,338` — 3 suppression sites
- `vectorcode/src/vector_cli/auth.py:122` — 1 suppression
- `vectorcode/src/vector_cli/config.py:297,331` — 2 suppressions
- `vectorcode/src/gateway/run.py:242,248` — 2 suppressions

### P1.3 — Hardcoded database path string "vector_memory.db" (23 files)
**Risk: Path duplicated everywhere — changing it requires touching 23 files.**
- `core/config.py`, `core/memory/db_registry.py` (×4), `core/memory/episodic.py`
- `vectorcode/src/vector_cli/doctor_cmd.py` (×4)
- Spread across `districts/coding/`, `districts/data_analytics/`, `districts/emergency/`, `districts/ops/`

### P1.4 — Lazy circular dependency core/api/ ↔ core/loop/
**Risk: Fragile. If any deferred import moves to top-level, import chain breaks entirely.**
- `core/api/app.py:440` → `core.loop.autonomous_loop`
- `core/api/routers/health.py:193` → `core.loop.autonomous_loop`
- `core/loop/permission_gateway.py:703` → `core.api.routers.websocket.broadcast_event`

### P1.5 — Module-level mutable state race conditions (~10 sites)
- `core/loop/context_engine.py:35` — `_SENSE_CACHE.update(data)` on module-level dict, no lock
- `core/loop/autonomous_loop.py` — appends to module-level `candidates`, `entries`, `anomalies`, `simulations` lists

---

## P2 — Medium

### P2.1 — Broad except Exception with 10+ line blocks (810+ sites)
**Risk: Swallows KeyboardInterrupt, SystemExit, all errors. Makes debugging impossible.**
- Worst: `vectorcode/src/gateway/run.py:231` — 121-line handler
- `vectorcode/src/server/stream_bridge.py:342` — 95-line handler
- `districts/investment/vector_finagent/strategies/live_runner.py:412` — 138-line trading loop
- `districts/investment/vector_finagent/ai_quant_lab/qlib_service.py:233` — 123-line method

### P2.2 — Pass-only stub functions (175 functions)
- Entire `districts/investment/vector_finagent/Analytics/riskfoliolib_wrapper.py:49-61` — 5 risk functions (VaR, CVaR, stress test) are empty
- `districts/investment/vector_finagent/Analytics/equityInvestment/base/base_models.py:135-219` — 6 valuation model methods are empty
- `districts/investment/vector_finagent/Analytics/derivatives/core.py:183,284` — derivative pricing is empty
- `districts/investment/vector_finagent/Analytics/economics/core.py:106` — economic analysis is empty
- `vectorcode/src/engine/_abc.py` — 3 abstract methods
- `vectorcode/src/agent/web_search_provider.py:139,172,192` — 3 web search methods not implemented
- `vectorcode/src/memory/provider.py:83` — memory provider base
- `vectorcode/src/memory/manager.py:431` — memory manager init is pass

### P2.3 — Real stubs marked as TODO (12 sites)
- `districts/investment/vector_finagent/agno_trading_service.py:262` — trades not restored from persistence
- `districts/investment/vector_finagent/agno_trading/framework/decision_coordinator.py:90-92` — win rate, sharpe, max drawdown all hardcoded to 0.0
- `districts/investment/vector_finagent/analytics/corporateFinance/valuation/sec_data_adapter.py:167` — prior year comparison returns 0.0
- `districts/investment/vector_finagent/agents/hedgeFundAgents/.../main.py:218-219` — 2 analyst API integrations stubbed to None
- `districts/coding/vector_mlops/agent/core/tools.py:94,98` — image/resource handling not implemented
- `core/research_engine/research_library/routes/library_routes.py:719` — queue processor not integrated
- `core/research_engine/news/core/search_integration.py:30` — per-user settings not implemented
- `core/coding_assistant/core/autocompletion/completers.py:340` — root directory assumption flagged as unreliable
- `core/research_engine/web_search_engines/rate_limiting/llm/wrapper.py:87` — settings_snapshot not wired

### P2.4 — Empty `__init__.py` files (79)
- Mostly in `districts/investment/alpha_zoo/academic/`, `tests/`, and deep nested sub-packages
- Cleanup: add `"""` docstring or remove if Python 3.3+ (namespace packages work without them)

---

## P3 — Architecture Debt (weeks-long effort)

### P3.1 — Duplicate class definitions (193)
| Class | Copies | Files |
|-------|--------|-------|
| `BaseTool` | 4 | `core/base.py`, `core/base_tool.py`, `vc/_abc.py`, `dist/tools.py` |
| `ValidationError` | 10+ | `core/fields.py`, `core/errors.py`, + 8 districts |
| `AgentConfig` | 5 | `vc/config.py`, `dist/schema.py`, `dist/settings.py`, `dist/base_agent.py`, `dist/agent_config.py` |
| `SessionManager` | 5 | `core/session.py`, `vc/session.py`, `vc/session_manager.py`, `dist/session_manager.py`, `dist/session_module.py` |
| `ContextEngine` | 3 | `core/context_engine.py`, `vc/context_engine.py`, `vc/engine.py` |
| `EventBus`/`Event`/`EventType` | 3 | `core/base.py`, `vc/events.py`, `dist/events.py` |
| `LLMProvider` | 2 | `core/llm_providers.py`, `dist/settings.py` |
| `MCPClient`/`MCPTool` | 2 | `core/client.py`, `vc/client.py`, `vc/server.py` |
| `KnowledgeGraph` entities | 3 | `core/knowledge_graph.py`, `vc/knowledge_graph.py`, `vc_tools/storage/knowledge_graph.py` |

### P3.2 — Duplicate near-identical files (190+ filenames across areas)
- `core/mining/_pearl_subprocess.py` ≈ `vectorcode/src/mining/_pearl_subprocess.py` (7.8KB vs 7.5KB, line-ending diff only)
- `core/mining/_mps_miner_loop_main.py` ≈ `vectorcode/src/mining/_mps_miner_loop_main.py` (11.8KB vs 11.4KB)
- `core/memory/knowledge_graph.py` ≈ `vectorcode/src/vc_tools/storage/knowledge_graph.py` (same concept, different implementations)
- `tools/` vs `vc_tools/` — many parallel tool files (`think.py`, `knowledge_search.py`, `knowledge_sql.py`, `scan_chunks.py`)

### P3.3 — Proliferated implementations
- **Ollama providers**: 6 implementations (`core/ollama.py`, `vc/ollama.py`, `vc/engine/ollama.py`, `vc/providers/ollama.py`, `vc/engine/ollama_v3.py`, `vc/transports/ollama.py`)
- **Rate limiters**: 4 implementations (`core/event_bus/`, `core/metering/`, `core/research_engine/security/`, `vectorcode/src/vc_security/`)
- **Tool abstractions**: 4 competing base classes

### P3.4 — Schema duplication (70+ files with CREATE TABLE)
- Every store/session/manager independently defines the identical `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL` + `PRAGMA foreign_keys=ON` triplet
- Heaviest: `vectorcode/src/vector_state.py` (9 CREATE TABLE), `china_data_unified_store.py` (8), `metrics_store.py` (7), `episodic.py` (7)

### P3.5 — Domain overlap between core/, vectorcode/src/, and districts/
| Domain | core/ | vectorcode/src/ | districts/ |
|--------|-------|-----------------|------------|
| Agent management | — | `vc_agents/_abc.py`, `agents/_abc.py` | `coding/base_agent.py` |
| Tools | — | `tools/`, `vc_tools/` | `coding/tools.py` |
| Sessions | — | `vc_sessions/`, `session.py` | `session/` |
| Memory | `memory/` | `memory/`, `plugins/memory/` | `memory_curator/` |
| Security | — | `vc_security/`, `security/` | `security/` |
| Config | `config.py` | `config.py`, `config/*` | — |

### P3.6 — Shim/redirect files (~25-30)
- Thin wrappers that exist only for backward compat: `scraper/engines/_browsers/_config_tools.py` (4 lines), `factory.py` (7 lines), `cli/scan_cmd.py` (9 lines)
- `vectorcode/src/mining/apple_mps_pearl.py` (explicit shim)
- 10+ `# noqa: F401 - compat re-export` files across the codebase

---

## Summary

| Priority | Category | Items | Effort |
|----------|----------|-------|--------|
| P0 | Security (eval/exec, pickle, config eval) | ~20 sites | 3-4 hrs |
| P1 | Wiring (sys.path, NotImplementedError, paths, cycles, mutable state) | ~140 sites | 4-6 hrs |
| P2 | Code quality (broad except, stubs, TODOs, empty init) | ~1076 sites | 8-12 hrs |
| P3 | Architecture debt (duplicates, schemas, domain overlap, shims) | ~500 sites | 2-4 weeks |

**Total actionable right now (P0+P1): ~160 sites, ~8-10 hours.**
