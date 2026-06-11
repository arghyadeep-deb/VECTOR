# Issue 12 — sys.exit(1) at module import

- **Severity:** CRITICAL · **Category:** Stability
- **Source (audit):** `nexa_shim.py:31` — kills entire VECTOR process
- **Status:** ⬜ TODO

## Issue (as reported)
A module calls `sys.exit(1)` at import time — importing it (e.g. via a registry
scan) kills the whole VECTOR process.

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/.../nexa_shim.py`
- Fix approach: _pending_ (never exit at import; raise a guarded ImportError or no-op + warn)
- Tests / Acceptance: _pending_ (import the module without process death)
