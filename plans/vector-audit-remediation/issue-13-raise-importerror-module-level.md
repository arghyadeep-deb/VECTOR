# Issue 13 — raise ImportError at module level

- **Severity:** HIGH · **Category:** Stability
- **Source (audit):** `apple_fm_shim.py:26` — crashes on non-macOS
- **Status:** ✅ RESOLVED (2026-06-12)

## Issue (as reported)
Module raises ImportError at top level on non-macOS platforms; any importer
crashes instead of degrading.

## Resolution
- `vectorcode/src/vc_engine/apple_fm_shim.py` no longer raises `ImportError` at import time on non-macOS.
- The module imports successfully and reports unavailable via `/health` or 503 on completion calls.
- Regression: `tests/backend/test_audit_followups.py`.
