# AI-Trader-main Audit

**Repo:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\AI-Trader-main`
**Audited:** 2026-06-01
**License:** MIT

---

## 1. Repo Reality

AI-Trader is an **Agent-Native Social Trading Platform** — not a local backtester or algo engine. It is a hosted multi-agent marketplace at `https://ai4trade.ai` where AI agents (Claude Code, OpenClaw, Cursor, Codex, custom) register, publish trading signals, follow each other, and copy-trade in paper accounts.

**Concrete features:**

- **Paper Trading Engine** — each registered agent starts with $100,000 simulated capital. Supports US stocks (Alpha Vantage + market-hours gate), crypto (Hyperliquid), and Polymarket prediction markets. Trade types: buy, sell, short, cover.
- **Signal Publishing** — three signal types: `operation` (realtime trade), `strategy` (text analysis), `discussion` (open debate). All stored in SQLite (PostgreSQL optional via `DATABASE_URL`).
- **Copy Trading** — followers automatically mirror leader's trades at same price+quantity. SAVEPOINT-based per-follower atomic execution. Insufficient-cash followers are silently skipped.
- **Leaderboard** — multi-metric ranking: return %, risk-adjusted score (return minus max drawdown), collaboration score (reply+citation+adoption count), quality score average. Time windows configurable.
- **Signal Quality Scoring** — heuristic-v1 scorer in `signal_quality.py`: detects duplicate content, extracts price targets from text, scores on keywords, specificity, and originality.
- **Heartbeat / WebSocket Notifications** — agents poll `/api/claw/agents/heartbeat` (or subscribe to `wss://ai4trade.ai/ws/notify/{id}`) for replies, follows, mentions, accepted answers, new follower strategies.
- **Challenges System** — time-boxed trading competitions with configurable scoring (return-only or risk-adjusted) and configurable reward tiers.
- **Team Missions** — multi-agent collaborative challenges with role assignment (lead/analyst/risk/scribe), contribution scoring, and team-level rewards.
- **Experiment / A/B Framework** — `experiments.py` supports agent-bucketed A/B tests (e.g. `quality_weighted` reward mode) with stable hashing assignment and behavior event tracking.
- **Market Intelligence** — `market_intel.py` aggregates financial news from Alpha Vantage NEWS_SENTIMENT endpoint, Adanos API, and OpenRouter LLM summaries into snapshot tables. Includes macro signal detection, ETF flow analysis, BTC macro correlation, and per-symbol stock analysis.
- **Points / Rewards Ledger** — idempotent ledger in `agent_reward_ledger` table. Points exchange: 1 point = $1,000 simulated cash.
- **Research Exports** — `research_exports.py` allows agents to publish structured research artifacts.
- **React Frontend** — full-featured React/Vite/recharts dashboard with pages: Landing, TradePage, PositionsPage, SignalsFeed, StrategiesPage, DiscussionsPage, LeaderboardPage (with profit-history line charts per agent), CopyTradingPage, FinancialEventsPage (market intel), ChallengePage, TeamMissionsPage, ExperimentAdminPage. Chinese/English i18n.
- **SKILL.md Integration Protocol** — agent auto-integration via `skills/ai4trade/SKILL.md` bootstrap. Child skills: `copytrade`, `tradesync`, `heartbeat`, `polymarket`, `market-intel`.

**Execution model:** ALL trading is paper-only simulation within the platform's own ledger. There are NO real broker API calls, no live order routing, no Binance/IBKR/Coinbase execution. The "trade sync" feature records trades you already made on external brokers — it does not place orders on your behalf.

---

## 2. VECTOR Parity

### Verification run
```
StockAnalyst OK: <class 'districts.investment.stock_analyst.StockAnalyst'>   (yfinance: True)
FundamentalsBot OK: <class 'districts.investment.fundamentals_bot.FundamentalsBot'>
TechnicalBot OK: <class 'districts.investment.technical_bot.TechnicalBot'>
SentimentBot OK: <class 'districts.investment.sentiment_bot.SentimentBot'>
```

All four investment district agents import and initialize correctly.

| Feature | VECTOR Equivalent | Verified Output | Status |
|---------|------------------|-----------------|--------|
| Stock price quotes (yfinance, NSE/BSE fallback) | `districts/investment/stock_analyst.py` — `get_quote()`, `get_nse_quote()`, `get_crypto_quote()` | `StockAnalyst OK` — yfinance live | ✅ |
| Technical indicators (SMA, EMA, RSI, MACD, Bollinger, ATR, ADX, Stochastic, CCI, Williams %R) | `districts/investment/technical_bot.py` — `get_price_data()`, yfinance + pandas-ta | `TechnicalBot OK` | ✅ |
| Fundamental analysis (income stmt, balance sheet, cash flow) | `districts/investment/fundamentals_bot.py` — `analyze_financials()`, yfinance | `FundamentalsBot OK` | ✅ |
| News/social sentiment analysis | `districts/investment/sentiment_bot.py` — NewsAPI + Ollama LLM scoring | `SentimentBot OK` | ✅ |
| Backtesting (9-engine) | `districts/investment/backtest_agent.py` — `BacktestAgent`, wraps Vibe-Trading engine | Import confirmed in district `__init__` | ✅ |
| Bull/Bear debate swarm for stocks | `core/trading/agents/researchers/bull_researcher.py` + `bear_researcher.py` + `core/trading/agents/risk_mgmt/` | Files exist, LangChain LLM debate loop | ✅ |
| Investment plan → trader proposal pipeline | `core/trading/agents/trader/trader.py` — `create_trader()`, LangChain structured output | File verified | ✅ |
| Crypto quotes via CoinGecko | `districts/investment/stock_analyst.py` — `get_crypto_quote()`, `get_top_cryptos()` | Code verified | ✅ |
| Multi-agent LLM council for high-stakes decisions | `districts/governance/llm_council.py` — HP>700 gate, 3-stage deliberative | Architecture confirmed | ✅ |
| **Paper trading platform (agent social network)** | **None** | N/A | ❌ |
| **Signal feed / community discussion board** | **None** | N/A | ❌ |
| **Copy-trading (follow/unfollow, auto-mirror positions)** | **None** | N/A | ❌ |
| **Leaderboard with PnL history charts** | **None** — `districts/investment/` has no leaderboard | N/A | ❌ |
| **Heartbeat notification loop (WebSocket + polling)** | **Partial** — `core/mcp_server.py` + vectorcode channels handle notifications, but no agent-to-agent trading notification system | No trading heartbeat | ⚠️ |
| **Signal quality scoring (heuristic, duplicate detection, prediction extraction)** | **None** | N/A | ❌ |
| **Challenges / trading competitions** | **None** | N/A | ❌ |
| **Team missions (multi-agent collaborative trading)** | **None** | N/A | ❌ |
| **A/B experiment framework on agent rewards** | **None** | N/A | ❌ |
| **Market intel snapshots (Alpha Vantage NEWS_SENTIMENT, ETF flows, BTC macro)** | **Partial** — `districts/research/news_aggregator.py` has RSS/Reddit/news, but no ETF flows or structured market intel snapshot table | Research district exists | ⚠️ |
| **Points/rewards ledger (idempotent, experiment-tagged)** | **Partial** — HP system in `core/city/agent_base.py` serves a similar role but is not a public ledger | HP award_points() exists | ⚠️ |
| **React trading dashboard with recharts PnL lines** | **None** — `dashboard/src/` not built yet (phase_status.md: "❌ Not built yet") | N/A | ❌ |
| **Polymarket paper trading** | **None** | N/A | ❌ |
| Market hours gate (US stocks 9:30-16:00 ET) | **None** | N/A | ❌ |
| Trade fee model (TRADE_FEE_RATE applied on buy/sell/short/cover) | **None** | N/A | ❌ |

**Execution flag:** AI-Trader has NO live order execution — it is a pure paper trading + signal sharing network. VECTOR's ANALYSIS-ONLY rule is not violated because AI-Trader never routes to a real broker. However, if VECTOR were to integrate as a participant agent, the `POST /api/signals/realtime` endpoint records simulated position changes in AI-Trader's SQLite. This is safe (no real money), but any VECTOR agent that calls this endpoint should be routed through YELLOW tier at minimum (automated paper-trade publication) so the owner can see what VECTOR is posting publicly on behalf of them.

🔴 **Execution note:** The copy-trading auto-mirror feature (`_update_position_from_signal` running automatically for all followers when a leader posts) means that if VECTOR registers as a signal provider, other agents will automatically copy its trades. Consent is explicit (followers opted in), but VECTOR's decision to post should still be YELLOW-gated (not RED since there is no real money, but the public-posting aspect and potential reputation impact warrants human review).

---

## 3. Frontend / Panel Spec

AI-Trader's React frontend is relevant to VECTOR's planned HUD. Key panels worth extracting:

### Leaderboard Panel
- Source: `AppPages.tsx` — `LeaderboardPage`
- Recharts `LineChart` with `ResponsiveContainer` — PnL history per agent over configurable time windows (7d/30d/90d/365d)
- 4-metric sort tabs: Return %, Risk-Adjusted, Collaboration, Quality
- Data: `GET /api/profit/history?metric={return|risk|collaboration|quality}&days={n}&limit={n}`

### Positions Panel
- Source: `AppPages.tsx` — `PositionsPage`
- Live positions with per-position PnL column
- Distinguishes self-opened vs copied positions (`source: "self"` vs `"copied:{leader_id}"`)

### Signal Feed
- Source: `AppPages.tsx` — `SignalsFeed`
- Filterable by market, message_type, keyword
- Sort modes: new, active, following
- Reply counts, participant counts, team mission badges inline

### Market Intelligence Dashboard
- Source: `AppPages.tsx` — `FinancialEventsPage`
- Unified news snapshot by category (12 categories, 48h lookback)
- Macro signals panel (FOMC, CPI, PMI, earnings)
- ETF flow table
- BTC macro correlation panel
- Alpha Vantage + OpenRouter LLM summary

### Trade Page
- Source: `AppPages.tsx` — `TradePage`
- Buy/sell/short/cover form with market selector (us-stock / crypto / polymarket)
- Market hours badge (ET time, open/closed status)
- MARKETS constant maps market ids to labels

### Recommendations for VECTOR HUD

The Leaderboard + Positions panels are directly relevant to VECTOR's investment district monitoring. The pattern of recharts `LineChart` with `buildLeaderboardChartData()` (normalizes history points to chart-compatible format) is reusable. The market hours badge (`isUSMarketOpen()` with ET timezone check) is a standalone utility worth porting.

---

## 4. Verdict

**Do not absorb.** AI-Trader is fundamentally a **hosted multi-agent social trading network** — not a local intelligence module. Its value is as an external platform VECTOR can participate in as an agent-consumer, not as Python code to reimplement.

Reasons:
1. The core of AI-Trader is its community — leaderboard, followers, copy-trading network. Reimplementing it locally gives VECTOR a single-player version with no community value.
2. VECTOR's investment district already covers the analytical stack (quotes, technicals, fundamentals, sentiment, backtesting, bull/bear swarm) that AI-Trader uses only at the edges.
3. The FastAPI backend is tightly coupled to its SQLite schema, Redis cache, and `ai4trade.ai` hosted service. Porting it to VECTOR's architecture would duplicate `core/collections/`, `core/engine/oauth/`, and `core/event_bus` without adding new capability.
4. VECTOR should instead **register as an agent** on `https://ai4trade.ai` — this gives access to the full community leaderboard, copy-trading network, and market intel with zero implementation cost.

**Three genuine gaps** worth absorbing (small, self-contained):

1. **Market hours gate** — `routes_signals.py`:`is_market_open()` with proper zoneinfo ET handling. VECTOR has no US trading hours check.
2. **Market intel snapshot pattern** — `market_intel.py` Alpha Vantage NEWS_SENTIMENT poller + structured snapshot table + per-category history. VECTOR's research district has news aggregation but not the structured financial event snapshot (ETF flows, macro signals, BTC correlation) that market_intel provides.
3. **Leaderboard recharts pattern** — `buildLeaderboardChartData()` + `LeaderboardTooltip` from `appShared.tsx` is the right pattern for VECTOR's planned investment dashboard panel once `dashboard/src/` is built.

---

## 5. Gaps

| Gap | Priority | Files to reference | VECTOR target |
|-----|----------|--------------------|---------------|
| US market hours gate (`is_market_open()` for us-stock, crypto, polymarket) | Medium | `service/server/routes_shared.py` — `is_market_open()` using `ZoneInfo("America/New_York")` | `districts/investment/stock_analyst.py` or a new `core/utils/market_hours.py` |
| Alpha Vantage NEWS_SENTIMENT financial event snapshot (structured market intel with ETF flows, macro signals, BTC correlation) | Low | `service/server/market_intel.py` — `MarketIntelJob`, snapshot tables, category limits, lookback windows | `districts/research/news_aggregator.py` extension or new `districts/investment/market_intel_agent.py` |
| Leaderboard chart data builder for HUD | Low | `service/frontend/src/appShared.tsx` — `buildLeaderboardChartData()`, `formatIntelNumber()`, `getLeaderboardDays()` | `dashboard/src/` once built |
| AI-Trader agent registration (VECTOR joins as signal provider) | Nice-to-have | `skills/ai4trade/SKILL.md` — `POST /api/claw/agents/selfRegister` | New `districts/investment/ai4trade_adapter.py` — YELLOW-gated `publish_signal()` |

**Explicitly NOT worth absorbing:**
- Paper trading engine (SQLite ledger, position tracking, fee model) — VECTOR does not paper-trade; district 17 is analysis-only by rule
- Copy-trading social network — requires the hosted community to be useful
- Challenges / team missions / A/B experiments — multi-user SaaS features, not relevant to single-owner VECTOR
- React dashboard pages — build VECTOR's own dashboard; do not fork AI-Trader's frontend
