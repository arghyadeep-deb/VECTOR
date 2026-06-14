# Issue 19 — _SPAWNED_AGENTS dict not thread-safe

- **Severity:** HIGH · **Category:** Concurrency
- **Source (audit):** `agent_tools.py:32` — shared mutable dict, no lock
- **Status:** ✅ RESOLVED

## Issue (as reported)
A module-level `_SPAWNED_AGENTS` dict is mutated from concurrent spawn paths
without locking.

## Resolution
- Added `_SPAWNED_AGENTS_LOCK` and `get_spawned_agents_snapshot()`.
- Spawn/list/send/kill paths now lock around shared registry reads and writes.
- API routes now consume snapshots instead of iterating the mutable registry directly.

## Verification
- `python -m pytest -q tests/backend/test_audit_followups.py`
