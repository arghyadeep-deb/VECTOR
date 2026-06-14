# Issue 15 — TimeoutError shadows builtin

- **Severity:** HIGH · **Category:** Stability
- **Source (audit):** `core/errors.py:56` — silent logic bomb in asyncio
- **Status:** ✅ RESOLVED

## Issue (as reported)
A custom `TimeoutError` shadows the builtin, so `except asyncio.TimeoutError` /
`except TimeoutError` elsewhere may not catch real timeouts → silent logic bomb.

## Resolution
- Renamed the custom VECTOR exception to `VectorTimeoutError`.
- Removed `TimeoutError` from `core.errors.__all__` so importing from `core.errors` no longer shadows the builtin by default.
- Grep found no local importers of `core.errors.TimeoutError`.

## Verification
- `python -m pytest -q tests/backend/test_audit_followups.py`
