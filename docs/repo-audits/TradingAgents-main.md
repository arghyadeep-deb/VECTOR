# Repo Audit — TradingAgents-main (TauricResearch)

> Audited: 2026-05-31 · Method: read + RUN against VECTOR · Verdict: **SAFE TO DELETE (already ported) + small PATCH gaps**
> Repo: `GitHub/TradingAgents-main` · v0.2.5 · arXiv 2412.20138 · License: Apache-2.0 (LICENSE present)

---

## Section 1 — Repo Reality

**What it is:** A LangGraph multi-agent LLM trading framework that mirrors a trading desk. Decomposes "should I trade ticker X on date Y?" into specialized LLM agents that produce reports, **debate** (bull vs bear, then a 3-way risk debate), and converge on a **5-tier rating** (Buy / Overweight / Hold / Underweight / Sell). Research artifact — *not* a live trading bot.

**Stack:** `langgraph>=0.4.8`, `langchain-{core,openai,anthropic,google-genai}`, `langgraph-checkpoint-sqlite`, `yfinance`, `stockstats`, `pandas`, `rich`+`typer`+`questionary` (CLI), `backtrader` (declared but **never imported** — dead dep), `redis` (optional cache). Python ≥3.10. `requirements.txt` is empty (2 bytes); deps live in `pyproject.toml`.

**Concrete features (verified by reading source):**

| # | Feature | File |
|---|---------|------|
| 1 | **Analyst team (4):** market/technical, sentiment, news, fundamentals — each a ToolNode agent | `agents/analysts/*.py` |
| 2 | **Researcher debate:** bull vs bear, N rounds, free-text back-and-forth | `agents/researchers/{bull,bear}_researcher.py` |
| 3 | **Research Manager:** synthesizes debate → investment plan (structured output) | `agents/managers/research_manager.py` |
| 4 | **Trader:** investment plan → concrete BUY/SELL/HOLD proposal w/ entry levels | `agents/trader/trader.py` |
| 5 | **Risk debate (3):** aggressive vs conservative vs neutral debators | `agents/risk_mgmt/*_debator.py` |
| 6 | **Portfolio Manager:** synthesizes risk debate → final 5-tier rating | `agents/managers/portfolio_manager.py` |
| 7 | **Debate flow control:** round-counting conditional edges | `graph/conditional_logic.py` |
| 8 | **Signal processing:** deterministic regex rating extractor (no extra LLM call) | `graph/signal_processing.py`, `agents/utils/rating.py` |
| 9 | **Memory log + reflection:** append-only `trading_memory.md`; next same-ticker run fetches realized return (raw + alpha vs SPY) and injects reflections into PM prompt | `agents/utils/memory.py`, `graph/reflection.py` |
| 10 | **Checkpoint resume:** opt-in per-ticker SQLite LangGraph saver, resume crashed runs | `graph/checkpointer.py` |
| 11 | **Data feeds:** yfinance, Alpha Vantage (stock/fundamentals/indicator/news), Reddit, StockTwits, stockstats | `dataflows/*.py` |
| 12 | **Multi-provider LLM:** OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen (intl+CN), GLM, MiniMax (intl+CN), OpenRouter, **Ollama**, Azure | `llm_clients/*` |
| 13 | **Crypto asset mode** (v0.2.5): `asset_type="crypto"` branches prompts/fundamentals | `agents/**` (`asset_type` plumbing) |
| 14 | **Rich CLI dashboard:** `rich.Live`+`Layout` real-time agent-progress view; `questionary` interactive setup | `cli/main.py` (1287 LOC) |
| 15 | **Backtest "date fidelity":** holding-period return calc vs benchmark; benchmark map by exchange suffix | `graph/trading_graph.py:_fetch_returns` |

**Execution:** README claims *"the order will be sent to the simulated exchange and executed."* This is **false / aspirational** — `grep` for `place_order`/`submit_order`/`broker`/`self.buy`/`backtrader` import = **zero matches in code**. The actual terminal output is a **rating string + markdown decision log**. No order routing, no broker, no paper account, no kill-switch. **No execution gap to capture — there is no execution.**

---

## Section 2 — VECTOR Parity (verified by import + run)

**Headline:** VECTOR already contains a **near-1:1 Python port of this entire framework** at `core/trading/` (the graph) + `core/trading/agents/` (every role), wrapped by `districts/investment/trading_conductor_agent.py`. This was absorbed in an earlier session.

| Repo feature | VECTOR equivalent | Run result | Verdict |
|---|---|---|---|
| Full graph orchestrator (`TradingAgentsGraph`) | `core/trading/graph/trading_graph.py` → `VectorTradingGraph`; wrapped by `districts/investment/trading_conductor_agent.py` | `TradingConductorAgent()` instantiated, **HP=500, district=investment**. Graph import fails ONLY on missing optional dep `langgraph.checkpoint.sqlite` (⚠️ pip gap, not a code bug). | ⚠️ (dep) |
| 4 analysts | `core/trading/agents/analysts/{market,sentiment,news,fundamentals,social_media}_analyst.py` | All 5 files present (ported). | ✅ |
| Bull/Bear researchers | `core/trading/agents/researchers/{bull,bear}_researcher.py` | `diff` vs repo = **byte-identical logic** except import path + missing crypto branch (see gaps). | ✅ |
| Research Manager + Trader + Portfolio Manager | `core/trading/agents/managers/*`, `trader/trader.py` | Present, ported. | ✅ |
| Risk debate (aggressive/conservative/neutral) | `core/trading/agents/risk_mgmt/{aggressive,conservative,neutral}_debator.py` | All 3 present. | ✅ |
| Conditional debate logic | `core/trading/graph/conditional_logic.py` | Present. | ✅ |
| Signal/rating extraction | `core/trading/agents/utils/rating.py`, `graph/signal_processing.py` | Present. | ✅ |
| Memory log + reflection | `core/trading/agents/utils/memory.py` (`TradingMemoryLog`); also `get_past_performance()` action | Present; conductor exposes `past_performance` action. | ✅ |
| Data feeds | `core/trading/dataflows/*` **+** `districts/investment/vector_finagent/` (**200+ data-source modules**: yfinance, alpha_vantage, finnhub, reddit, fred, akshare, polygon, sec, coingecko…) | `finagent_agent.py` ran clean: **HP=500**, terminal built, 6 actions. VECTOR's data layer dwarfs the repo's. | ✅ |
| Multi-provider LLM | `core/trading/llm_clients/factory.py` (ollama+openrouter+openai…) **+** `core/inference/provider_client.py` (27 providers, Ollama-first) | Config verified: `llm_provider=openai` but `deep_think_llm=vector-reasoning` (an **Ollama** model) — Ollama-first intent wired. | ✅ |
| **Multi-agent DEBATE→decision** (the core value) | TWO layers: (a) the **ported finance-specific** bull/bear + 3-way risk debate above; (b) `districts/governance/llm_council.py` — generic **3-stage deliberation** (Stage1 independent answers → Stage2 blind peer ranking → Stage3 chairman synthesis), HP>700 gate | Council 3-stage methods confirmed (`_stage1_collect`, `_stage2_rank`, `_stage3_synthesize`). The council is *more sophisticated* (blind ranking) but **domain-agnostic**; the finance roles are the domain-specific match. **VECTOR has both.** | ✅ |
| Backtest / returns | `districts/investment/vector_backtest/` (full engine: runner, metrics, optimizers, validation, benchmark) — far beyond the repo's holding-period calc | ⚠️ `vector_backtest/__init__.py:21` has an **IndentationError** (truncated `if` body, likely an autocommit artifact) blocking package import. Engine files themselves are intact. | ⚠️ (bug) |
| **Live execution** (hedge fund) | `districts/investment/hedgebot_agent.py` + `vector_hedgebot/tools/jupiter_ultra.py` — **real Solana DEX execution** via Jupiter Ultra Swap (`get_order` → `execute_trade` signs w/ `SOLANA_PRIVATE_KEY`) | VECTOR has *more* than the repo here: actual on-chain order signing. (Repo has none.) | ✅ (exceeds) |

**Net:** Every TradingAgents feature is present in VECTOR, mostly as a direct port. Two operational ⚠️s (missing `langgraph-checkpoint-sqlite` dep; a one-line indentation bug in the backtest `__init__`). Two genuine **content gaps** where the repo's v0.2.5 is newer than VECTOR's port (below).

### Real gaps (repo is newer than VECTOR's port)
- ❌ **Crypto `asset_type` mode** — repo's agents branch stock vs crypto (`grep asset_type core/trading` = **0 files**; VECTOR's `bull_researcher.py` hardcodes `"stock"`). VECTOR's *crypto execution* lives in hedgebot, but the **analysis/debate pipeline is stock-only**.
- ❌ **Newer model catalog** — repo adds gpt-5.5, glm-5, minimax dual-region, grounded sentiment analyst, `TRADINGAGENTS_*` env-var config + API-key auto-detect, remote-Ollama URL, ticker path-traversal hardening. VECTOR's port predates these.

---

## Section 3 — Frontend → HUD Panel

The repo ships a **`rich.Live` + `Layout` terminal dashboard** (`cli/main.py`, 1287 LOC): a header + multi-region live view that streams each agent's progress (analysts running → bull/bear debate transcript → risk debate → final rating) as the graph executes. `questionary` drives interactive ticker/date/provider/depth selection.

**Panel spec — "Trading Debate" HUD (recommended: build, low cost):**
- **Layout:** left rail = pipeline stages (Analysts → Researchers → Trader → Risk → PM) with live status dots; center = streaming debate transcript (bull vs bear color-coded, then 3-way risk); right = final 5-tier rating badge + realized-return reflection from the memory log.
- **Data source:** `VectorTradingGraph.propagate()` already `stream()`s per-node chunks (`trading_graph.py:_run_graph` debug path) — wire those chunks to a WS channel. Reflection/alpha pulled from `TradingMemoryLog.get_past_context()`.
- **Worth it?** **Yes, modest value.** The debate transcript is the single most legible, "watchable" output VECTOR's investment district produces — ideal for a HUD finance tab. It's read-only (no execution), so safe. Reuse the existing stream seam; don't rebuild the graph.

---

## Section 4 — Verdict

### SAFE TO DELETE the cloned repo — with two PATCHes to VECTOR

**Reasoning by size-of-gap:** The repo is a research framework whose *entire* surface area is already inside VECTOR (`core/trading/` is a verified near-byte-identical port; `bull_researcher.py` diff = logic-identical). VECTOR additionally **exceeds** it: a 200+ source data layer (`vector_finagent/`), a real backtest engine (`vector_backtest/`), a blind-ranking deliberative council, and **actual live Solana execution** (hedgebot) — which the repo only *claims* to have. Keeping the clone adds nothing; it is an older snapshot of code VECTOR already owns. **Delete it.**

Before deleting, harvest the two deltas where the repo is newer:

1. **PATCH — crypto asset mode.** Port `asset_type` plumbing into VECTOR's stock-only debate pipeline.
   - Seam: `core/trading/agents/researchers/bull_researcher.py` (and bear, trader, PM, fundamentals_analyst) — re-introduce the `asset_type = state.get("asset_type","stock")` branch + crypto fundamentals label. Compare against repo `tradingagents/agents/**` which already has it.
   - Wire `asset_type` through `core/trading/graph/propagation.py` initial state. Conductor already accepts it conceptually (`run_analysis` ticker is provider-agnostic).
   - Size: ~6 files, mechanical (the repo is the reference diff). High value — unifies VECTOR's stock-analysis and crypto-execution sides.

2. **PATCH — model catalog + env config.** Refresh `core/trading/llm_clients/model_catalog.py` with gpt-5.5 / glm-5 / minimax dual-region; adopt repo's `TRADINGAGENTS_*`→VECTOR-CONFIG env mapping + remote-Ollama `OLLAMA_BASE_URL`. Low effort, keeps the port current. (Provider-agnostic already satisfied via `provider_client.py`.)

### Also fix (pre-existing VECTOR bugs surfaced during audit — not from this repo)
- `districts/investment/vector_backtest/__init__.py:21` — **IndentationError** (empty body after `if str(_BACKTEST_DIR) not in sys.path:`). Blocks backtest package import. Likely an autocommit truncation. **PATCH** `vector_backtest/__init__.py:21`.
- Missing dep: add `langgraph-checkpoint-sqlite` to VECTOR requirements so `VectorTradingGraph` imports without the checkpointer error.

### Execution note
Repo has **no execution** despite README claims (in-scope gap = N/A). VECTOR's *own* hedgebot has live Solana signing — that is a separate, pre-existing VECTOR concern that should sit behind the permission gateway RED (paper-first + human-confirmed). Not introduced by this repo.

---

### 5-line summary
- **What:** TradingAgents v0.2.5 — LangGraph multi-agent LLM trading framework (analysts → bull/bear debate → trader → 3-way risk debate → 5-tier rating + reflective memory log). Research artifact.
- **Feature count:** 15 concrete features.
- **Verdicts:** ✅ 9 · ⚠️ 3 (missing sqlite-checkpoint dep, backtest `__init__` indentation bug, both pre-existing in VECTOR) · ❌ 2 real gaps (crypto asset mode; newer model catalog).
- **Execution?** No — README "simulated exchange" claim is false; output is a rating + markdown log. (VECTOR's hedgebot, separately, *does* execute on Solana.)
- **Verdict:** **SAFE TO DELETE** clone — VECTOR already holds a verified near-1:1 port at `core/trading/` and exceeds it. Harvest 2 small PATCHes first: crypto `asset_type` plumbing + refreshed model catalog.
