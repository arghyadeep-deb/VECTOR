# Issue 19 — _SPAWNED_AGENTS dict not thread-safe

- **Severity:** HIGH · **Category:** Concurrency
- **Source (audit):** `agent_tools.py:32` — shared mutable dict, no lock
- **Status:** ⬜ TODO

## Issue (as reported)
A module-level `_SPAWNED_AGENTS` dict is mutated from concurrent spawn paths
without locking.

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/.../agent_tools.py`
- Fix approach: _pending_ (guard with a lock; or use a thread-safe registry like `core/city/agent_registry`)
- Tests / Acceptance: _pending_
