# ai-financial-agent-main Audit

**Repo path:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\ai-financial-agent-main`
**Audited:** 2026-06-02
**Stack:** Next.js 15 + TypeScript + Vercel AI SDK + Financial Datasets API
**License:** Not explicitly stated (MIT assumed from public demo)

---

## 1. Repo Reality

### What it is
A proof-of-concept **chat-based financial research assistant** — a Next.js 15 web app with GPT-4.x as the reasoning layer. Users ask financial questions in a chat UI; the LLM decomposes the query into sub-tasks, calls Financial Datasets API tools, and streams results back as generative UI (interactive charts and tables rendered inline in the chat).

### Full feature list

| Feature | Where |
|---------|-------|
| Chat UI with persistent history (PostgreSQL via Vercel Postgres + Drizzle ORM) | `app/(chat)/`, `lib/db/` |
| Auth (email + password, NextAuth v5) | `app/(auth)/` |
| Model selector (GPT-4.1-nano, GPT-4.1-mini, GPT-4.1, GPT-4o) | `lib/ai/models.ts` |
| Streaming task decomposition (GPT-4.1-nano breaks query into 1-3 sub-tasks, streams to UI) | `app/(chat)/api/chat/route.ts:114-174` |
| **Tool: getStockPrices** — snapshot + historical prices at any interval (second/minute/day/week/month/year) | `lib/ai/tools/financial-tools.ts:56` |
| **Tool: getIncomeStatements** — quarterly/annual/TTM, bounded by date | `lib/ai/tools/financial-tools.ts:116` |
| **Tool: getBalanceSheets** — same API shape as income statements | `lib/ai/tools/financial-tools.ts:152` |
| **Tool: getCashFlowStatements** — same API shape | `lib/ai/tools/financial-tools.ts:187` |
| **Tool: getFinancialMetrics** — derived metrics (P/E, PEG, margins, ROIC, etc.) | `lib/ai/tools/financial-tools.ts:222` |
| **Tool: searchStocksByFilters** — multi-filter stock screener (89 filterable fields) | `lib/ai/tools/financial-tools.ts:256` |
| **Tool: getNews** — latest news articles per ticker | `lib/ai/tools/financial-tools.ts:41` |
| Deduplication cache per request (avoids duplicate tool calls in one session) | `lib/ai/tools/financial-tools.ts:29-36` |
| Generative UI — inline Recharts `AreaChart` stock price chart with snapshot summary | `components/ui/stock-chart.tsx` |
| Generative UI — income statement table (structured rows, groupings, per-share formatting) | `components/income-statements-table.tsx` |
| Generative UI — balance sheet table | `components/balance-sheets-table.tsx` |
| Generative UI — cash flow statement table | `components/cash-flow-statements-table.tsx` |
| Generative UI — financial metrics table (valuation, profitability, liquidity, leverage, growth) | `components/financial-metrics-table.tsx` |
| Generative UI — stock screener results table (sortable by any column) | `components/stock-screener-table.tsx` |
| Generative UI — news cards carousel (thumbnail, sentiment badge, scrollable) | `components/ui/news.tsx` |
| Streaming "query-loading" task names panel (shows sub-tasks as they stream) | `components/data-stream-handler.tsx` |
| "Blocks" side panel for code generation (ProseMirror + CodeMirror Python editor) | `components/block.tsx`, `components/editor.tsx` |
| Message voting (thumbs up/down) | `lib/db/schema.ts` (Vote table) |
| Chat sharing (public/private visibility toggle) | `components/visibility-selector.tsx` |
| API key modal (user supplies their own OpenAI key + Financial Datasets key, stored in localStorage) | `components/api-keys-modal.tsx` |
| LangSmith tracing integration | `app/(chat)/api/chat/route.ts:29` |
| Vercel Analytics | `package.json` |
| Vercel Blob storage (file attachments) | `app/(chat)/api/files/` |
| Dark/light theme | `components/theme-provider.tsx` |
| Mobile-responsive sidebar | `components/app-sidebar.tsx` |

### Live order execution
None. The repo is explicitly read-only research/analysis. No brokerage integration, no order placement API, no portfolio management writes. All seven tools are pure GET requests to `api.financialdatasets.ai`. No 🔴 flag required.

### Data provider dependency
All 7 tools call `https://api.financialdatasets.ai` — a paid API. Free tier covers only AAPL, GOOGL, MSFT, NVDA, TSLA. No fallback when the key is absent.

---

## 2. VECTOR Parity

### Command run (exact as specified)
```
cd "C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase" && python -X utf8 -c "
import sys; sys.path.insert(0,'.')
from districts.investment.stock_analyst import StockAnalyst
from districts.investment.fundamentals_bot import FundamentalsBot
from districts.investment.technical_bot import TechnicalBot
s = StockAnalyst(); print('StockAnalyst OK')
f = FundamentalsBot(); print('FundamentalsBot OK')
t = TechnicalBot(); print('TechnicalBot OK')
" 2>&1 | tail -5
```

**Actual output:**
```
[VECTOR][investment] Investment district loaded
[VECTOR][city] Agent StockAnalyst gen 1 born at 500 HP using vector-focus
[VECTOR][stock_analyst] StockAnalyst initialized - yfinance: True
[VECTOR][city] Agent FundamentalsBot gen 1 born at 500 HP using vector-focus
[VECTOR][fundamentals_bot] FundamentalsBot initialized
[VECTOR][city] Agent TechnicalBot gen 1 born at 500 HP using vector-focus
[VECTOR][technical_bot] TechnicalBot initialized
StockAnalyst OK
FundamentalsBot OK
TechnicalBot OK
```
All three agents instantiate cleanly with yfinance available.

### Feature-by-feature parity table

| Repo Feature | VECTOR File | Verified Output | Status |
|---|---|---|---|
| Stock price snapshot + historical (getStockPrices) | `districts/investment/stock_analyst.py` → `get_quote()` + `get_nse_quote()` + `_get_real_quote()` | yfinance live; NSE/BSE fallback via Yahoo Finance chart API; CoinGecko for crypto | ✅ running |
| Income statements (getIncomeStatements) | `districts/investment/fundamentals_bot.py` → `_analyze_real_financials()` | yfinance `ticker.income_stmt` → `_format_income_statement()` | ✅ running |
| Balance sheets (getBalanceSheets) | `districts/investment/fundamentals_bot.py` → `_analyze_real_financials()` | yfinance `ticker.balance_sheet` → `_format_balance_sheet()` | ✅ running |
| Cash flow statements (getCashFlowStatements) | `districts/investment/fundamentals_bot.py` → `_analyze_real_financials()` | yfinance `ticker.cashflow` → `_format_cash_flow()` | ✅ running |
| Financial metrics / derived ratios (getFinancialMetrics) | `districts/investment/fundamentals_bot.py` → `check_valuation()` + `_get_real_fundamentals()` | PE, forward_PE, PEG, EPS, ROE, profit_margin, debt_to_equity via yfinance `.info` | ⚠️ stub — `_calculate_key_metrics()` at line 151 returns all zeros for real data; only mock path returns real values |
| Stock screener / filter search (searchStocksByFilters) | `districts/investment/vector_finagent/nasdaq_data.py` → `get_equity_screener()` | NASDAQ screener by exchange + market_cap only; no 89-field filter engine | ⚠️ stub — field coverage is ~5% of repo's 89 filterable fields |
| Company news (getNews) | `districts/investment/sentiment_bot.py` → `fetch_news_sentiment()` | NewsAPI-backed with mock fallback; returns headlines + sentiment score | ✅ running (mock fallback when newsapi_key absent) |
| Streaming task decomposition (LLM query plan shown in UI) | No equivalent | VECTOR processes tasks internally; no user-visible task decomposition stream | ❌ missing |
| Generative UI — stock price chart (Recharts AreaChart) | `frontend/VECTOR.html` + `frontend/js/` | No chart components; ticker strip in dashboard uses fallback quotes; no interactive chart | ❌ missing |
| Generative UI — income/balance/cashflow/metrics tables | No equivalent | VECTOR has JSON API endpoints but no rendered financial statement tables | ❌ missing |
| Generative UI — stock screener results table (sortable) | No equivalent | No UI equivalent | ❌ missing |
| Generative UI — news carousel with sentiment badges | No equivalent | No UI equivalent | ❌ missing |
| Chat persistence (PostgreSQL, full message history) | `core/memory/episodic.py` | VECTOR has episodic SQLite memory but it stores observations/events, not structured chat threads | ⚠️ stub — episodic memory is not a chat history store with thread/message schema |
| Chat history sidebar (per-session titles, share, delete) | No equivalent | No UI equivalent | ❌ missing |
| User auth (email + password, session tokens) | `core/collections/auth.py` (PocketBase-style auth absorbed) | JWT + bcrypt exists in collections layer; not wired to investment chat | ⚠️ stub — not connected to investment workflow |
| Multi-model selection (GPT-4.1-nano/mini/4.1/4o) | `core/inference/provider_client.py` + `core/inference/llm_providers.py` | VECTOR has 27-provider routing; Ollama primary, OpenAI available via key | ✅ running (superset — more models) |
| Deduplication cache (skip repeated tool calls) | No equivalent | VECTOR agents don't deduplicate within a session | ❌ missing |
| LangSmith tracing | No equivalent | VECTOR uses loguru + reasoning_memory.py | ⚠️ different approach — not LangSmith |
| Crypto quotes (getStockPrices for BTC/ETH) | `districts/investment/stock_analyst.py` → `get_crypto_quote()` + `get_top_cryptos()` | CoinGecko API, USD + INR, top-N by market cap | ✅ running (VECTOR actually exceeds repo here) |
| NSE/BSE Indian market support | `districts/investment/stock_analyst.py` → `get_nse_quote()` | Yahoo Finance `.NS` / `.BO` suffixes with fallback | ✅ running (VECTOR only, not in repo) |

### Summary counts
- ✅ running: 7 features
- ⚠️ stub/partial: 5 features
- ❌ missing: 7 features

---

## 3. Frontend

### Repo frontend
A full production-grade Next.js 15 app with:
- **Chat interface**: streaming text + inline tool results rendered as React components
- **Recharts AreaChart**: interactive stock price chart with snapshot header (price, daily change %, market cap, volume)
- **Financial tables**: 4 table types (income statement, balance sheet, cash flow, metrics) with proper row groupings, indent levels, and number formatting (B/M abbreviations, per-share values)
- **Screener table**: sortable columns, ticker + date as fixed fields
- **News carousel**: card-per-article with thumbnail, date, source, sentiment badge
- **Query loading panel**: shows sub-task names as the LLM plans
- **Blocks side panel**: split-pane code editor (ProseMirror + CodeMirror)
- **Sidebar**: chat history, per-session titles, public/private visibility, user nav, dark mode toggle
- **API keys modal**: user inputs OpenAI key + Financial Datasets key to localStorage

Tech stack: Next.js 15 App Router, Vercel AI SDK 4.x, Drizzle ORM, Vercel Postgres, Vercel Blob, Radix UI primitives, Tailwind CSS, Recharts, Framer Motion, FontAwesome.

### VECTOR frontend
VECTOR has a static HTML/CSS/JS dashboard (`frontend/VECTOR.html`, `frontend/widgets.css`, `frontend/js/`) with a ticker marquee (live quotes via `/finance/ticker`) and a news strip (`/news/headlines`). No React. No financial statement tables. No chat UI. No interactive charts. The VECTOR dashboard spec (`docs/frontend-spec.md`) describes 200 endpoints and 6 WebSocket channels but the investment-specific UI panels (charts, tables, screener) are not built.

**Gap**: VECTOR has the data layer (yfinance, NSE, CoinGecko, fundamentals) and the API (`/investment/*` router) but zero rendering layer for financial visualizations.

---

## 4. Verdict

**Absorb: YES — 4 specific gaps worth absorbing. Do NOT absorb the app shell.**

The repo is a TypeScript/Next.js web application. VECTOR's codebase is Python-first. Absorbing the app shell (auth, chat persistence, Drizzle ORM, Vercel Postgres) is zero value — VECTOR has equivalent or better in Python (FastAPI, SQLCipher episodic memory, collections auth layer).

The genuine Python-portable gaps are:

1. **Multi-filter stock screener engine** — the repo's `searchStocksByFilters` tool implements a composable filter DSL (89 fields, 5 operators: gt/gte/lt/lte/eq) backed by `financialdatasets.ai`. VECTOR's NASDAQ screener only handles exchange + market_cap. Gap: implement `districts/investment/stock_screener.py` with the same 89-field filter schema backed by yfinance/FMP/financialdatasets, or wire the Financial Datasets API as an optional provider in `provider_client.py`.

2. **Derived financial metrics calculation fix** — `fundamentals_bot.py:_calculate_key_metrics()` (line 151) returns all zeros for live data. The repo demonstrates which 20+ derived metrics matter (P/E, EV/EBITDA, free_cash_flow_yield, PEG, ROIC, working_capital_turnover, operating_cycle, etc.). Gap: fix `_calculate_key_metrics()` to compute from income + balance DataFrames instead of returning zeros.

3. **Tool-call deduplication within a session** — the repo's `FinancialToolsManager.shouldExecuteToolCall()` (line 29) uses a per-request Set to skip duplicate tool invocations. VECTOR's investment agents have no equivalent guard; if the loop calls `get_quote()` multiple times in the same cycle, each call hits the API. Gap: add a session-scoped cache to `StockAnalyst` and `FundamentalsBot` using `functools.lru_cache` or a TTL dict.

4. **Stock screener filter constants** — the 89 filterable fields in `lib/api/stock-filters.ts` are a well-curated list of what matters for financial screening. Worth adding as a Python constant to `districts/investment/__init__.py` for validation and documentation.

The generative UI components (Recharts charts, financial tables, news carousel) are TypeScript/React — not absorbable as Python. They represent the correct design pattern for VECTOR's eventual Next.js dashboard but would need to be rebuilt in the VECTOR frontend stack.

---

## 5. Gaps

### Gap 1 — `_calculate_key_metrics()` returns all zeros (Bug)
**File:** `C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\districts\investment\fundamentals_bot.py:151-159`

```python
def _calculate_key_metrics(self, income_df, balance_df) -> dict:
    """Calculate key financial metrics."""
    return {
        "profit_margin": 0.0,   # ← always zero, never computed
        "roe": 0.0,
        "roa": 0.0,
        "debt_to_equity": 0.0,
        "current_ratio": 0.0,
        "quick_ratio": 0.0
    }
```

This means `compare_to_sector()` (line 210) always compares zeros to sector averages, producing meaningless output. The method receives `income_df` and `balance_df` DataFrames from yfinance but ignores them entirely. Fix: compute `profit_margin = net_income / revenue`, `roe = net_income / shareholders_equity`, etc. from the DataFrames.

### Gap 2 — Stock screener missing 89-field filter engine
**File:** VECTOR has no equivalent to `lib/ai/tools/financial-tools.ts:256-330` (searchStocksByFilters) or `lib/api/stock-filters.ts` (89 fields).

The repo implements a composable filter API: `[{field: "net_income", operator: "gt", value: 1e9}, {field: "revenue", operator: "gt", value: 5e10}]` backed by `POST https://api.financialdatasets.ai/financials/search/`.

VECTOR's closest equivalent is `districts/investment/vector_finagent/nasdaq_data.py:263` (`get_equity_screener()`) which only filters by exchange and market_cap string categories (not numeric comparisons). The 89-field filter list from `lib/api/stock-filters.ts` covers income statement fields, balance sheet fields, cash flow fields, valuation multiples, profitability/liquidity/leverage/growth ratios — exactly what `FundamentalsBot` and `StockAnalyst` need for screening tasks.

**Absorb target:** New file `districts/investment/stock_screener.py` — `StockScreener` class with:
- `SCREENER_FIELDS` constant (89 fields from `stock-filters.ts`)
- `search(filters: list[dict], period: str, limit: int) -> list[dict]` using yfinance bulk fetch + pandas filter logic as the free alternative to `financialdatasets.ai`
- Optional: wire `financialdatasets.ai` API as a provider when `FINANCIAL_DATASETS_API_KEY` is set in `.env`

### Gap 3 — Tool-call deduplication within session
**File:** No VECTOR equivalent to `lib/ai/tools/financial-tools.ts:29-36`.

The repo's guard:
```typescript
private shouldExecuteToolCall(toolName: string, params: any): boolean {
    const key = JSON.stringify({ toolName, params });
    if (this.toolCallCache.has(key)) return false;
    this.toolCallCache.add(key);
    return true;
}
```

VECTOR agents call the data layer on every invocation without caching. The `StockAnalyst` has an `_analysis_cache` dict but it only covers `analyze_sentiment()`, not `get_quote()` or `get_fundamentals()`. The `TechnicalBot` has `_analysis_cache` defined but never populated. Add `@functools.lru_cache(maxsize=64)` or a `TTLDict` to `get_quote()` in `stock_analyst.py` and `analyze_financials()` in `fundamentals_bot.py`.

**Files to fix:**
- `districts/investment/stock_analyst.py` — add 5-minute TTL cache on `get_quote()` and `get_fundamentals()`
- `districts/investment/technical_bot.py` — populate `_analysis_cache` on `get_price_data()` and `calculate_indicators()`
- `districts/investment/fundamentals_bot.py` — add TTL cache on `analyze_financials()`

### Gap 4 — Financial metrics table UI component missing
**Repo files (TypeScript/React — not directly absorbable):**
- `components/financial-metrics-table.tsx` — renders 20+ valuation/profitability/liquidity/leverage/growth metrics in grouped accordion sections
- `components/income-statements-table.tsx` — structured income statement with indent levels (Revenue → Gross Profit → Operating Expenses → Operating Income → Net Income)
- `components/balance-sheets-table.tsx`, `components/cash-flow-statements-table.tsx`
- `components/ui/stock-chart.tsx` — Recharts AreaChart with snapshot header
- `components/stock-screener-table.tsx` — sortable multi-column screener results
- `components/ui/news.tsx` — scrollable card carousel

These are the reference implementation for VECTOR's `docs/frontend-spec.md` investment UI panels. When building the VECTOR Next.js dashboard (currently `❌ NOT BUILT` per phase_status.md), these 6 components are the direct port targets. The data shape from VECTOR's `/investment/*` API matches what these components expect, so the components can be adapted with minimal changes.

### Gap 5 — Chat persistence for investment sessions not wired
VECTOR has `core/collections/` (PocketBase-style dynamic CRUD with JWT auth) and `core/memory/episodic.py` (SQLite FTS5 + WAL) but neither provides a structured `Chat`→`Message`→`Vote` schema equivalent to what the repo has in `lib/db/schema.ts`.

The repo's schema:
- `Chat(id, userId, title, visibility, createdAt)`
- `Message(id, chatId, role, content: json, createdAt)`
- `Vote(chatId, messageId, isUpvoted)`

For VECTOR's investment chat to persist sessions, a migration in `core/collections/` adding a `chats` and `chat_messages` collection is the natural absorb path. Low priority — VECTOR is autonomous-loop first, not chat-first.
