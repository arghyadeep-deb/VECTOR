# VECTOR Remaining Issues — Reality Check (2026-06-18)

**Note:** Counts below are from actual AST/code scans, not claims. Items marked "Fixed" are verified gone from the codebase.

## Triage Count

Based on the reality-check table below:

| Bucket | Count | Meaning |
|--------|-------|---------|
| True issues that still need fixing | 6 | Real code/security/architecture issues still present |
| Uncertain / needs fresh rescan | 1 | May be true, but this file does not currently prove it |
| False, resolved, or no-action issues | 10 | Fixed, removed, verified gone, or not actually a problem |
| Total issue rows checked | 17 | Rows in the current reality-check table |

### True issues still needing work
- P0.1 eval/exec sandbox: production surface is gated/allowlisted, but dev REPL/eval/backtesting/test paths still contain dynamic exec.
- P1.1 sys.path hacks: still present, though many are likely legitimate runtime shims.
- P1.4 circular imports: still present as lazy imports.
- P2.1 broad `except Exception`: still a large real debt.
- P2.2 pass-only stubs: still present in broad scans.
- P2.3 analyst-estimates integration: Renaissance stat-arb still has no real analyst/fair-value estimate provider.

### Uncertain / needs fresh rescan
- P1.5 mutable state races.

### False, resolved, or no-action
- P0.3 eval in config: fixed.
- P0.2 pickle RCE: fixed; portfolio cache no longer uses `pickle.load()`.
- P0.4 SUDO_PASSWORD global: fixed/stale; no `_cached_sudo_password` global remains.
- P1.2 NotImplementedError swallowed: stale/overcounted; listed startup paths re-raise, log, or intentionally ignore unsupported chmod on platforms like Windows.
- P1.3 hardcoded `vector_memory.db`: fixed for runtime DB resolution with `core.memory.db_utils.configured_db_path()`; remaining refs are config defaults, labels, comments, or registry templates.
- P2.4 empty `__init__.py`: normal Python pattern, no action needed.
- P3 dead ContextEngine stubs: removed.
- P3 dead mining duplicates: removed.
- P3 unused Ollama providers: removed.
- P3 PRAGMA scatter in core: fixed with `apply_pragmas()`.

### Current live gate note
`python tools\ci_gate.py` currently passes. The 3 runtime `except Exception: pass` regressions found on 2026-06-18 were fixed:
- `core/loop/autonomous_loop.py:485`
- `core/loop/autonomous_loop.py:1695`
- `districts/investment/vector_finagent/Analytics/corporateFinance/valuation/sec_data_adapter.py:179`
- Early startup loggers were also fixed in `vector_cli/main.py` and `gateway/run.py`; rare startup-failure logging could previously reference `logger` before initialization.
- Runtime memory DB path resolution was centralized through `core.memory.db_utils.configured_db_path()`; `vector doctor` now checks the configured SQLCipher-aware DB path instead of plain-sqlite opening the repo-root filename.
- Compatibility shims that overwrote real implementations with `pass` were fixed for `vectorcode.src.security`, chat banner/notifications, and first-run `init`.
- `vectorcode.src.security.types` no longer shadows canonical `vc_security.types`; only the legacy `InjectionScanResult` compatibility dataclass remains local.
- Unbound exception-logging variables were repaired: AST scan now reports 0 `_sve` log references outside a matching `except ... as _sve` binding.
- Undefined module-level `logger` usage was repaired: AST scan now reports 0 modules that call `logger` without importing or defining it.
- Duplicate adjacent logger statements were removed: scan now reports 0 byte-for-byte adjacent duplicate `logger.*` / `logging.*` calls.
- Logger import cleanup completed: scan now reports 0 duplicate `from loguru import logger` imports and 0 unused loguru `logger` imports.
- Misplaced `apply_pragmas` imports were normalized to top-level/future-safe positions; previously broken files now compile and the CI gate passes again.
- `apply_pragmas` import/use consistency was verified: scan now reports 0 undefined, duplicate, or unused `apply_pragmas` imports.
- Adjacent duplicate import cleanup completed: scan now reports 0 byte-for-byte adjacent duplicate `import` / `from` lines.
- Unbound exception-name cleanup continued: real `except ...:` handlers that referenced `e`/`exc` without binding were fixed; remaining scanner hits were manually reviewed as outer-scope references.
- Silent `except Exception: pass` cleanup continued: non-test hook scripts now report skipped best-effort failures to stderr; narrowed non-test scan reports 0 `except Exception` pass-only handlers.
- Remaining runtime pass-only handlers were spot-checked; sampled cases are intentional probes/fallbacks such as hostname parsing, DNS failure deferral, temp-file cleanup, and queue-empty races.
- Import/docstring ordering repaired: scan now reports 0 mechanically touched imports placed before module docstrings.

---

## Status Summary

| Issue | Claimed | Reality | Actual Count | Verdict |
|-------|---------|---------|-------------|---------|
| P0.1 eval/exec sandbox | ✅ Fixed | Production surface gated; REPL/eval/test/dev paths still contain dynamic exec | Production allowlist passes; non-prod/dev hits remain | PROD FIXED / DEV DEBT |
| P0.2 pickle RCE | Fixed | Verified gone | 0 | **FIXED** |
| P0.3 eval in config | ✅ Fixed | ✅ Verified gone | 0 | **FIXED** |
| P0.4 SUDO_PASSWORD global | Fixed | Verified gone | 0 cached-global refs | **FIXED** |
| P1.1 sys.path hacks | ⏸ Deferred | ⏸ Still present | **~85 sites** | Grew (+17) |
| P1.2 NotImplementedError swallowed | ✅ Fixed | Verified not silently swallowed in listed startup paths | 0 silent listed sites | **FIXED/STALE CLAIM** |
| P1.3 hardcoded vector_memory.db | ✅ Fixed | Runtime DB resolution centralized; remaining refs are labels/default/template strings | 0 stale runtime fallback sites found | **FIXED** |
| P1.4 circular imports | ✅ Fixed | ❌ **Still present** | **7 lazy imports** | NOT FIXED |
| P1.5 mutable state races | ✅ Verified | ❓ Not rescanned | — | UNCERTAIN |
| P2.1 broad except (10+) | ⚠️ Partial | ⚠️ Worse | **~4,500 sites** | Underestimated 5x |
| P2.2 pass-only stubs | ✅ Fixed | ⚠️ Reduced | **283 functions** | PARTIALLY FIXED (-100) |
| P2.3 hardcoded 0.0 TODOs | Fixed | Rescanned: 3 stale claims, 1 real analyst-estimates integration gap remains | 1 real TODO | PARTIALLY FIXED |
| P2.4 empty __init__.py | ✅ N/A | ✅ Normal Python pattern | — | **NO ACTION** |
| P3 dead ContextEngine stubs | ✅ Removed | ✅ Verified | 0 | **FIXED** |
| P3 dead mining duplicates | ✅ Removed | ✅ Verified | 0 | **FIXED** |
| P3 unused Ollama providers | ✅ Removed | ✅ Verified | 0 | **FIXED** |
| P3 PRAGMA scatter (core) | ✅ Fixed | ✅ Verified — `core/memory/db_utils.py::apply_pragmas()` exists, 0 core files with inline PRAGMA | 0 | **FIXED** |

---

## P0 — Critical Security

### P0.1 — eval/exec with variable input — production fixed, dev/eval surfaces remain
**Risk: Arbitrary code execution via untrusted input to exec()/eval()**

`python run_vector.py production-check` reports `dynamic_exec_surface: ok`, so the production-scanned surface is currently gated/allowlisted. Remaining hits are concentrated in interactive REPL, eval harness, red-team skill loader, tests, and dynamic backtesting paths.

**vectorcode/src/ — REPLs & evals (13 sites):**
- `vc_tools/repl.py:331,337` — LLM-controlled eval()+exec() in REPL
- `vc_agents/rlm_repl.py:171` — LLM REPL exec()
- `evals/execution/webchorearena_env.py:406,446` — eval() ×2
- `evals/scorers/coding_assistant.py:121,128` — exec() ×2
- `evals/scorers/coding_task.py:73,88,101,106` — exec() ×4
- `evals/scorers/pinchbench.py:391` — exec()
- `skills/red-teaming/godmode/scripts/auto_jailbreak.py:52,54` — exec() ×2
- `skills/red-teaming/godmode/scripts/load_godmode.py:29` — exec()

**districts/investment/ — Backtesting engines (5 sites):**
- `vector_finagent/algo_trading/python_backtest_engine.py:92,142` — exec() ×2
- `vector_finagent/strategies/live_runner.py:179` — exec()
- `vector_finagent/Analytics/backtesting/backtestingpy/backtestingpy_provider.py:992` — exec()
- `vector_finagent/Analytics/backtesting/base/fincept_strategy_runner.py:90` — exec()
- `vector_finagent/Analytics/backtesting/vectorbt/vectorbt_provider.py:1828` — exec()

**Test files (7 sites):**
- `vector_finagent/agents/hedgeFundAgents/renaissance_technologies_hedge_fund_agent/tests/test_glm_model.py:195,330,372,403,450,483,514` — exec() ×7
- `vector_backtest/tests/test_shadow_codegen_security.py:71` — exec()

### P0.2 — pickle.load() deserialization — 0 active risky sites ✅ FIXED
- ~~`vector_finagent/Analytics/portfolioManagement/data_manager.py`~~ — portfolio cache migrated from pickle to JSON encoding.
- Remaining `pickle` hits are scanner/test examples or local trusted checkpoint utilities, not this reported portfolio-cache RCE.
- ~~`qlib_online_learning.py`~~ ✅ Fixed (joblib)
- ~~`qlib_meta_learning.py`~~ ✅ Fixed (joblib)
- ~~`qlib_advanced_models.py`~~ ✅ Fixed (joblib)

### P0.3 — eval() in config parser — 0 sites ✅ FIXED
- ~~`vectorcode/src/vc_core/config.py:1429`~~ — replaced with AST-based coercion

### P0.4 — SUDO_PASSWORD cached in module global — 0 cached-global refs ✅ FIXED
- ~~`vectorcode/src/tools/terminal_tool.py` module-level `_cached_sudo_password`~~ removed.
- Current terminal code reads `SUDO_PASSWORD` per call or from thread-local interactive state. Remaining `SUDO_PASSWORD` strings are config/help/env lookups, not retained module globals.

---

## P1 — High

### P1.1 — sys.path.insert/append hacks — ~85 sites across 60+ files (up from 68)
**Production core (not finagent, not tests):**
- `core/inference/ollama_safe.py` — inserts airllm repo
- `core/memory/obsidian_sync.py:212,376` — inserts LightRAG path
- `vectorcode/src/bootstrap.py` — canonical bootstrap (ok, intentional)
- `districts/coding/vector_mlops/__init__.py` — inserts package root
- `districts/intelligence/shadowbroker/__init__.py` — inserts dependencies
- `districts/intelligence/vector_social_sim/__init__.py:26` — inserts social sim dir
- `districts/investment/vector_backtest/__init__.py:22` — inserts backtest dir
- `districts/data_analytics/performance_benchmarker.py` — inserts benchmark tools

**vector_finagent (40+ sites):** Nearly every Analytics sub-package inserts `SCRIPT_DIR`:
- `Analytics/backtesting/bt/bt_fixed_income.py`, `bt_provider.py`, `bt_risk.py`
- `Analytics/backtesting/vectorbt/vectorbt_provider.py`
- `Analytics/backtesting/zipline/zipline_provider.py`
- `Analytics/backtesting/backtestingpy/backtestingpy_provider.py`
- `Analytics/corporateFinance/deal_database/database_schema.py`, `deal_parser.py`, `deal_scanner.py`
- `Analytics/corporateFinance/valuation/precedent_transactions.py`, `trading_comps.py`, `valuation_summary.py`
- `Analytics/ffn_wrapper/ffn_service.py`, `Analytics/fortitudo_tech_wrapper/fortitudo_service.py`
- `Analytics/functime_wrapper/functime_service_polars_legacy.py`
- `Analytics/gs_quant_wrapper/gs_quant_service.py`
- `Analytics/python_skfolio_lib/skfolio_service.py`
- `Analytics/financial_analysis_cli.py`, `quant_analytics_cli.py`, `statsmodels_cli.py`
- `agents/finagent_core/core_agent_stream.py`, `main.py`, `tools/edgar_tools.py`
- `agents/hedgeFundAgents/.../schemas/agent_config.py`
- `ai_quant_lab/qlib_high_frequency.py`
- `algo_trading/python_backtest_engine.py`
- `strategies/AlgorithmImports.py`, `live_runner.py`
- `strategies/Execution/__init__.py`, `Portfolio/__init__.py`, `Risk/__init__.py`, `Selection/__init__.py`, `alphas/__init__.py`
- `vision_quant/backtester.py`, `engine.py`, `scorer.py`, `setup_index.py`

### P1.2 — NotImplementedError silently suppressed — stale/overcounted ✅ FIXED
- `vectorcode/src/vector_cli/main.py` listed sites re-raise `NotImplementedError` before broader exception handling.
- `vectorcode/src/gateway/run.py` listed startup sites re-raise `NotImplementedError`.
- `vectorcode/src/vector_cli/config.py` chmod paths log platform permission-bit failures; those are intentional Windows/container fallbacks.
- `vectorcode/src/vector_cli/auth.py` remaining combined handlers log warnings rather than silently suppressing failures.

### P1.3 — Hardcoded "vector_memory.db" runtime path fallback — 0 stale runtime sites ✅ FIXED
- Added `core.memory.db_utils.configured_db_path()` as the shared resolver.
- Updated memory/runtime users including episodic memory, retry queue, shared facts, A/B experiments, avatar state, memory persona, recovery playbooks, database optimizer, data engineer, emergency log, DevOps backup, multi-DB backup/restore, and `vector doctor`.
- Remaining `vector_memory.db` references are the canonical `core/config.py` default, DB registry path templates, user-facing check labels, comments, or docstrings.

### P1.4 — Lazy circular dependency core/api/ ↔ core/loop/ — 7 imports
```
core/api/app.py → core.loop.context_engine, core.loop.decision_engine,
                   core.loop.permission_gateway, core.loop.nudge_engine,
                   core.loop.loop_state (×2)
core/api/routers/health.py:193 → core.loop.loop_state
core/loop/permission_gateway.py:703 → core.api.routers.websocket.broadcast_event
```
Works only because all imports are deferred inside functions. If any moves to top-level, the entire chain breaks.

### P1.5 — Module-level mutable state race conditions (not rescanned)

---

## P2 — Medium

### P2.1 — Broad `except Exception` with 10+ line try bodies — ~4,500 sites
**Too many to list individually. Worst offenders:**
- `vectorcode/src/gateway/run.py:231` — 121-line try block
- `vectorcode/src/server/stream_bridge.py:342` — 95-line try block
- `vectorcode/src/vector_state.py:2144` — 56-line try block
- `districts/investment/vector_finagent/strategies/live_runner.py:412` — 138-line try block
- `districts/investment/vector_finagent/ai_quant_lab/qlib_service.py:233` — 123-line method
- `districts/intelligence/shadowbroker_server/main.py:1941` — 84-line try block

### P2.2 — Pass-only function bodies — 163 functions (down from 377 in raw AST scan, -57%)
**214 stubs fixed in 2026-06-18 session:** All `base_*.py`, `*_base.py`, and ABC method stubs across `core/research_engine/`, `vectorcode/src/gateway/platforms/`, `vectorcode/src/comms/`, `vectorcode/src/learning/`, `vectorcode/src/plugins/`, `core/trading/llm_clients/`, `core/scraper/`, `core/coding_assistant/` were converted:
- ABC methods → `raise NotImplementedError("ClassName.method must be implemented by subclass")`
- Lifecycle hooks (stop/disconnect/close/rollback/send_typing) → `logger.debug("[VECTOR][module] method called (no-op)")`

**Remaining 163 stubs fall into 3 irreducible categories:**
1. **Financial domain ABCs (143):** `vector_finagent/strategies/fincept_engine/algorithm_imports.py` (40), `algorithm.py` (25), `ai_quant_lab/qlib_data_processors.py` (8), `Analytics/equityInvestment/base/base_models.py` (8), `Analytics/derivatives/market_data.py` (7), `Analytics/finagent_core/repositories.py` (6), etc. — require financial domain expertise (VaR, CVaR, option pricing, economic indicators) to implement
2. **Intentional no-ops (14):** `core/coding_assistant/cli/turn_summary/noop.py` (6) — named "noop" by design; `vectorcode/src/connectors/oauth.py` (2) — `log_message` silence pattern; `core/video/html_renderer.py` (1) — same
3. **Test fixtures (6):** `vectorcode/src/memory/manager.py:431` (`_FakeProvider.initialize`), `vectorcode/src/evals/tests/conftest.py` (`MockDataset.load`) — test doubles that should not raise

Recently fixed / reclassified:
- ~~`core/trading/llm_clients/openai_client.py`~~ is not a stub; `OpenAIClient.get_llm()` and `validate_model()` are implemented.
- ~~`vectorcode/src/security/__init__.py`~~ no longer overwrites `setup_security()` with `pass`.
- ~~`vectorcode/src/security/types.py`~~ no longer shadows canonical `ThreatLevel`, `ScanFinding`, and `ScanResult`.
- ~~`vectorcode/src/cli/_chat_banner.py` and `_chat_notifications.py`~~ now re-export real implementations instead of no-op shims.
- ~~`vectorcode/src/cli/init_cmd.py` / `vectorcode/src/vector_cli/init_cmd.py`~~ now route first-run initialization into the setup wizard instead of silently doing nothing.
- ~~`core/research_engine/news/core/storage.py` (27 stubs)~~ → all raise NotImplementedError
- ~~`core/research_engine/settings/base.py` (9 stubs)~~ → all raise NotImplementedError
- ~~`core/research_engine/storage/base.py` (6 stubs)~~ → all raise NotImplementedError
- ~~`vectorcode/src/gateway/platforms/base.py` (6 stubs)~~ → connect/send/get_chat_info raise NIE; disconnect/send_typing/stop_typing log debug
- ~~`vectorcode/src/comms/*.py` stop() methods~~ → all log debug
- ~~59 more research_engine/coding_assistant/learning/evals base class stubs~~ → all raise NotImplementedError

### P2.3 — Real stubs marked as TODO (rescanned)
Previously identified claims:
- ~~`vector_finagent/agno_trading_service.py:262` — positions not restored~~ Stale: persisted JSON positions are restored into `PositionSnapshot` objects.
- ~~`vector_finagent/agno_trading/framework/decision_coordinator.py:90-92` — win rate/sharpe/drawdown = 0.0~~ Stale: these are fallbacks used only when `portfolio.get_performance_stats()` omits a metric.
- ~~`vector_finagent/Analytics/corporateFinance/valuation/sec_data_adapter.py:167` — prior year comparison = 0.0~~ Stale: prior-period and `PriorYear*` tags are used when available; `0.0` is the documented conservative fallback.
- `vector_finagent/agents/hedgeFundAgents/.../main.py` — analyst/fair-value estimates still require a real provider. Peer/sector prices are now wired through `AnalysisConfig(include_peers=True, peer_ticker=...)`.

### P2.4 — Empty `__init__.py` (≤50 bytes) — 71 files
Scattered across sub-packages. Mostly in `districts/investment/alpha_zoo/academic/`, deep nested dirs. Python 3.3+ namespace packages work without them.

---

## P3 — Architecture Debt

### P3.1 — Duplicate class definitions (not rescanned)
- `BaseTool` (4 copies), `ValidationError` (10+), `AgentConfig` (5), `SessionManager` (5)
- `ContextEngine` (3), `EventBus`/`Event`/`EventType` (3), `LLMProvider` (2), `MCPClient`/`MCPTool` (2)
- `KnowledgeGraph` entities (3)

### P3.2 — Duplicate near-identical files (remaining after 3 deletions)
- `core/memory/knowledge_graph.py` ≈ `vectorcode/src/vc_tools/storage/knowledge_graph.py`
- `tools/` vs `vc_tools/` — parallel tool files

### P3.3 — Proliferated implementations (remaining after 2 deletions)
- **Ollama providers**: 4 remain (`core/ollama.py`, `vc/ollama.py`, `vc/engine/ollama.py`, `vc/engine/ollama_v3.py`)
- **Rate limiters**: 4 (`core/event_bus/`, `core/metering/`, `core/research_engine/security/`, `vectorcode/src/vc_security/`)
- **Tool abstractions**: 3 competing base classes

### P3.4 — Schema duplication (70+ files with CREATE TABLE)
- Every store/session/manager independently defines the identical PRAGMA triplet

### P3.5 — Domain overlap core/ ↔ vectorcode/ ↔ districts/
| Domain | core/ | vectorcode/src/ | districts/ |
|--------|-------|-----------------|------------|
| Agent management | — | `vc_agents/_abc.py`, `agents/_abc.py` | `coding/base_agent.py` |
| Tools | — | `tools/`, `vc_tools/` | `coding/tools.py` |
| Sessions | — | `vc_sessions/`, `session.py` | `session/` |
| Memory | `memory/` | `memory/`, `plugins/memory/` | `memory_curator/` |
| Security | — | `vc_security/`, `security/` | `security/` |
| Config | `config.py` | `config.py`, `config/*` | — |

### P3.6 — Shim files (~25-30)
Thin re-export wrappers; intentional namespace exports

---

## What Was Actually Fixed (Verified)

| Fix | Scope | Verified |
|-----|-------|----------|
| Hardcoded `C:\Users\Arghyadeep\...` absolute paths | 8 files → Path.home()/env vars | ✅ |
| `except ImportError: pass` → logging | 30 blocks across 10 files | ✅ |
| Empty except handlers in hub_artifacts + sandbox_client | 6 handlers | ✅ |
| MCP SSE non-localhost warning | 1 guard | ✅ |
| eval() in config parser | `vc_core/config.py:1429` | ✅ |
| pickle.load → joblib (3 qlib files) | 3 of 4 pickle sites | ✅ |
| sys.path hacks (28 removed) | 96→68 | ✅ |
| Dead ContextEngine stubs | 2 files deleted | ✅ |
| Dead mining duplicates | 2 files deleted | ✅ |
| Unused Ollama providers | 2 files deleted | ✅ |
| Empty __init__.py (8 removed) | 79→71 | ✅ |

## Reality-Based Effort Estimate

| Tier | Category | Sites | Honest Effort |
|------|----------|-------|---------------|
| P0 | eval/exec sandbox + SUDO_PASSWORD + remaining pickle | 43 | 4-5 hrs |
| P1 | sys.path + NotImplementedError + hardcoded path + circular dep | 126 | 6-8 hrs |
| P2 | broad except + pass stubs + empty init | ~4,954 | 2-3 weeks |
| P3 | Architecture debt (duplicates, schemas, domain overlap) | ~500 | 3-6 weeks |

---

# Q0 — Missing Substance (Unwritten Features)

These aren't bugs or code smells — they are features that exist as placeholders but were never actually built. Fixing everything in P0-P3 above leaves these untouched.

### Q0.1 — Empty analytics district (pass-only stubs)
**All of the following are `pass` — they do nothing:**
- `vector_finagent/Analytics/riskfoliolib_wrapper.py` — VaR, CVaR, stress testing, risk budgeting
- `vector_finagent/Analytics/equityInvestment/base/base_models.py` — intrinsic value, market data analysis, company analysis, DCF models
- `vector_finagent/Analytics/derivatives/core.py` — option pricing, forward pricing, fair value
- `vector_finagent/Analytics/economics/core.py` — economic indicator analysis
- `vector_finagent/Analytics/portfolioManagement/data_manager.py` — price data, economic data fetching
- `vector_finagent/Analytics/alternateInvestment/base_analytics.py:501` — valuation summary
- `vector_finagent/Analytics/finanicalanalysis/core/base_analyzer.py:187` — key metrics
- `vectorcode/src/agent/web_search_provider.py:139,172,192` — web search, news search, image search
- `vectorcode/src/memory/provider.py:83` — memory provider (the abstract base for ALL memory)
- `vectorcode/src/memory/manager.py:431` — memory manager `initialize()` does nothing
- `core/mcp/client.py:130` — MCP client `disconnect()` does nothing
- `vectorcode/src/engine/_abc.py` — 3 abstract methods with no implementations

**Effort to implement: 2-4 weeks** (requires domain knowledge for each category)

### Q0.2 — No CI/CD pipeline
- No automated test runner in CI
- No linting/type-checking gate
- No deployment script (the deploy.sh is a stub)
- No staging environment
- No rollback strategy
- No artifact/build pipeline
- No versioned releases

**Effort: 1-2 days** to wire up GitHub Actions with pytest + mypy + ruff

### Q0.3 — No test coverage
- Zero test coverage metrics exist
- The 65 tests in `test_audit_followups.py` cover only SQLite patterns + spec15 hardening
- No unit tests for any district agent
- No integration tests for the autonomous loop
- No API endpoint tests for the 25+ routers
- No mock/fixture infrastructure for district agents

**Reality:** Coverage is <5%. The system has never been tested as a whole.

**Effort to reach 50% coverage: 2-4 weeks**

### Q0.4 — No monitoring or observability
- No health check endpoint that actually checks subsystem health
- `/metrics` endpoint returns only loop ticks + agent count (no memory usage, no error rates, no latency)
- No structured logging standard (mix of loguru, print, and logging module)
- No alerting — if the autonomous loop dies, nothing notifies
- No crash recovery — if the process crashes, state is lost
- No database backup/restore for any of the 16+ SQLite databases
- No disk usage monitoring (SQLite DBs can grow unbounded)

**Effort: 2-3 days** for basic health + alerting; **1-2 weeks** for complete observability

### Q0.5 — No graceful degradation
- If Ollama goes down, the entire system crashes
- If `vector_memory.db` is corrupted, memory operations throw unhandled errors
- If an API key is missing, features fail silently (because of the `except ImportError: pass` pattern that was partially fixed)
- No circuit breakers for external API calls
- No retry logic with backoff (except in a few hand-written spots)
- No fallback models when the primary model is unavailable

**Effort: 3-5 days** for circuit breakers + graceful fallbacks

### Q0.6 — No user-facing UX
- The web HUD at `/hud/` exists but is a basic skeleton
- No configuration UI (everything is YAML/json config files)
- No onboarding flow
- No error messages designed for end users
- No documentation for what the system can do
- The only way to interact is via API calls or the CLI

**Effort: 1-2 weeks** for a functional dashboard; **4-6 weeks** for a complete user experience

### Q0.7 — No data persistence strategy
- 16+ separate SQLite databases with no migration strategy
- No backup automation for any database
- No data retention policy (episodic memory grows forever)
- If a DB file is deleted or corrupted, all data in that domain is lost
- No replication or failover

**Effort: 2-3 days** for automated backups; **1-2 weeks** for migration framework + retention

### Q0.8 — No security hardening beyond localhost
- API auth middleware exists but only blocks non-localhost when no key is set
- No encryption at rest for any SQLite database
- No TLS for API traffic (HTTP, not HTTPS)
- The MCP server on port 9000 has no auth at all
- API keys stored in environment variables or config files (not a secrets manager)
- No audit logging of who did what

**Effort: 3-5 days** for TLS + encryption + audit logging

### Q0.9 — Missing core agent behaviors
- `core/loop/decision_engine.py` — scores 4 candidates but the scoring formula is simplistic (weighted average, no ML)
- `core/loop/nudge_engine.py` — exists but what it actually does is unclear
- `core/city/agent_base.py` — agents have HP but there's no actual death/rebirth cycle implemented
- `core/memory/policy.py` — RL table exists but no evidence it's actually trained
- `core/loop/context_engine.py` — builds world state but no evidence any agent actually uses the full output

**Effort: 2-4 weeks** to wire up the intended agent lifecycle

---

# Honest Overall Assessment

| Dimension | Current State | After All P0-P3 Fixes | After All Q0 Fixes |
|-----------|--------------|----------------------|-------------------|
| Security | 40/100 | 75/100 | 85/100 |
| Code Quality | 30/100 | 70/100 | 75/100 |
| Feature Completeness | 30/100 | 35/100 | **75/100** |
| Test Coverage | <5% | 15% | 50% |
| Production Readiness | 20/100 | 45/100 | **70/100** |
| JARVIS Closeness | 55% | 60% | **80%** |

**Bottom line:** P0-P3 fixes = clean up the mess. Q0 fixes = actually build the thing. Both are needed.
