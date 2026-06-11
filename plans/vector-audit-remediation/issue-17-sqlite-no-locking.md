# Issue 17 — 12+ SQLite connections with check_same_thread=False, no locking

- **Severity:** CRITICAL · **Category:** Concurrency
- **Source (audit):** many modules — will corrupt or "database is locked"
- **Status:** 🟨 PARTIAL

## Issue (as reported)
12+ SQLite connections opened with `check_same_thread=False` and shared across
threads without serialization → corruption / "database is locked" under load.

## Status notes
- ✅ `core/memory/episodic.py` — `_write_lock` (RLock) serializes shared-conn
  ops in `get_temp_cursor` (production-hardening Task 07). Re-verify.
- ⬜ The other 11+ connections — todo. Known offenders to confirm (from earlier
  audit): `core/brain/epistemic_tracker.py`, `core/brain/person_model.py`,
  `core/city/meta_cognition.py`, `core/memory/counterfactual.py`,
  `core/memory/causal_graph.py`, `core/persona/evolution.py`,
  `core/brain/suggestion_queue.py`, `districts/health/metrics_store.py`,
  `districts/emergency/log.py`, plus `core/memory/multi_db_manager.py`.

## Analysis (to complete during analysis pass)
- Fix approach: _pending_ (shared per-module write lock around cursor use; or WAL + short-lived connections; standardize a helper)
- Tests / Acceptance: _pending_ (concurrent-write test per offender, no "database is locked")
