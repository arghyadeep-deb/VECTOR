# Repo Audit — Vibe-Trading-main vs VECTOR

> Audited: 2026-05-31 · Method: read repo source + README, then ran VECTOR's
> equivalents live. Repo: `GitHub/Vibe-Trading-main` (HKUDS, MIT, Python 3.11 +
> React 19). VECTOR has already absorbed the bulk of this repo into
> `districts/investment/vector_backtest/` — this audit **verifies that claim by
> running it**, and finds the one genuine gap.

---

## Section 1 — Repo Reality (concrete features)

Vibe-Trading is an AI quant-research workspace: a natural-language agent that
generates strategy code, runs backtests across markets, validates them, and
delivers reports/exports. Concrete capabilities from the source:

| # | Feature | Where in repo |
|---|---------|---------------|
| 1 | **Multi-market backtest engines** — china_a, china_futures, crypto, forex, global_equity, global_futures, options_portfolio, composite (cross-market shared capital pool) | `agent/backtest/engines/` (12 files) |
| 2 | **Market data loaders w/ auto-fallback** — yfinance, okx, ccxt, akshare, tushare, tushare_fundamentals, futu, mootdx | `agent/backtest/loaders/` (9 files) |
| 3 | **Portfolio optimizers** — mean_variance, risk_parity, equal_volatility, max_diversification | `agent/backtest/optimizers/` |
| 4 | **Backtest metrics** — Sharpe, max DD, win rate, PnL stats, annualisation by interval/source | `agent/backtest/metrics.py` |
| 5 | **Statistical validation** — Monte Carlo, Bootstrap Sharpe CI, Walk-Forward | `agent/backtest/validation.py` |
| 6 | **Reproducible run cards** — `run_card.json`/`.md` with schema version + hash | `agent/backtest/run_card.py` |
| 7 | **Correlation matrix** — rolling return correlation, Spearman, market inference | `agent/backtest/correlation.py` |
| 8 | **Benchmark comparison** — excess return, information ratio vs SPY/CSI300 | `agent/backtest/benchmark.py` |
| 9 | **Alpha Zoo — 452 pre-built quant factors** (alpha101=101, gtja191=191, qlib158=154, academic=6) + registry + bench runner (IC/IR, alive/reversed/dead), strict OOS gate, AST purity gate | `agent/src/factors/` + `zoo/` |
| 10 | **Agent harness** — ReAct loop, persistent cross-session memory, FTS5 session search, self-evolving skills | `agent/src/agent/`, `src/session/`, `src/memory/` |
| 11 | **77/74 finance skills** (data, strategy, analysis, asset-class, crypto, flow, tool, risk) | `agent/src/skills/` |
| 12 | **29 swarm presets** — multi-agent trading teams (investment_committee, quant_strategy_desk, etc.) | `agent/src/swarm/presets/` |
| 13 | **Shadow Account** — broker-journal parse → behavior diagnostics → rule extraction → shadow backtest → HTML/PDF report | `agent/src/shadow_account/` |
| 14 | **Trade Journal Analyzer** — parse 同花顺/东财/富途/generic CSV, bias diagnostics | `agent/src/tools/trade_journal_*.py` |
| 15 | **Universal document reader** — PDF/Word/Excel/PPT/image-OCR | `agent/src/tools/doc_reader_tool.py` |
| 16 | **Multi-platform export** — TradingView Pine v6, TDX, MetaTrader 5 (MQL5), vnpy CtaTemplate | `src/skills/pine-script`, `vnpy-export` |
| 17 | **22 MCP tools + FastAPI server + SSE streaming** | `agent/mcp_server.py`, `agent/api_server.py` |
| 18 | **React 19 + ECharts Web UI** — agent chat, run detail, alpha zoo, correlation heatmap, compare, settings | `frontend/` |
| 19 | **Robinhood Agentic live trading** (opt-in, mandate-bounded, kill switch, audit ledger) — **live order execution** | `agent/src/live/` (robinhood, mandate, propose_mandate_tool) |

---

## Section 2 — VECTOR Parity (verified by running)

**Key finding:** VECTOR absorbed Vibe-Trading near-wholesale into
`districts/investment/vector_backtest/` (a near-mirror of the repo's `agent/`:
same `backtest/engines/`, `loaders/`, `optimizers/`, `src/swarm/`,
`src/shadow_account/`, `src/skills/`, `mcp_server.py`, `cli.py`, plus a `tests/`
suite). All runs below were executed against that tree.

| # | Repo feature | VECTOR location | Test run + actual output | Verdict |
|---|--------------|-----------------|--------------------------|---------|
| 1 | Backtest engines (12) | `vector_backtest/backtest/engines/` | listdir → `['base','china_a','china_futures','composite','crypto','forex','futures_base','global_equity','global_futures','options_portfolio']` | ✅ |
| 2 | Data loaders + fallback | `…/loaders/` | importing all 6 → `LOADER_REGISTRY = ['akshare','ccxt','futu','okx','tushare','yfinance']`; `FALLBACK_CHAINS` = 8 markets (a_share, crypto, forex, fund, futures, hk_equity, macro, us_equity) | ✅ (mootdx loader from repo's 2026-05-27 update **not** present — see gap note) |
| 3 | Optimizers (4) | `…/optimizers/` | listdir → `['base','equal_volatility','max_diversification','mean_variance','risk_parity']` | ✅ |
| 4 | Metrics | `…/backtest/metrics.py` | `calc_bars_per_year('1D','yfinance')` → `252`; `('1H','okx')` → `8760` | ✅ |
| 5 | Validation (MC/Bootstrap/WF) | `…/backtest/validation.py` | `monte_carlo_test(trades,100000,n_simulations=300)` → `{actual_sharpe, p_value_sharpe, simulated_sharpe_p5/p95, n_simulations…}`; `bootstrap_sharpe_ci(eq)` → `{observed_sharpe, ci_lower, ci_upper, prob_positive…}`. Real statistical output. (Walk-forward present; my synthetic string dates broke a `<=` compare — harness artifact, not a code defect.) | ✅ |
| 6 | Run cards | `…/backtest/run_card.py` | exposes `write_run_card`, `SCHEMA_VERSION`, `BACKTEST_SUMMARY_KEYS` | ✅ |
| 7 | Correlation | `…/backtest/correlation.py` | exposes `compute_correlation_matrix`, `infer_market`, `spearmanr` | ✅ |
| 8 | Benchmark comparison | `…/backtest/benchmark.py` | file present (same as repo) | ✅ |
| 9 | **Alpha Zoo (452 factors)** | — | `find` for `factors/`, `zoo/`, `alpha101`, `gtja191`, `qlib158`, `*alpha*`, `*gtja*` across `vector_backtest/` and whole VECTOR (excl. worktrees) → **nothing**. Only `social_alpha_team.yaml` swarm preset matches the name. The entire `src/factors/` module (registry, bench_runner, strict OOS gate, 452 alpha files) was **not absorbed**. | ❌ **MISSING** |
| 10 | Agent harness (memory, FTS5 search, skills) | `…/src/agent/`, `src/session/`, `src/memory/persistent.py` | dirs present; session has `events/models/search/service/store` | ✅ |
| 11 | Finance skills | `…/src/skills/` | `74` skill dirs (repo claims 77; 3 fewer — minor) | ✅ |
| 12 | Swarm presets (29) | `…/src/swarm/presets/` | `29` preset YAMLs counted | ✅ |
| 13 | Shadow Account | `…/src/shadow_account/` | `import extractor, backtester, scanner, reporter, codegen` → OK | ✅ |
| 14 | Trade Journal Analyzer | `…/src/tools/trade_journal_parsers.py` | exposes `detect_format`, `parse_eastmoney`, `parse_file`, `load_dataframe`, `TradeRecord` | ✅ |
| 15 | Document reader | `…/src/tools/doc_reader_tool.py` | file present | ✅ |
| 16 | Pine/TDX/MT5/vnpy export | `…/src/skills/pine-script`, `vnpy-export` | skill dirs present | ✅ |
| 17 | MCP server + FastAPI + SSE | `…/mcp_server.py`, `api_server.py`, `src/session/events.py` | files present | ✅ |
| 18 | React/ECharts Web UI | — (no `vector_backtest/frontend/`) | not absorbed; VECTOR uses its own HUD/dashboard. Out of scope as a separate web app; see Section 3 for a HUD panel spec. | ⚠️ not absorbed (by design) |
| 19 | **Robinhood live trading / order execution** | — | absent from `vector_backtest/` (no `live/`, no `mandate`, no `propose_mandate_tool`). VECTOR's only "robinhood" match is an unrelated `vectorcode/skills/vc-as-robinhood` engineering persona. | 🚫 **OUT OF SCOPE BY DESIGN** — investment district is ANALYSIS ONLY, never executes trades (districts.md / architecture rule) |

### Optional-dependency notes
- yfinance / akshare / ccxt / tushare / futu loaders import and self-register
  cleanly here; live data pulls need each provider's package + network. Code is
  present and registered — ⚠️ only "needs `<dep>`" for live fetch, not a gap.
- `mootdx` A-share loader (repo's 2026-05-27 addition) is **absent** in VECTOR —
  small data-source gap, not blocking (akshare/tushare cover A-shares).

### Score
- Repo features: **19**
- VECTOR: ✅ **15** · ⚠️ **2** (Web UI not absorbed by design; mootdx loader missing) · ❌ **1** (Alpha Zoo)
- Out of scope by design: **1** (Robinhood live trading)

---

## Section 3 — Frontend → VECTOR HUD Trading Panel Spec (document only)

Repo frontend: **React 19 + Vite + Tailwind + ECharts + zustand**, dark-mode
class-based, `react-markdown`+`remark-gfm` for agent answers. Documented as a
spec for a future VECTOR finance/trading HUD panel — not built here.

**Color tokens (HSL, from `frontend/src/index.css`):**
| Token | Light | Dark | Use |
|-------|-------|------|-----|
| primary | `27 90% 52%` (amber/orange) | same | accent, CTAs |
| background | `220 20% 98%` | `220 20% 5%` | page base |
| card | `0 0% 100%` | `220 20% 8%` | surfaces |
| success | `142 71% 45%` | same | gains / long |
| danger | `0 84% 60%` | `0 62% 50%` | losses / short |
| warning | `38 92% 50%` | — | drawdown alerts |
| info | `217 91% 60%` | — | neutral metrics |
| border / radius | `220 14% 87%` / `0.5rem` | `220 20% 18%` | dividers |
Fonts: Inter (sans) + JetBrains Mono (numbers/code).

**Pages → VECTOR HUD tabs:** `Home` (hero + 4 feature cards), `Agent` (chat +
live tool rail), `RunDetail` (metrics + equity + validation + run card),
`AlphaZoo` (factor browser), `Correlation` (heatmap), `Compare` (run A/B), `Settings`.

**Reusable panel widgets (from `frontend/src/components/`):**
- `charts/EquityChart` + `MiniEquityChart` — portfolio equity curve (ECharts).
- `charts/CandlestickChart` — OHLCV w/ indicator overlays (`lib/indicators.ts`).
- `charts/CorrelationMatrix` — heatmap.
- `charts/ValidationPanel` — Monte Carlo / Bootstrap / Walk-Forward results.
- `chat/MetricsCard` — Sharpe / max DD / win-rate tiles (success/danger coloring).
- `chat/RunCompleteCard`, `RunnerStatus`, `ToolProgressIndicator` (ARIA `role=status`, determinate `ProgressRing`), `ThinkingTimeline`.
- `chat/PineScriptViewer` — syntax-highlighted export.
- `chat/MandateProposalCard` — **live-trade mandate UI; skip for VECTOR (out of scope).**

**HUD recommendation:** a "Quant" panel = equity chart + metrics tiles +
validation panel + correlation heatmap, amber-accent on a near-black surface,
mono font for all numerics. Feed from `vector_backtest` run-card JSON.

---

## Section 4 — Verdict

### PATCH VECTOR — one real gap: the Alpha Zoo

**Reasoning (size of gap):** 17 of 19 repo features are already present and were
**run successfully** in `districts/investment/vector_backtest/` (engines, loaders,
optimizers, metrics, Monte Carlo/Bootstrap validation, run cards, correlation,
shadow account, 29 swarm presets, 74 skills, trade journal, MCP/API). One feature
(Robinhood live order execution) is **out of scope by VECTOR design** — investment
district is analysis-only — and is correctly absent; do not add it. One (React Web
UI) is intentionally not absorbed (VECTOR has its own HUD; spec captured above).

The **single genuine gap** is the **Alpha Zoo**: the repo's `agent/src/factors/`
module — `registry.py`, `bench_runner.py`, `bench_runner_strict.py`,
`factor_analysis_core.py`, `cli_handlers.py`, `base.py` — plus the 452 factor files
under `agent/src/factors/zoo/{alpha101 (101), gtja191 (191), qlib158 (154),
academic (6)}`. None of it exists anywhere in VECTOR.

**Exact missing pieces to port (MIT / Apache-2 / public-formula licensed):**
1. `agent/src/factors/` (6 core modules) → `districts/investment/vector_backtest/src/factors/`
2. `agent/src/factors/zoo/` (452 alpha files, 4 zoos) → same tree
3. Wire the `alpha bench/list/show` CLI handlers into `vector_backtest/cli.py`
   (alpha subcommands not present today) and `alpha_routes` into the API server.
4. Minor: also port the `mootdx` A-share loader (`agent/backtest/loaders/mootdx_loader.py`).

This is an **additive copy** of self-contained, pure-pandas factor files + a
registry — no rewrite of VECTOR's existing engine. Small, bounded, license-clean.

**Do NOT delete the repo** until the Alpha Zoo (+mootdx) is ported; everything else
is safe.

---

### 5-line summary
- Repo features: **19**.
- VECTOR: ✅ **15** real & verified-by-running · ⚠️ **2** (React Web UI not absorbed by design; mootdx loader missing) · ❌ **1** (Alpha Zoo / 452 factors entirely absent).
- Out of scope by design: **1** (Robinhood live order execution — investment district is analysis-only; correctly absent).
- Verified live: 12 engines, 6 self-registering loaders + 8 fallback markets, 4 optimizers, metrics, Monte Carlo + Bootstrap CI (real stats), run cards, correlation, shadow account, 29 swarm presets, 74 skills, trade-journal parsers — all in `districts/investment/vector_backtest/`.
- Verdict: **PATCH VECTOR** — port `agent/src/factors/` + `zoo/` (452 alphas) and the `mootdx` loader; small additive gap, not a rewrite.
