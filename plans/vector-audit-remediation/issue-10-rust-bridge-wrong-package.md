# Issue 10 — vector._rust_bridge wrong package

- **Severity:** HIGH · **Category:** Stability
- **Source (audit):** `shell_exec.py:139`, `sqlite.py:46` — always fails
- **Status:** ⬜ TODO

## Issue (as reported)
Imports `vector._rust_bridge` (wrong package name) — the import always fails.

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/.../shell_exec.py`, `.../sqlite.py`
- Fix approach: _pending_ (correct package path or guard + Python fallback)
- Tests / Acceptance: _pending_
