# nautilus_trader-develop - VECTOR Absorption Review

**Verdict:** DO NOT ABSORB. Use as an external engine only if VECTOR moves into serious live trading; reimplement selected safety ideas clean-room.

**Priority:** MEDIUM for investment hardening, LOW for immediate VECTOR/JARVIS roadmap

**Effort:** 2-4 sessions for a clean-room trading hardening layer; much larger for real Nautilus integration

**License:** LGPL-3.0-or-later

**Repo size inspected:** ~5,725 files / ~161.15 MB excluding `.git`, target, build, and dist

## What It Is

NautilusTrader is a production-grade Rust-native trading engine with Python control-plane APIs. It focuses on:

- deterministic event-driven trading runtime
- research-to-live parity
- backtesting with historical ticks, trades, bars, order books, and custom data
- live execution across multiple venues
- adapters for crypto, Interactive Brokers, betting/prediction markets, and data providers
- risk engine, execution engine, portfolio, cache, message bus, strategy model
- advanced orders: IOC, FOK, GTC, GTD, OCO, OTO, post-only, reduce-only, icebergs, stop/limit variants
- supply-chain/security discipline

This is real trading infrastructure, not a small utility.

## VECTOR Already Has

- `districts/investment/execution_engine.py`
- `districts/investment/safety.py`
- `districts/investment/vector_finagent/`
- `core/trading/`
- paper-first execution
- PermissionGateway approval for live financial actions
- kill switch and global caps
- OpenAlice review recommending staged order lifecycle
- research agents, market/status endpoints, and investment docs

VECTOR is already a personal trading assistant. Nautilus is a professional trading engine.

## Overlap

Approximate overlap: **50-60%** conceptually, but only **15-25%** implementation-compatible.

Both deal with trading, backtesting, risk, and execution. But Nautilus is a separate Rust/Python engine with its own domain model, runtime, adapters, precision model, persistence, and licensing obligations.

## License Boundary

Nautilus is LGPL-3.0-or-later. That does not automatically ban usage, but it is not the same as MIT/Apache absorption.

Do not copy code, schemas, tests, Rust domain types, adapter implementations, or Python wrappers into VECTOR.

If using Nautilus directly later, treat it as a clearly separate dependency or process, keep license notices, and document the boundary.

## Real Value For VECTOR

### 1. Stronger order lifecycle

Nautilus reinforces the OpenAlice finding: VECTOR needs a reviewable order lifecycle before real-money automation becomes serious.

Clean-room states:

- `draft`
- `staged`
- `risk_checked`
- `approved`
- `submitted`
- `accepted`
- `partially_filled`
- `filled`
- `cancel_requested`
- `cancelled`
- `rejected`
- `failed`

### 2. Research-to-live parity

VECTOR should make strategy logic run against the same interface in:

- paper mode
- backtest mode
- live mode

Today, paper/live behavior can drift if code paths are different. Nautilus shows why this matters.

### 3. Portfolio and risk snapshots

Add immutable snapshots around every proposed trade:

- cash
- positions
- exposure
- open orders
- daily realized/unrealized PnL
- max drawdown
- account/broker profile
- rule decisions

These snapshots should be attached to PermissionGateway approvals.

### 4. Broker adapter boundary

VECTOR should keep broker credentials and broker-specific execution away from LLM/planning code. This aligns with both OpenAlice and Nautilus.

### 5. External integration option

If the owner later wants serious live trading/backtesting, integrate Nautilus as an external engine:

- VECTOR creates strategies, scenarios, and review requests.
- Nautilus runs deterministic backtests/paper execution.
- VECTOR reads results and asks for owner approval.
- Live execution still requires explicit owner permission.

## What Not To Absorb

- Do not port Nautilus's engine.
- Do not vendor Rust crates.
- Do not copy adapters.
- Do not replace VECTOR's investment district with Nautilus.
- Do not add live trading shortcuts.
- Do not make LLM-generated strategies execute live without staging, risk checks, and approval.
- Do not introduce LGPL obligations accidentally by copying implementation.

## Implementation Option A - Recommended Now

Clean-room harden VECTOR's own investment execution.

1. Implement staged order lifecycle as already suggested in `openalice.md`.
2. Add portfolio/risk snapshot capture before approval.
3. Add paper/live parity tests.
4. Add broker account profile config.
5. Add an append-only execution event log.

## Implementation Option B - Later External Engine

Only if real trading scope expands:

1. Add `districts/investment/engines/nautilus_adapter.py`.
2. Treat Nautilus as an optional installed dependency or separate process.
3. Support paper/backtest first.
4. Never pass provider API keys or broker secrets through prompts.
5. Keep live execution disabled by default.
6. Add a clear license notice and dependency boundary doc.

## Acceptance Criteria For Option A

- Default remains paper trading.
- Live execution requires explicit approval.
- Every order has immutable transition history.
- Every approval includes a risk snapshot.
- Backtest/paper/live use the same order intent schema.
- Tests prove rejected/failed orders never reach broker execution.

## Final Recommendation

Nautilus is valuable as a north star for trading rigor, but too large and too separate to absorb. Use it to justify a clean-room order lifecycle, risk snapshots, and paper/live parity inside VECTOR. Consider direct Nautilus integration only when VECTOR is ready for serious broker-backed trading.
