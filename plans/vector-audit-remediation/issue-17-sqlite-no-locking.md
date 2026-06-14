# Issue 17 — 12+ SQLite connections with check_same_thread=False, no locking

- **Severity:** CRITICAL · **Category:** Concurrency
- **Source (audit):** many modules — will corrupt or "database is locked"
- **Status:** 🟨 PARTIAL

## Issue (as reported)
12+ SQLite connections opened with `check_same_thread=False` and shared across
threads without serialization → corruption / "database is locked" under load.

## Status notes
- ✅ `core/memory/episodic.py` — `_write_lock` (RLock) serializes shared-conn
  ops in `get_temp_cursor` (production-hardening Task 07).
- ✅ `core/city/meta_cognition.py`, `core/memory/counterfactual.py`,
  `core/memory/causal_graph.py`, `districts/emergency/log.py`, and
  `districts/predictive_analytics/prediction_store.py` now use per-store
  locks with WAL/busy-timeout where applicable.
- ✅ `vectorcode/src/vc_agents/digest_store.py` and
  `vectorcode/src/vc_security/audit.py` now serialize shared SQLite access;
  audit hash-chain insert is atomic with `tail_hash()`.
- ✅ `vectorcode/src/vc_agents/manager.py` now serializes shared SQLite access
  for agent CRUD, status/tick updates, checkpoints, task CRUD, channel
  bindings, message queues, and learning logs; connection uses WAL +
  `busy_timeout`.
- 🟨 Remaining scope: repo still contains additional absorbed/optional
  `check_same_thread=False` users (for example telemetry/traces,
  connector stores, finagent/backtest stores). These need their own module-level
  triage before Issue 17 can be called fully closed.

## Analysis (to complete during analysis pass)
- Fix approach: shared per-module RLocks around shared connections plus WAL and
  busy timeout, or short-lived per-operation connections where that pattern
  already exists.
- Tests / Acceptance: `python -m pytest -q tests/backend/test_audit_followups.py`
  includes concurrent-write coverage for the core runtime stores, digest store,
  and security audit hash chain.
