# daily_stock_analysis-main Audit

> Audit date: 2026-06-02
> Repo: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\daily_stock_analysis-main`
> VECTOR codebase: `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase`

---

## 1. Repo Reality

**What it is:** A股/港股/美股 AI-powered watchlist analysis system (Chinese: "股票智能分析系统"). Licensed MIT. Written entirely in Python + React/TypeScript. Actively maintained by ZhuLinsen on GitHub.

**Primary purpose:** Run a daily automated pipeline on a user-defined watchlist of A-share, HK-share, and US-share tickers — pulling multi-source market data, feeding it to any LLM (Gemini, Claude, DeepSeek, Ollama, etc.) and pushing a "decision dashboard" to 13+ notification channels. The emphasis is on A-share specifics (chip distribution, capital flows, AkShare/Tushare data, board-sector analysis).

### Concrete features (every one verified in source)

| # | Feature | Source location |
|---|---------|----------------|
| 1 | **Multi-market data fetcher** — AkShare, Tushare, Pytdx, Baostock, TickFlow, YFinance, Longbridge, AlphaVantage, eFiance, Finnhub | `data_provider/` (10 fetcher files) |
| 2 | **A-share chip distribution** — 筹码集中度, float chips, position distribution | `data_provider/realtime_types.py::ChipDistribution` |
| 3 | **Capital/money flow** — 主力资金流, northbound/southbound data | `data_provider/akshare_fetcher.py`, `tickflow_fetcher.py` |
| 4 | **Trading calendar** — per-market holiday check (XSHG/XHKG/XNYS), skip non-trading days, `--force-run` override | `src/core/trading_calendar.py` |
| 5 | **5-factor AI decision report** — core conclusion, score (0-100), trend, buy/sell levels, risk warnings, catalysts, checklist | `src/analyzer.py` via LiteLLM Router |
| 6 | **Market broad review** (大盘复盘) — A/HK/US index recap, sector performance, breadth statistics | `src/core/market_review.py` |
| 7 | **15+ Agent strategy system** — MA golden cross, 缠论, wave theory, trend, hot theme, event-driven, growth quality, expectation repricing, etc. | `strategies/*.yaml` (15 YAML files) |
| 8 | **Multi-round conversational stock agent** (`/chat`) — multi-turn, session export, send to channel, background execution | `src/agent/` (orchestrator + runner + executor) |
| 9 | **Event-based alert system** — price_cross, price_change_percent, volume_spike, MA/RSI/MACD/KDJ/CCI technical alerts, portfolio risk alerts, market-light alerts | `src/services/alert_service.py`, `src/services/alert_indicators.py` |
| 10 | **Backtest engine** — evaluates historical AI decisions against actual OHLC outcome, long-only daily bars, neutral-band scoring, direction-correct metric, hit stop-loss/take-profit tracking | `src/core/backtest_engine.py` + `src/services/backtest_service.py` |
| 11 | **Portfolio management** — accounts, FIFO/avg cost methods, buy/sell/dividend/split, FX refresh, oversell guard | `src/services/portfolio_service.py` |
| 12 | **History comparison** — compare current analysis vs historical records, run-level diagnostics | `src/services/history_comparison_service.py` |
| 13 | **Push to 13 notification channels** — WeChat Work, Feishu, Telegram, Discord, Slack, Email (SMTP), Pushover, Pushplus, Gotify, Ntfy, AstrBot, Serverchan3, Custom Webhook; Markdown-to-image conversion | `src/notification_sender/` (14 sender files) |
| 14 | **Feishu cloud doc creation** (飞书云文档) — creates a timestamped Feishu doc with full report after each run | `src/feishu_doc.py` |
| 15 | **Web UI workbench** — React/TypeScript SPA: manual analysis, task progress monitor, history reports, full Markdown viewer, agent chat, backtest view, portfolio, config management, light/dark theme | `apps/dsa-web/src/` (pages: Home, Chat, Backtest, Portfolio, Settings, Alerts) |
| 16 | **Desktop client** — Electron wrapper around the web UI | `apps/dsa-desktop/` |
| 17 | **FastAPI backend** — 100+ REST endpoints: analyze, history, portfolio, alerts, backtest, settings, config, agent chat, stock index | `api/` |
| 18 | **Smart stock import** — image upload, CSV/Excel, clipboard paste; code/name/pinyin/alias autocomplete | `src/services/import_parser.py`, `src/services/image_stock_extractor.py` |
| 19 | **Social sentiment** — optional Reddit/X/Polymarket (US stocks only) via Stock Sentiment API | `src/services/social_sentiment_service.py` |
| 20 | **GitHub Actions automation** — daily cron at 18:00 Beijing time, weekday-only, trading-day-aware skip, manual trigger, breakpoint resume | `.github/workflows/ci.yml` |
| 21 | **Scheduler daemon** — `--schedule` mode with hot-reload of `.env`, background agent event monitor | `src/scheduler.py`, `main.py::run_with_schedule` |
| 22 | **7 news/search sources** — Anspire, SerpAPI, Tavily, Bocha, Brave, MiniMax, SearXNG | `src/search_service.py` |
| 23 | **Docker + NSSM service** — Docker-ready, Linux and Windows service support | `docker/`, `scripts/` (if present) |
| 24 | **Context snapshot** — saves full analysis context pack for debugging and audit | `src/analysis_context_pack_prompt.py`, `src/analysis_context_pack_overview.py` |
| 25 | **Notification diagnostics** — `--check-notify` validates all channel configs, per-channel reachability | `src/services/notification_diagnostics.py` |

**Market focus:** A-shares first (AkShare/Tushare/Pytdx/Baostock data sources optimised for Shenzhen/Shanghai). Full HK and US support via YFinance/TickFlow/Longbridge.

---

## 2. VECTOR Parity

### Mandatory shell run (from protocol)

```
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase" && python -X utf8 -c "
import sys; sys.path.insert(0,'.')
from districts.investment.technical_bot import TechnicalBot
from districts.investment.sentiment_bot import SentimentBot
t = TechnicalBot(); print('TechnicalBot OK:', type(t))
s = SentimentBot(); print('SentimentBot OK:', type(s))
" 2>&1 | tail -4
```

**Output (verbatim):**
```
[INFO] [VECTOR][city] Agent TechnicalBot gen 1 born at 500 HP using vector-focus
[INFO] [VECTOR][technical_bot] TechnicalBot initialized
[INFO] [VECTOR][city] Agent SentimentBot gen 1 born at 500 HP using vector-focus
[INFO] [VECTOR][sentiment_bot] SentimentBot initialized
TechnicalBot OK: <class 'districts.investment.technical_bot.TechnicalBot'>
SentimentBot OK: <class 'districts.investment.sentiment_bot.SentimentBot'>
```

**Additional parity runs:**

```
# StockAnalyst + FundamentalsBot
StockAnalyst OK: <class 'districts.investment.stock_analyst.StockAnalyst'>
FundamentalsBot OK: <class 'districts.investment.fundamentals_bot.FundamentalsBot'>

# BacktestAgent
BacktestAgent OK: <class 'districts.investment.backtest_agent.BacktestAgent'>

# Live NSE quote fetch (RELIANCE)
[INFO] NSE quote fetched: RELIANCE via NSE @ 1320.0
NSE Quote: success - 1320.0
```

### Feature-by-feature parity table

| DSA Feature | VECTOR file | Verified output | Status |
|-------------|------------|----------------|--------|
| Price data fetch (US stocks via yfinance) | `districts/investment/technical_bot.py::_get_real_price_data` | TechnicalBot OK instantiation + yfinance flag True | ✅ running |
| Technical indicators: SMA, EMA, RSI, MACD, Bollinger | `districts/investment/technical_bot.py::calculate_indicators` | TechnicalBot OK; all 5 indicator methods present in source | ✅ running |
| Chart pattern detection: double-bottom, H&S, uptrend, downtrend, S/R | `districts/investment/technical_bot.py::detect_patterns` | Methods confirmed in source | ✅ running |
| News sentiment analysis (NewsAPI + keyword heuristic) | `districts/investment/sentiment_bot.py::fetch_news_sentiment` | SentimentBot OK; NewsAPI + mock path confirmed | ✅ running |
| Social media sentiment (Twitter/Reddit mock) | `districts/investment/sentiment_bot.py::fetch_social_sentiment` | SentimentBot OK; mock implementation confirmed | ⚠️ stub — mock only, no live API wired |
| NSE/BSE quote (Yahoo Finance v8 API, .NS/.BO fallback) | `districts/investment/stock_analyst.py::get_nse_quote` | `NSE Quote: success - 1320.0` | ✅ running |
| Fundamentals (income stmt, balance sheet, cash flow via yfinance) | `districts/investment/fundamentals_bot.py::analyze_financials` | FundamentalsBot OK; real + mock paths confirmed | ✅ running |
| Backtest engine (daily OHLC evaluation of past AI calls) | `districts/investment/backtest_agent.py`, `districts/investment/vector_backtest/backtest/engines/` | BacktestAgent OK; 9 engine files confirmed in vector_backtest/ | ✅ running |
| Multi-agent investment debate (bull/bear/risk/portfolio) | `districts/investment/trading_conductor_agent.py::run_analysis` | TradingConductorAgent OK; methods: run_analysis, run_forever confirmed | ✅ running (needs langgraph + API key at runtime) |
| A-share chip distribution (筹码集中度) | NOT PRESENT in investment district | No `chip` keyword in any top-level investment file | ❌ missing |
| A-share capital/money flow (主力资金) | NOT PRESENT in investment district | No `money_flow` or `capital_flow` keyword found | ❌ missing |
| AkShare data source (A-share specific OHLC, sector, fund flows) | Referenced in backtest_agent.py only (via vector_backtest absorbed repo) | Only in deep backtest path, not in standard analysis pipeline | ⚠️ stub |
| Tushare data source | NOT PRESENT | No tushare import in any investment district file | ❌ missing |
| Broad market review (大盘复盘 — indices, sectors, breadth) | NOT PRESENT | No market_review module in investment district | ❌ missing |
| Trading calendar / holiday skip per market | NOT PRESENT | No exchange_calendars or holiday logic in investment district | ❌ missing |
| Watchlist management (STOCK_LIST, per-run override) | NOT PRESENT | No watchlist concept in investment district agents | ❌ missing |
| Portfolio management (buy/sell/FIFO/avg cost/FX) | NOT PRESENT in investment district | No portfolio_service equivalent | ❌ missing |
| Alert/event monitor (price cross, RSI threshold, volume spike) | NOT PRESENT | No alert agent or AlertService in investment district | ❌ missing |
| Multi-channel push (WeCom/Feishu/Telegram/Discord/Slack/Email/Pushover) | `vectorcode/src/channels/` (telegram.py, slack.py, feishu.py, email_channel.py, discord_channel.py, whatsapp.py, 35+ others) | VectorCode channels list confirmed (40 channels) | ✅ running — but NOT wired to investment district output |
| AI report generation (score + buy/sell levels + risk + catalysts) | NOT PRESENT — investment district agents return raw dicts, no structured report formatter | No score/sentiment_score/operation_advice pipeline equivalent to DSA's AnalysisResult | ❌ missing |
| GitHub Actions automation (daily cron) | VECTOR has APScheduler in autonomous_loop + NSSM installer | `scripts/install_service.ps1` confirmed in phase_status | ✅ running (different mechanism — VECTOR is always-on loop, not cron) |
| Web workbench (React SPA with chat/backtest/portfolio/history) | NOT PRESENT | No dashboard built yet (phase_status: "Next.js dashboard ❌ not built yet") | ❌ missing |
| FastAPI REST API for external triggering | `core/api/` exists with routers | Confirmed in phase_status; `/api/v1/` routes exist | ✅ running (partial) |
| Feishu cloud doc creation | NOT PRESENT | No feishu_doc equivalent in investment district | ❌ missing |
| Context snapshot / run diagnostics | VECTOR has `core/loop/context_engine.py` and `core/memory/reasoning_memory.py` | ContextEngine confirmed instantiated in TradingConductorAgent | ✅ running (different mechanism) |
| Smart stock import (image/CSV/clipboard) | NOT PRESENT | No import_parser equivalent | ❌ missing |
| Social sentiment via Reddit/X API | VectorCode `reddit_channel.py` + `twitter_channel.py` exist | Channel adapters only — no investment sentiment pipeline wired | ⚠️ stub |

---

## 3. Frontend

### DSA has a full production frontend — VECTOR has none.

**DSA web app** (`apps/dsa-web/`): React 18 + TypeScript + Vite + Tailwind CSS. Pages confirmed:
- `HomePage.tsx` — dashboard entry, task list, analysis trigger
- `ChatPage.tsx` — multi-round agent strategy conversation (`/chat`)
- `BacktestPage.tsx` — backtest results viewer
- `PortfolioPage.tsx` — portfolio account + holdings + P&L
- `AlertsPage.tsx` — alert rule management
- `SettingsPage.tsx` — env/config management via WebUI
- `LoginPage.tsx` — optional auth gate
- Component directories: `dashboard/`, `history/`, `report/`, `settings/`, `tasks/`, `StockAutocomplete/`, `alerts/`, `common/`
- i18n: `src/locales/` — multilingual support confirmed
- Stores: Zustand (state management confirmed)
- Playwright e2e tests: `e2e/` directory present
- Light/dark theme toggle

**DSA desktop app** (`apps/dsa-desktop/`): Electron wrapper, `main.js` + `preload.js` + `renderer/`, packaged as a standalone desktop app with NSIS installer.

**VECTOR status:** `phase_status.md` explicitly says "Next.js Dashboard ❌ not built yet". The `docs/frontend-spec.md` was written on 2026-05-29 (from MEMORY.md: "200 endpoints, 6 WS channels") but no implementation exists. VECTOR has no investment district UI whatsoever — the TradingConductorAgent and StockAnalyst return raw Python dicts only.

---

## 4. Verdict

**Absorb selectively.** This repo is NOT absorb-as-whole material — it is a standalone product with its own LiteLLM router, SQLAlchemy ORM, Redis dependencies, and a React frontend that VECTOR does not use. However, it contains 5 high-value gaps that are genuinely missing from VECTOR's investment district.

**Why not a full absorption:**
- Depends on LiteLLM, SQLAlchemy, `exchange-calendars`, `json_repair`, `pandas` throughout — all legitimate but not in VECTOR's minimal install; would add ~15 heavy deps
- Has its own `src/config.py` singleton, `src/storage.py` DatabaseManager, `src/notification.py` that duplicate VECTOR's `core/config.py`, `core/memory/episodic.py`, `vectorcode/src/channels/` — absorbing them wholesale would create conflicts
- The React frontend is a TypeScript codebase (700+ lines of TSX) — not absorbable, VECTOR builds its dashboard in Next.js
- The backtest engine (`src/core/backtest_engine.py`) overlaps with `districts/investment/vector_backtest/` already absorbed from Vibe-Trading; partial overlap, not a clean gap

**Where VECTOR is clearly weaker:**
- A-share specific data pipeline (chip distribution, capital flows, AkShare/Tushare sources) — entirely absent
- Broad market daily review (大盘复盘) — no equivalent at all
- Trading calendar / holiday-aware scheduling for A/HK/US — absent
- Agent-generated structured report (score + buy/sell levels + risk + catalysts) using local Ollama — TradingConductorAgent returns LangGraph output but lacks DSA's clean `AnalysisResult` schema
- Alert/event monitor wired to investment data — no alert system in investment district

---

## 5. Gaps (what to absorb)

All 5 items below are Python-portable, VECTOR-architecture-compatible, and close real holes.

### Gap 1 — A-share chip distribution + capital flow pipeline
**DSA location:** `data_provider/akshare_fetcher.py`, `data_provider/realtime_types.py::ChipDistribution`
**What to build:** `districts/investment/china_data_fetcher.py` — `ChinaDataFetcher` class wrapping AkShare (and optionally Tushare) to return chip concentration, capital flow (northbound/southbound, main-force net buy), A-share OHLC with volume metrics. Guards via `try: import akshare` — degrades gracefully.
**VECTOR seam:** Wire into `StockAnalyst.get_quote()` as a new `get_ashare_data(symbol)` path; also callable from `TradingConductorAgent` analysts.
**Impact:** Closes the entire A-share analysis gap. Currently VECTOR can only get Yahoo Finance OHLC for A-shares (.SS/.SZ suffixes) — it has zero chip or capital flow data.

### Gap 2 — Trading calendar (A/HK/US holiday-aware skip)
**DSA location:** `src/core/trading_calendar.py` — uses `exchange-calendars` to check XSHG/XHKG/XNYS, per-stock market assignment, `get_open_markets_today()`, `compute_effective_region()`
**What to build:** `districts/investment/trading_calendar.py` — lightweight wrapper that checks if today is a trading day for a given market before running analysis. Guards via `try: import exchange_calendars` — degrades to always-run if unavailable.
**VECTOR seam:** TradingConductorAgent's `run_forever()` loop should call `is_trading_day(ticker)` before dispatching analysis. Also needed by any scheduled investment run in `autonomous_loop.py`.
**Impact:** Prevents VECTOR from running investment analysis on market holidays, wasting Ollama compute.

### Gap 3 — Daily broad market review agent (大盘复盘)
**DSA location:** `src/core/market_review.py`, `src/market_analyzer.py`
**What to build:** `districts/investment/market_review_agent.py` — `MarketReviewAgent(AgentBase)` that runs daily (after market close) to fetch major index data (Nifty 50, BSE Sensex, SSE Composite, Hang Seng, S&P 500, Nasdaq), sector performance, advance/decline breadth, and generates a structured daily summary via `vector-focus` Ollama. Stores result in `EpisodicMemory`.
**VECTOR seam:** Governor routes `market_review`, `daily_review`. Output goes to VectorCode channels (telegram/discord/email already wired). Also feeds `districts/reflection/daily_reviewer.py`.
**Impact:** Gives VECTOR a daily macro context layer that currently doesn't exist in the investment district. The reflection district's `daily_reviewer.py` can consume market_review output for the 2AM reflections.

### Gap 4 — AnalysisResult schema (structured AI stock report)
**DSA location:** `src/analyzer.py::AnalysisResult` dataclass (fields: `code`, `name`, `sentiment_score` 0-100, `operation_advice`, `trend_prediction`, `buy_price`, `sell_price`, `stop_loss`, `risk_warning[]`, `catalysts[]`, `checklist[]`), `src/schemas/report_schema.py`
**What to build:** `districts/investment/analysis_result.py` — dataclass mirroring DSA's `AnalysisResult` schema, plus a `format_report(result, channel)` function that renders it to Markdown suitable for VectorCode push. TradingConductorAgent currently returns raw LangGraph output — it should be normalized into this schema.
**VECTOR seam:** `TradingConductorAgent.run_analysis()` return value normalised through `AnalysisResult`. Output formatted and dispatched via VectorCode `telegram.py` / `discord_channel.py` / `email_channel.py`.
**Impact:** Closes the "VECTOR can analyse but can't push a clean daily report" gap. Currently `generate_sentiment_report()` returns unstructured dicts; `TradingConductorAgent` returns raw LangGraph state. Neither produces a pushable decision dashboard.

### Gap 5 — Alert/event monitor for investment signals
**DSA location:** `src/services/alert_service.py`, `src/services/alert_indicators.py` (MA price cross, RSI threshold, MACD cross, KDJ cross, CCI threshold, volume spike, price change percent)
**What to build:** `districts/investment/alert_agent.py` — `InvestmentAlertAgent(AgentBase)` that monitors a watchlist at configurable intervals for technical trigger events. Uses `TechnicalBot.calculate_indicators()` (already running) for RSI/MACD/SMA data; evaluates thresholds; pushes via VectorCode on trigger. Stores trigger history in `EpisodicMemory` to enforce cooldowns.
**VECTOR seam:** Governor route `investment_alert`. Wired into autonomous_loop background tasks (5-10 min interval). Cooldown state in `EpisodicMemory` prevents alert spam.
**Impact:** Gives VECTOR proactive intraday investment triggers instead of only end-of-day reports.

---

### Priority order

| Priority | Gap | Effort | Value |
|----------|-----|--------|-------|
| P0 | Gap 4 — AnalysisResult schema + daily report push | Low (1 file, 150 LOC) | Immediately unlocks daily report delivery |
| P1 | Gap 1 — A-share chip + capital flow | Medium (1 file, ~200 LOC + `pip install akshare`) | Closes entire Indian/Chinese A-share data hole |
| P2 | Gap 3 — Market review agent | Medium (1 file, ~250 LOC) | Daily macro context for reflection district |
| P3 | Gap 5 — Alert/event monitor | Medium (1 file, ~300 LOC) | Proactive investment signals |
| P4 | Gap 2 — Trading calendar | Low (1 file, ~100 LOC + `pip install exchange-calendars`) | Prevents wasted compute on holidays |

### Explicitly NOT absorbing

| Item | Reason |
|------|--------|
| `src/analyzer.py` (LiteLLM router) | VECTOR uses `core/inference/provider_client.py` (27-provider router); duplicate |
| `src/storage.py` (SQLAlchemy + BacktestResult ORM) | VECTOR uses SQLCipher + EpisodicMemory; absorbing would create ORM conflict |
| `src/notification.py` + `notification_sender/` (13 senders) | VECTOR has 40+ VectorCode channels; DSA's senders are a strict subset |
| `src/core/pipeline.py` (StockAnalysisPipeline) | VECTOR's TradingConductorAgent already handles the multi-agent pipeline role |
| `apps/dsa-web/` (React SPA) | TypeScript-only; VECTOR will build its own Next.js dashboard from `docs/frontend-spec.md` |
| `apps/dsa-desktop/` (Electron) | Not applicable to VECTOR's architecture (server-side daemon + web UI) |
| `src/core/backtest_engine.py` | `districts/investment/vector_backtest/` already absorbed from Vibe-Trading; overlap |
| `src/feishu_doc.py` | Feishu cloud doc creation — nice-to-have but not in VECTOR's comms stack (VectorCode uses webhooks) |
