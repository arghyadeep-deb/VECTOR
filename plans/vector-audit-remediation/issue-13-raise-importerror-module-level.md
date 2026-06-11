# Issue 13 — raise ImportError at module level

- **Severity:** HIGH · **Category:** Stability
- **Source (audit):** `apple_fm_shim.py:26` — crashes on non-macOS
- **Status:** ⬜ TODO

## Issue (as reported)
Module raises ImportError at top level on non-macOS platforms; any importer
crashes instead of degrading.

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/.../apple_fm_shim.py`
- Fix approach: _pending_ (guard platform check; expose a disabled-capability flag instead of raising)
- Tests / Acceptance: _pending_ (import succeeds on Windows/Linux)
