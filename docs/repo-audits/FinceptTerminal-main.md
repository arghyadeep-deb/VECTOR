# FinceptTerminal-main Audit

**Date:** 2026-06-01
**Auditor:** Claude Sonnet 4.6 (automated)
**Repo path:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\FinceptTerminal-main`
**VECTOR location:** `districts/investment/vector_finagent/` (full script mirror + agent wrappers)

---

## 1. Repo Reality

### What it is
Fincept Terminal v4 is a native C++20/Qt6 Bloomberg-style financial workstation with embedded Python analytics. It is dual-licensed: AGPL-3.0 (personal/academic) with a paid commercial license required for any business use.

### Scale
| Dimension | Count |
|-----------|-------|
| C++ source files | ~1,626 (`.cpp`/`.h`, ~342,000 LOC) |
| Python scripts | ~1,423 (scripts/ directory, 360 entries in top-level scripts/) |
| Qt6 screens | 54 (lazy-instantiated) |
| Bounded contexts (C++) | 13 (Markets, News, Economics, Geopolitics, Trading, Portfolio, Crypto, Derivatives, Predictions, Agents, AI Chat, Workflow, Identity) |
| Broker integrations | 16 equity/F&O + 2 crypto exchanges |
| MCP tools | 40+ |
| Data connectors | 100+ |

### Python analytics structure (the 1,423 scripts)
Located in `fincept-qt/scripts/`. Categories:

**Analytics/ — Multi-domain quant library (most valuable)**
| Subdirectory | Contents |
|-------------|----------|
| `equityInvestment/` | DCF models, dividend models, multiples, residual income, private valuation, company analysis (fundamental/industry/forecasting), market analysis (efficiency, structure, index) |
| `portfolioManagement/` | Portfolio analytics, optimization (PyPortfolioOpt), active management, behavioral finance, ETF analytics, risk management, quantstats, ffn |
| `derivatives/` | Options analytics, arbitrage, forward commitments, market data, core pricing |
| `fixedIncome/` | Bond pricing/portfolio, credit analysis, duration/convexity, yield curve, sovereign credit, structured products |
| `economics/` | Business cycle, capital flows, currency analysis, equity risk premium, exchange rates, growth/market cycle analysis, policy analysis, trade/geopolitics |
| `corporateFinance/` | LBO models, merger models, M&A analytics (deal structure, comparison, fairness opinion, synergies), startup valuation, industry metrics |
| `alternateInvestment/` | 24 asset types: hedge funds, private capital, REITs, digital assets, precious metals, convertible bonds, managed futures, structured products, etc. |
| `backtesting/` | 6 engines: backtestingpy, bt, vectorbt, zipline, fasttrade, fincept (with bridge adapters per engine) |
| `finanicalanalysis/` | Income statement, balance sheet, cash flow analyzers; specialized analysis (financial modeling, financial institutions, inventory, tax, multinational) |
| `technical_analysis/` | Momentum, trend, volatility, volume indicators |
| `quant/` | `quant_modules_3042.py`, rate calculations, base calculator |
| `options/` | GEX calculator, IV smile/surface, OI tracker, straddle simulator, strategy chart |
| Library wrappers | ffn, skfolio, pyportfolioopt, talipp, statsmodels, gluonts, vnpy, gs_quant, functime, fortitudo, tsmoothie, pmdarima |

**agents/ — AI investment agents (config-driven)**
| Agent group | Members |
|------------|---------|
| `TraderInvestorsAgent/` | 7 investor personas: Buffett, Graham, Lynch, Munger, Klarman, Marks, Renaissance (configs with detailed system prompts + scoring weights) |
| `hedgeFundAgents/` | Renaissance Technologies hedge fund agent |
| `EconomicAgents/` | Economic analysis configs |
| `GeopoliticsAgents/` | Grand Chessboard agents, Prisoners of Geography agents |
| `deepagents/` | Multi-provider deep research agent (orchestrator, subagents, backends) |
| `rdagents/` | Research director agents (MCP server, tool registry, task manager) |
| `finagent_core/` | Core agent framework |

**ai_quant_lab/ — Qlib quantitative ML pipeline**
14 scripts: advanced backtesting, models, data processors, feature engineering, high-frequency, meta-learning, online learning, portfolio optimization, RL (`qlib_rl.py`), rolling retraining, strategy, evaluation, reporting.

**Top-level data connectors (360 files)**
100+ data source scripts: AkShare (26 scripts for Chinese/global markets), Yahoo Finance, Alpha Vantage, FRED, IMF, World Bank, OECD, ECB, BIS, Polygon, Intrinio, SEC, EDGAR, DBnomics, Eurostat, government APIs (US, UK, France, Germany, Japan, etc.), crypto feeds (CoinGecko, Glassnode, CoinMarketCap, Dexscreener, HyperLiquid), alternative data (ACLED geopolitics, NOAA climate, NASA, maritime/shipping), Polymarket, Kalshi prediction markets.

**Other script directories**
- `exchange/` — ccxt broker exchange OHLCV/orderbook/position fetch scripts (16 functions)
- `technicals/` — ML-based technical signal scoring
- `vision_quant/` — Vision-based quantitative analysis
- `voice/` — Speech-to-text, TTS (Deepgram, clap detector)
- `agno_trading/` — Agno framework trading agents
- `algo_trading/` — Algorithmic trading scripts
- `alpha_arena/` — Custom alpha discovery framework
- `mcp/` — EDGAR MCP tools

### Qt6 UI panel layout (54 screens)
| Screen | Panel components |
|--------|-----------------|
| `dashboard/` | MarketPulsePanel, TickerBar, DashboardStatusBar, canvas widgets |
| `equity_research/` | Overview, Financials (with populate + views), Analysis, News, Peers, Sentiment, Technicals (talipp), Fundamentals tabs |
| `portfolio/` | Blotter, PerfChart, Heatmap, InsightsPanel, OrderPanel, FFNView, CommandBar |
| `crypto_trading/` | Chart, OrderBook, DepthChart, BottomPanel, Credentials |
| `node_editor/` | Canvas, palette, properties, toolbar — visual workflow DAG |
| `relationship_map/` | GraphScene (force-directed), RelationshipMapScreen |
| `quantlib/` | QuantLibScreen + data populator |
| `algo_trading/` | Algorithmic trading screen |
| `backtesting/` | Backtest screen |
| `ai_quant_lab/` | ML models, qlib UI |
| `alpha_arena/` | Custom alpha discovery UI |
| `derivatives/` | F&O/options screens |
| `markets/` | Multi-asset quotes + sectors |
| `economics/` | FRED/DBnomics/government indicators |
| `geopolitics/` | HDX/ACLED/maritime geopolitics |
| `news/` | News aggregation with AI clustering |
| Other screens | `ma_analytics/`, `surface_analytics/` (IV surface), `trade_viz/`, `watchlist/`, `ai_chat/`, `mcp_servers/` |

### Architecture pattern
Modular monolith: ADS (Advanced Docking System) dock manager, DockScreenRouter (54 lazy factory screens), DataHub pub/sub data plane, C++/Qt6 rendering with Python analytics via PythonRunner subprocess bridge, 26 typed SQLite repositories, SecureStorage (AES-256-GCM).

---

## 2. VECTOR Parity

### Absorption location
Memory claims `core/fincept/` — **this directory does not exist.** The actual absorption is:
- `districts/investment/vector_finagent/` — full mirror of `fincept-qt/scripts/` (360 → 361 entries, 1:1 copy including `Analytics/`, `agents/`, `ai_quant_lab/`, data connectors)
- `districts/investment/vector_finagent/qt/` — full mirror of `fincept-qt/` C++ source (build attempted but no `.exe` produced — `build/win-mingw/` present but incomplete)
- `districts/investment/finagent_agent.py` — FinAgentAgent wrapper (7 routes)
- `districts/investment/backtest_agent.py` — BacktestAgent wrapper (vibe-trading ReAct, 6 routes)
- `districts/investment/hedgebot_agent.py` — HedgeBotAgent wrapper (AutoHedge 5-agent pipeline)
- Other investment agents: `fundamentals_bot.py`, `stock_analyst.py`, `technical_bot.py`, `sentiment_bot.py`

### Verification results

| Feature | VECTOR equivalent | Verified output | Status |
|---------|------------------|-----------------|--------|
| FundamentalsBot (financials, yfinance) | `districts/investment/fundamentals_bot.py` | `FundamentalsBot OK: <class '...FundamentalsBot'>` — imports clean, yfinance check, HP=500 | ✅ |
| AnalyticsReporter (data insights) | `districts/data_analytics/analytics_reporter.py` | `AnalyticsReporter OK: <class '...AnalyticsReporter'>` — episodic + obsidian wired | ✅ |
| FinAgentAgent (investor personas, corporate finance, alpha) | `districts/investment/finagent_agent.py` | `FinAgentAgent OK: <class '...FinAgentAgent'>`, HP=500 | ✅ |
| BacktestAgent (9 engines, LangGraph swarms) | `districts/investment/backtest_agent.py` | `BacktestAgent OK: <class '...BacktestAgent'>`, HP=500 | ✅ |
| HedgeBotAgent (5-agent pipeline, Solana DEX) | `districts/investment/hedgebot_agent.py` — class `HedgeBotAgent` | `HedgeBotAgent OK: <class '...HedgeBotAgent'>`, HP=500 | ✅ |
| TechnicalBot, SentimentBot | `districts/investment/technical_bot.py`, `sentiment_bot.py` | Both import clean, HP=500 | ✅ |
| Analytics library (1,423 Python scripts) | `districts/investment/vector_finagent/` (full mirror, 361 entries) | Directory count matches: 361 VECTOR vs 360 FinceptTerminal | ✅ (mirror present) |
| Qlib ML pipeline (14 scripts) | `districts/investment/vector_finagent/ai_quant_lab/` | 14 qlib_*.py files present | ✅ (mirror present) |
| Investor persona agents (Buffett, Graham etc.) | `vector_finagent/agents/TraderInvestorsAgent/configs/agent_definitions.json` | JSON configs with full system prompts present | ✅ (configs only — needs API key to run) |
| Data connectors (100+ scripts) | `vector_finagent/` top-level .py files | All 360 scripts present (abs_data → zillow_data) | ✅ (mirror present) |
| Qt6 terminal binary | `vector_finagent/qt/build/win-mingw/` | Build files present but **no FinceptTerminal.exe** — build did not complete | ⚠️ |
| QuantLib wrappers (18 quant modules) | `vector_finagent/Analytics/quant/quant_modules_3042.py` | File present in mirror | ✅ (mirror present) |
| LBO / merger / M&A models | `vector_finagent/Analytics/corporateFinance/` | lbo/, merger_models/, fairness_opinion/ all present | ✅ (mirror present) |
| Broker integrations (16 equity + 2 crypto) | C++ only in `vector_finagent/qt/src/trading/` | BrokerRegistry.cpp, 16 broker dirs present in source; no Python broker layer | ⚠️ (C++ source only, no Python API) |
| Exchange/CCXT scripts | `vector_finagent/exchange/` | 20 exchange scripts present | ✅ (mirror present) |
| Data analytics district | `districts/data_analytics/` (4 agents) | AnalyticsReporter, DataEngineer, PerformanceBenchmarker, PerformanceOptimizer — all VECTOR-native, not FinceptTerminal analytics | ✅ (independent VECTOR agents) |

### Key finding: absorption method
The absorption strategy was a **directory mirror** — `fincept-qt/scripts/` was copied verbatim into `districts/investment/vector_finagent/`. This means:
- All 1,423 Python analytics scripts are physically present in VECTOR
- Each script retains its original imports and dependencies (akshare, yfinance, qlib, vectorbt, etc.)
- They are not yet wired into the Governor routing or callable via VECTOR agent invocations
- The FinAgentAgent wrapper calls into them via `importlib` and module path, but most routes depend on runtime API keys (OpenAI for investor analysis, LLM providers for geopolitics)
- `finagent_agent.py` line 27 constructs `_FINCEPT_BASE = Path(...) / "core" / "vector_finagent"` — **wrong path** (should be `districts/investment/vector_finagent`)

---

## 3. Frontend / Panel spec — Qt6 terminal as HUD inspiration

FinceptTerminal's 54-screen layout is the richest financial terminal HUD reference available. Key panels for VECTOR dashboard inspiration:

### Dashboard (launchpad)
- Ticker bar (scrolling real-time prices across top)
- Market Pulse Panel (indices + sector heatmap)
- Quick-access function keys (F1–F12 mapped to screens)
- Command palette (Bloomberg-style function key + command input)

### Equity Research HUD (8 tabs per stock)
```
[Overview] [Financials] [Analysis] [Technicals] [Peers] [Sentiment] [News] [AI]
```
- Overview: price chart + key metrics sidebar
- Financials: income/balance/cashflow tables with period selector
- Analysis: DCF/multiples/residual income outputs
- Technicals: talipp indicator chart with MA/RSI/MACD overlays
- Sentiment: social + news sentiment scoring

### Portfolio View
- Holdings blotter (position table with P&L columns)
- Performance chart (equity curve)
- Heatmap (sector/allocation visual)
- Insights panel (AI-generated brief)
- Order panel (buy/sell entry form)

### Crypto Trading View
- Real-time OHLCV chart (candlestick)
- Order book (bid/ask depth table)
- Depth chart (bid/ask volume visualization)
- Open positions / P&L summary

### IV Surface (surface_analytics/)
- 3D implied volatility surface (strike × expiry × IV)
- Smile chart (IV by strike at fixed expiry)

### Node Editor (visual workflow)
- Canvas with draggable nodes
- Palette sidebar (data sources, indicators, strategies)
- Properties panel
- Toolbar (run/pause/stop/save)
- DAG execution engine

### Relationship Map
- Force-directed graph (entities + relationship edges)
- Geopolitical, corporate, or user-defined entity networks

### Key UI pattern: ADS (Advanced Docking System)
All panels are dock widgets — floatable, tabbable, splittable. This is the Bloomberg multi-window paradigm: any screen can be torn off into a separate monitor. VECTOR dashboard should adopt this for the monitoring/HUD.

---

## 4. Verdict

**Absorption status: PARTIAL — scripts present, not fully wired.**

The session memory log (2026-05-18) claimed the absorption produced `core/fincept/` with 7 working routes executing end-to-end. The actual state:
1. The scripts were copied into `districts/investment/vector_finagent/` (correct spirit, wrong path from memory)
2. The agent wrappers (`finagent_agent.py`, `backtest_agent.py`, `hedgebot_agent.py`) all import and instantiate correctly
3. `_FINCEPT_BASE` in `finagent_agent.py` points to `core/vector_finagent` (non-existent) instead of `districts/investment/vector_finagent` — persona configs will fail to load at runtime
4. The Qt6 terminal binary was not built (build dir present but no `.exe`)
5. Most analytics functions require extra pip installs (qlib, vectorbt, zipline, etc.) and API keys (OpenAI for investor persona agents)
6. The `data_analytics` district is independent VECTOR-native code — does not use FinceptTerminal analytics

**License risk:** FinceptTerminal is AGPL-3.0 with a custom commercial clause that treats "any business use" as requiring a paid license. VECTOR is a personal tool, so AGPL-3.0 personal use is permissible. However, the mirror copy approach (copying code verbatim) means VECTOR technically contains AGPL-licensed code — if VECTOR is ever shared or commercialized, this requires attention.

---

## 5. Gaps

| # | Issue | Location | Type | Status |
|---|-------|----------|------|--------|
| 1 | `_FINCEPT_BASE` wrong path in `finagent_agent.py` — points to `core/vector_finagent` which doesn't exist; persona configs silently fail to load | `districts/investment/finagent_agent.py:27` | Bug | ❌ Open |
| 2 | Qt6 terminal binary not built — `build/win-mingw/` present but no `.exe`; `launch_terminal` route will fail | `districts/investment/vector_finagent/qt/build/win-mingw/` | Deployment | ⚠️ Deferred |
| 3 | Investor persona agents (Buffett, Graham, Lynch, etc.) require `OPENAI_API_KEY` or `FINANCIAL_DATASETS_API_KEY` — not wired to VECTOR's local Ollama provider_client | `vector_finagent/agents/TraderInvestorsAgent/configs/agent_definitions.json` | Integration | ❌ Open |
| 4 | 1,423 Python analytics scripts are mirror-copied but not Governor-routable — no district agent exposes them as callable actions beyond the 7 FinAgentAgent routes | `districts/investment/vector_finagent/Analytics/` | Architecture | ❌ Open |
| 5 | Qlib ML pipeline (14 scripts) requires `qlib` pip install and Microsoft Azure storage for data — not in VECTOR requirements.txt | `vector_finagent/ai_quant_lab/qlib_*.py` | Dependency | ⚠️ Deferred |
| 6 | vectorbt, zipline, fasttrade, bt backtest engines require separate pip installs not in requirements.txt | `vector_finagent/Analytics/backtesting/` | Dependency | ⚠️ Deferred |
| 7 | 100+ data connector scripts at top-level of `vector_finagent/` have heterogeneous dependencies (akshare, financepy, finrl, gluonts, etc.) — no validation script checks which are actually importable | `districts/investment/vector_finagent/*.py` | Dependency | ❌ Open |
| 8 | `hedgebot_agent.py` routes for Solana DEX (`solana_order`, `solana_execute`) require `SOLANA_PRIVATE_KEY` + `JUPITER_API_KEY` and `live_trading=True` — none documented in CONFIG | `districts/investment/hedgebot_agent.py` | Config | ⚠️ Documented |
| 9 | No VECTOR test coverage for FinceptTerminal absorption — no `tests/test_fincept_absorption.py` exists | `tests/` | Testing | ❌ Open |
| 10 | Qt6 HUD panels (ticker bar, candlestick chart, IV surface, node editor) have no Python/web equivalent in VECTOR dashboard — `dashboard/src/` is not yet built | `dashboard/src/` (missing) | Feature gap | ❌ Open |
| 11 | Geopolitics agents (Grand Chessboard, Prisoners of Geography) require LLM API calls but VECTOR's `districts/research/` has no geopolitics route | `vector_finagent/agents/GeopoliticsAgents/` | Integration | ❌ Open |
| 12 | FinceptTerminal's voice scripts (Deepgram STT/TTS, clap detector) are present in `vector_finagent/voice/` but duplicate VECTOR's own `core/voice/` — no consolidation | `vector_finagent/voice/` | Duplication | ⚠️ Low priority |
| 13 | License risk: AGPL-3.0 code (verbatim mirror) inside VECTOR codebase — if VECTOR is ever shared commercially, FinceptTerminal's custom commercial clause applies | `districts/investment/vector_finagent/` | Legal | ⚠️ Note |

### Priority fixes
1. **Fix `_FINCEPT_BASE` path** (Gap 1) — one-line change, unlocks investor persona loading
2. **Wire persona agents to local Ollama** (Gap 3) — replace `"provider": "openai"` with VECTOR's `provider_client.py`; enables Buffett/Graham/Lynch analysis via local LLMs
3. **Write absorption test suite** (Gap 9) — verify importability of key analytics modules

### Nice-to-have
- Scaffold a Governor wrapper that exposes top Analytics categories (DCF, LBO, bond pricing, portfolio optimization) as routable actions (Gap 4)
- Add `pip install vectorbt backtesting bt zipline` to requirements or a separate `requirements-fincept.txt` (Gap 6)
- Build VECTOR dashboard panels inspired by the Equity Research 8-tab HUD and Portfolio heatmap (Gap 10)
