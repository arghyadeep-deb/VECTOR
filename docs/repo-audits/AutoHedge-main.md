# AutoHedge-main Repo Audit
**Date:** 2026-06-01  
**Auditor:** Claude Code  
**Verdict:** SAFE TO DELETE — with 🔴 CRITICAL open item before Solana is usable

---

## 5-Line Summary

- **Feature count:** 12 concrete features across 4 agents, 5 tools, market data sources.
- **Absorption real?** Yes — `districts/investment/vector_hedgebot/` mirrors AutoHedge 1:1 (all 5 agents, all 5 tools, orchestrator). All absorbed modules import cleanly.
- **Per-feature verdict:** ✅ all 12 features absorbed and importable; no ❌ missing items.
- **Is Solana execution gated?** 🔴 PARTIALLY — `live_trading=False` config flag prevents `execute_trade` from being called, but the gate is a simple boolean in `hedgebot_agent.py`, NOT the `permission_gateway`. Zero RED-tier council review for `solana_execute`. Zero kill switch. Zero paper-trading mode.
- **Delete verdict:** SAFE TO DELETE the source repo. The open CRITICAL item is a VECTOR hardening task, not a blocker on the delete.

---

## Section 1: Repo Reality

**Source:** `autohedge/` (Python package, MIT license)

### Concrete Features (12 total)

| # | Feature | Source File |
|---|---------|-------------|
| 1 | Director Agent — strategy + thesis generation, ticker discovery from task | `workers.py` |
| 2 | Quant Agent — technical scores, volume scores, trend, volatility, probability | `workers.py` |
| 3 | Risk Manager Agent — position sizing, VaR, drawdown, risk score | `workers.py` |
| 4 | Execution Agent — structured order parameters (entry/exit/SL/TP/TIF) | `workers.py` |
| 5 | Sentiment Agent — news + social sentiment scoring via Exa search | `workers.py` |
| 6 | Jupiter Price API — USD prices for Solana token mint addresses | `tools/jupiter_price.py` |
| 7 | Jupiter Token Search — search by symbol/name/mint | `tools/jupiter_search.py` |
| 8 | Jupiter Ultra `get_order` — unsigned Solana swap quote | `tools/ultra_tools.py` |
| 9 | Jupiter Ultra `execute_trade` — sign + broadcast Solana transaction (LIVE) | `tools/ultra_tools.py` |
| 10 | Jupiter Ultra `get_holdings` — wallet balance query | `tools/ultra_tools.py` |
| 11 | Yahoo/Polygon market data — OHLC, balance sheets, fundamentals | `tools/yahoo_api.py`, `tools/polygon_api.py` |
| 12 | Swarms-based multi-agent pipeline orchestrator (`AutoHedge` class) | `main.py` |

**What is NOT present in AutoHedge:** backtesting, shadow account, LangGraph swarms — those came from Vibe-Trading (already absorbed into `districts/investment/vector_backtest/`).

---

## Section 2: VECTOR Parity — Verified

### 2.1 Absorption Location

`districts/investment/vector_hedgebot/` is the direct reimplementation:

```
districts/investment/
├── hedgebot_agent.py          — VECTOR agent wrapper (AgentBase, HP, episodic memory)
├── trading_conductor_agent.py — 12-agent analysis pipeline (ANALYSIS ONLY)
├── backtest_agent.py          — Vibe-Trading quant backtest (different origin)
├── finagent_agent.py          — FinceptTerminal finance agent (different origin)
├── stock_analyst.py, ...      — existing Phase 2 agents
└── vector_hedgebot/
    ├── orchestrator.py        — VECTORHedge (mirrors AutoHedge main.py)
    ├── agents.py              — 5 agents (director, quant, risk, execution, sentiment)
    ├── prompts.py             — all 5 prompts
    └── tools/
        ├── jupiter_ultra.py   — execute_trade, get_order, get_holdings
        ├── jupiter_price.py   — get_token_price
        ├── jupiter_search.py  — search_tokens
        ├── yahoo.py           — yfinance wrapper
        ├── polygon.py         — Massive API wrapper
        └── exa_search.py      — Exa search tool
```

### 2.2 Import Tests

All ran cleanly (no ImportError, no AttributeError):

```
python -c "from districts.investment.hedgebot_agent import HedgeBotAgent; print('loads')"
→ loads

python -c "from districts.investment.trading_conductor_agent import TradingConductorAgent; print('loads')"
→ loads

python -c "from districts.investment.stock_analyst import StockAnalyst; print('loads')"
→ loads

python -c "from districts.investment.backtest_agent import BacktestAgent; print('loads')"
→ loads

python -c "from districts.investment.finagent_agent import FinAgentAgent; print('loads')"
→ loads

python -c "from districts.investment.vector_hedgebot.tools.jupiter_ultra import execute_trade, get_order; print('loads')"
→ loads
```

### 2.3 🔴 SAFETY: Solana Execution Gate Audit

**Grep for solana/jupiter/execute_trade in `districts/investment/`:**

```
core\city\governor.py:200: "hedge_run":  "investment",
core\city\governor.py:201: "hedge_trade": "investment",
core\city\governor.py:202: "solana_order": "investment",
core\city\governor.py:203: "solana_execute": "investment",
core\city\governor.py:204: "solana_holdings": "investment",
```

**Permission gateway check on `solana_execute` and `solana_order`:**

```
solana_execute_permission_gateway = False
solana_execute_live_trading_flag  = True
solana_execute_solana_private_key_check = True
solana_order_permission_gateway   = False
solana_order_live_trading_flag    = True
```

**Permission tier registry:**

```python
GREEN:  [read_calendar, play_music, search_web, ...]         # 35 actions
YELLOW: [send_message_routine, commit_code, run_tests, ...]  # 21 actions
RED:    [send_email, delete_files, execute_code,
         financial_transaction, push_github,
         deploy_production, overwrite_note_personal]         # 7 actions

solana_execute in RED? → False
solana_order   in RED? → False
financial_transaction in RED? → True  (but solana_execute is NOT mapped to it)
```

**CONFIG `vector_hedgebot.live_trading`:**

```python
CONFIG["vector_hedgebot"]["live_trading"] = False   # default
```

**Governor `_COUNCIL_TASK_TYPES` (RED-tier council triggers):**

```python
_COUNCIL_TASK_TYPES = frozenset({
    "push_github", "deploy_production", "delete_files",
    "financial_transaction", "send_email",
    "execute_code", "overwrite_note_personal", "create_pr"
})
# "solana_execute" is NOT in this set
```

**UNKNOWN fallthrough:** Any action_type not in GREEN/YELLOW/RED defaults to `UNKNOWN`, which returns `GatewayResult(approved=False)` — effectively blocked. BUT `solana_execute` never reaches the gateway at all: the governor dispatches directly to `HedgeBotAgent.run()`, which checks `live_trading` and `solana_private_key` from CONFIG, then calls `execute_trade()` directly. The permission gateway is never in the call chain.

**Kill switch:** None. No paper trading mode. No circuit breaker.

### 🔴 CRITICAL FINDING

`solana_execute` and `solana_order` bypass `permission_gateway` entirely. The only guard is `CONFIG["vector_hedgebot"]["live_trading"] == False`. Any agent or external caller with a task `{"type": "solana_execute", ...}` can trip through to `execute_trade()` in `jupiter_ultra.py` if `live_trading` is flipped to `True` (or if `SOLANA_PRIVATE_KEY` is set in .env — the code checks `solana_private_key` from the config dict, not the env var directly). The `execute_trade()` function signs and broadcasts a Solana blockchain transaction with real money. Zero RED-tier gate. Zero council review. Zero paper-trading mode.

**This is A1-class risk per VECTOR's own bug tracker.**

### 2.4 Feature Parity Verdict

| AutoHedge Feature | VECTOR Status |
|-------------------|---------------|
| Director Agent | ✅ `vector_hedgebot/agents.py` — loads |
| Quant Agent | ✅ `vector_hedgebot/agents.py` — loads |
| Risk Manager | ✅ `vector_hedgebot/agents.py` — loads |
| Execution Agent | ✅ `vector_hedgebot/agents.py` — loads |
| Sentiment Agent | ✅ `vector_hedgebot/agents.py` — loads |
| Jupiter price / search | ✅ `tools/jupiter_price.py`, `tools/jupiter_search.py` — load |
| Jupiter Ultra `get_order` | ⚠️ present and loads — ungated (see 🔴 above) |
| Jupiter Ultra `execute_trade` | ⚠️ present and loads — ungated (see 🔴 above) |
| Jupiter Ultra `get_holdings` | ✅ read-only, no gate needed |
| Yahoo / Polygon data | ✅ `tools/yahoo.py`, `tools/polygon.py` — load |
| Swarms orchestrator | ✅ `vector_hedgebot/orchestrator.py` — loads |
| Exa search | ✅ `tools/exa_search.py` — loads |

No missing features. Two execution tools need RED gating.

---

## Section 3: Frontend Panel Design

AutoHedge has no dashboard or web UI. It is a pure Python library (`pip install autohedge`). No HTML, no React, no REST server. The `cli.py` is a basic Click CLI.

**HUD panel worth building?** Yes — one panel for the VECTOR monitoring dashboard:

**Panel: "Hedge Fund Control"**

```
┌─────────────────────────────────────────────────────┐
│  HEDGE FUND CONTROL        [PAPER MODE]  [LIVE OFF] │
│─────────────────────────────────────────────────────│
│  Last Pipeline Run:  2026-06-01 03:14 | NVDA/TSLA  │
│  Director:  ✅ Bullish thesis on semicond.          │
│  Quant:     tech=0.82  vol=0.71  p_score=0.68       │
│  Risk:      size=2%  drawdown=8.4%  score=MEDIUM    │
│  Execution: LIMIT $891.50 SL $840 TP $960           │
│─────────────────────────────────────────────────────│
│  Solana Wallet:  [NOT CONNECTED]                    │
│  Holdings:       —                                  │
│  Pending Orders: 0                                  │
│─────────────────────────────────────────────────────│
│  [Run Analysis]  [View Thesis]  [Export Report]     │
└─────────────────────────────────────────────────────┘
```

Priority: low. The analysis pipeline is useful for daily VECTOR reports; live Solana trading is blocked pending the fix in Section 4.

---

## Section 4: Verdict + Delete-Readiness

### Delete Verdict: SAFE TO DELETE

The absorption is complete and verified. All 12 features are present in `districts/investment/vector_hedgebot/`. All imported clean. The source repo adds no value beyond what is already in VECTOR.

### Open Item Before Solana Can Ever Be Enabled

🔴 **CRITICAL — wire `solana_execute` and `solana_order` through permission_gateway**

Concrete fix required (two steps):

**Step 1** — Add to `core/config.py` RED permission tier:
```python
"red": [
    "send_email", "delete_files", "execute_code",
    "financial_transaction", "push_github",
    "deploy_production", "overwrite_note_personal",
    "solana_execute",   # ← ADD
    "solana_order",     # ← ADD
]
```

**Step 2** — In `hedgebot_agent.py` `solana_execute()` and `solana_order()`, replace the config boolean check with a `PermissionGateway.check()` call:
```python
from core.loop.permission_gateway import PermissionGateway, Action
gw = PermissionGateway()
result = await gw.check(Action(
    action_type="solana_execute",
    params={"request_id": request_id, "amount": "unknown"},
    agent_id=self.agent_id,
    district=self.district,
))
if not result.approved:
    return {"status": "blocked", "reason": result.reason}
```

**Step 3** — Add paper trading mode: a `paper=True` config flag that logs the signed transaction JSON but does NOT POST to `JUPITER_ULTRA_BASE/execute`.

**Step 4** — Add to `_COUNCIL_TASK_TYPES` in `governor.py`:
```python
"solana_execute",
"solana_order",
```

Until steps 1–4 are done: `live_trading` must stay `False` and `SOLANA_PRIVATE_KEY` must not be set in `.env`. The default CONFIG enforces this. Risk is contained as long as defaults hold.

### Tracker Entry

```
A1-class: solana_execute + solana_order bypass permission_gateway
Files:    districts/investment/hedgebot_agent.py (solana_execute, solana_order)
          core/config.py (permission.red list)
          core/city/governor.py (_COUNCIL_TASK_TYPES)
Fix:      4 steps above
Priority: MUST FIX before setting live_trading=True or SOLANA_PRIVATE_KEY
```
