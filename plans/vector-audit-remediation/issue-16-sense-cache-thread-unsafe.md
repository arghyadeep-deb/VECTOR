# Issue 16 — Thread-unsafe _SENSE_CACHE dict

- **Severity:** HIGH · **Category:** Concurrency
- **Source (audit):** `context_engine.py:9` — data race in autonomous loop
- **Status:** ⬜ TODO

## Issue (as reported)
A module-level `_SENSE_CACHE` dict is read/written from multiple coroutines/
threads in the autonomous loop without locking → data race.

## Analysis (to complete during analysis pass)
- Affected files: `core/loop/context_engine.py`
- Fix approach: _pending_ (guard with a lock, or use an atomic snapshot/immutable swap)
- Tests / Acceptance: _pending_ (concurrent read/write test)
