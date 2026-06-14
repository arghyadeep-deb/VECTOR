# Issue 10 — vector._rust_bridge wrong package

- **Severity:** HIGH · **Category:** Stability
- **Source (audit):** `shell_exec.py:139`, `sqlite.py:46` — always fails
- **Status:** ✅ RESOLVED

## Issue (as reported)
Imports `vector._rust_bridge` (wrong package name) — the import always fails.

## Resolution
- Corrected Rust bridge imports from `vector._rust_bridge` to `vectorcode.src._rust_bridge`.
- Added regression coverage in `tests/backend/test_audit_followups.py`.

## Verification
- `python -m pytest -q tests/backend/test_audit_followups.py`
