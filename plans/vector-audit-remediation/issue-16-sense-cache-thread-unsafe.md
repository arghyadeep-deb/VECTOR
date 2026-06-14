# Issue 16 — Thread-unsafe _SENSE_CACHE dict

- **Severity:** HIGH · **Category:** Concurrency
- **Source (audit):** `context_engine.py:9` — data race in autonomous loop
- **Status:** ✅ RESOLVED

## Issue (as reported)
A module-level `_SENSE_CACHE` dict is read/written from multiple coroutines/
threads in the autonomous loop without locking → data race.

## Resolution
- Added `_SENSE_CACHE_LOCK` and `get_sense_cache_snapshot()`.
- Writes now take the lock; world-state reads use a stable snapshot.
- Kept `_SENSE_CACHE` as a dict for compatibility with existing integration tests.

## Verification
- `python -m pytest -q tests/backend/test_audit_followups.py`
