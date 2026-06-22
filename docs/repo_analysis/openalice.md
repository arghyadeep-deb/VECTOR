# OpenAlice-master - VECTOR Absorption Review

**Verdict:** LEARN architecture, do not copy code. Implement one clean-room trading-state upgrade only if live-trading scope expands.

**Priority:** MEDIUM for design reference, LOW for immediate implementation

**Effort:** 2-3 sessions if the trading-state upgrade is accepted

**License:** AGPL-3.0-only

**Repo size inspected:** ~1,848 files / ~8.85 MB

## License Boundary

OpenAlice is **AGPL-3.0-only**. Do not copy code, schemas, prompts, UI, tests, or file structure into VECTOR unless the owner intentionally accepts AGPL obligations for the relevant derivative work.

Allowed use here: architecture review and clean-room reimplementation of general ideas.

## What It Is

OpenAlice is an AI trading/workspace system. Its strongest ideas are:

- **UTA service:** broker credentials and execution live in a separate carrier process
- **Trading-as-Git:** stage orders, commit with a message, push to execute
- **Guard pipeline:** per-account pre-execution safety checks
- **Broker abstraction:** CCXT, Alpaca, Interactive Brokers, Longbridge, mock broker
- **Workspace substrate:** per-task directory + git repo + native agent CLI session
- **Inbox:** append-only workspace-to-user push channel
- **Headless scheduled runs:** cron spawns a workspace task and agents report back through Inbox

## VECTOR Already Has

- `districts/investment/execution_engine.py`: paper-first execution, kill switch, caps, permission gateway, live broker path
- `districts/investment/safety.py`: owner approval for live financial actions
- `districts/investment/vector_finagent/`: large analysis/research/trading stack
- `core/trading/`: multi-agent trading graph already live-proven in capability docs
- `api/src/router.ts`, `api/schema.sql`, `phone_node/ambient_server.py`: Cloudflare command queue, node polling, result posting, Termux node
- `districts/governance/federation_agent.py`: peer task delegation
- `core/coding_assistant/`: programmatic/headless coding assistant paths
- event bus, scheduler, memory, and permission gates

OpenAlice is not a replacement for VECTOR's investment district. Its useful value is in execution boundary discipline.

## Overlap

Approximate overlap: **70-75%**.

VECTOR already has research, investment analysis, permission-gated execution, scheduling, federation, and the new cloud/Termux node queue. OpenAlice is more mature specifically around broker isolation and a reviewable staged order lifecycle.

## Real Gaps Worth Considering

1. **Staged order lifecycle.** VECTOR has a paper/live ledger, but not a true staged -> reviewed -> committed -> pushed state machine. A clean-room version would make financial action review clearer.

2. **Broker credential isolation.** VECTOR keeps execution code in the same Python app. A small credential-holding carrier is a stronger long-term security boundary for real money.

3. **Per-account guard configuration.** VECTOR has global guardrails; per-account guards are cleaner for multiple brokers/accounts.

4. **Workspace-to-user push channel.** VECTOR has queues, memory, UI, and federation, but not exactly an append-only "agent pushed this doc/comment from a workspace" inbox. Useful, but less urgent than the trading boundary.

## What Not To Absorb

- Do not copy any TypeScript code.
- Do not vendor OpenAlice packages.
- Do not copy its UTA protocol schemas.
- Do not copy UI/workspace/inbox implementation.
- Do not add live broker support beyond what VECTOR can test and gate safely.
- Do not loosen VECTOR's `paper_trading=True` default.

## Implementation Option A - Recommended Now

Document only. No code.

Reason: VECTOR's current execution engine is already paper-first and permission-gated. The next urgent repo absorptions are security and voice/content upgrades, not a full trading substrate rewrite.

## Implementation Option B - If Owner Wants Stronger Trading Safety

Build a clean-room staged order layer in Python.

1. Add `districts/investment/order_lifecycle.py`.
   - States: `draft`, `staged`, `committed`, `approved`, `pushed`, `filled`, `rejected`, `cancelled`, `failed`.
   - Store every transition in SQLite.
   - Include reason/message, proposed_by, approved_by, risk snapshot, and timestamp.

2. Update `ExecutionEngine`.
   - `place_order()` in paper mode can still fill immediately.
   - In live mode, create a staged order first.
   - Only `push_order(order_id)` calls the broker after permission approval.

3. Add per-account guard config.
   - Keep existing global caps as defaults.
   - Add optional account profile: broker, paper/live, max position size, allowed symbols, cooldown, max trades/day.

4. Preserve PermissionGateway.
   - RED approval remains mandatory.
   - Never allow an LLM-only path to push a live order.

5. Add tests.
   - staged order cannot execute without approval
   - rejected approval never calls broker
   - kill switch blocks push
   - paper mode remains backward compatible
   - transition log is append-only

## Acceptance Criteria For Option B

- No AGPL code or schema shape is copied.
- Default behavior remains paper trading.
- Existing investment/trading tests pass.
- Live broker call is reachable only through explicit push + permission approval.
- Transition history is reviewable by order id.

## Final Recommendation

Treat OpenAlice as a **design reference**, not an absorption source. The only idea worth implementing soon is a clean-room staged order lifecycle for VECTOR's investment execution engine. Everything else overlaps with existing VECTOR systems or is blocked by AGPL risk.
