# Issue 15 — TimeoutError shadows builtin

- **Severity:** HIGH · **Category:** Stability
- **Source (audit):** `core/errors.py:56` — silent logic bomb in asyncio
- **Status:** ⬜ TODO

## Issue (as reported)
A custom `TimeoutError` shadows the builtin, so `except asyncio.TimeoutError` /
`except TimeoutError` elsewhere may not catch real timeouts → silent logic bomb.

## Analysis (to complete during analysis pass)
- Affected files: `core/errors.py` (+ grep importers that may rely on the name)
- Fix approach: _pending_ (rename custom exception, e.g. `VectorTimeoutError`; fix importers)
- Tests / Acceptance: _pending_ (asyncio.timeout still caught where expected)
