# Issue 11 — sqlite.py unreachable code (NameError)

- **Severity:** HIGH · **Category:** Stability
- **Source (audit):** `sqlite.py` — NameError after suppressed ImportError, crash on every instantiation
- **Status:** ✅ RESOLVED

## Issue (as reported)
A suppressed ImportError leaves a name undefined; later use raises NameError on
every instantiation (unreachable/dead recovery path).

## Resolution
- `SQLiteMemory` now attempts the Rust backend first and falls back to a working Python SQLite/FTS5 implementation if the bridge is unavailable.
- The fallback creates tables, stores/retrieves/deletes/clears/counts documents, and serializes DB access with an `RLock`.

## Verification
- `python -m pytest -q tests/backend/test_audit_followups.py`
