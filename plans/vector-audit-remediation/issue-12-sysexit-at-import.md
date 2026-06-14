# Issue 12 — sys.exit(1) at module import

- **Severity:** CRITICAL · **Category:** Stability
- **Source (audit):** `nexa_shim.py:31` — kills entire VECTOR process
- **Status:** ✅ RESOLVED (2026-06-12)

## Issue (as reported)
A module calls `sys.exit(1)` at import time — importing it (e.g. via a registry
scan) kills the whole VECTOR process.

## Resolution
- `vectorcode/src/vc_engine/nexa_shim.py` no longer calls `sys.exit(1)` when `nexaai` is missing.
- The module imports successfully and reports unavailable at request/health time.
- Regression: `tests/backend/test_audit_followups.py`.
