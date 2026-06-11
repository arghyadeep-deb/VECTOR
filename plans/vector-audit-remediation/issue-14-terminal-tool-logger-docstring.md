# Issue 14 — terminal_tool logger NameError

- **Severity:** HIGH · **Category:** Stability
- **Source (audit):** `terminal_tool.py` — logger referenced in docstring/scope, NameError at runtime for any `logger.xxx()` call
- **Status:** ⬜ TODO

## Issue (as reported)
`logger` is not actually imported/bound (only appears in a docstring), so any
`logger.xxx()` call raises NameError at runtime.

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/.../terminal_tool.py` (same file as Issue 06 SUDO_PASSWORD)
- Fix approach: _pending_ (add `from loguru import logger`)
- Tests / Acceptance: _pending_
