# Issue 11 — sqlite.py unreachable code (NameError)

- **Severity:** HIGH · **Category:** Stability
- **Source (audit):** `sqlite.py` — NameError after suppressed ImportError, crash on every instantiation
- **Status:** ⬜ TODO

## Issue (as reported)
A suppressed ImportError leaves a name undefined; later use raises NameError on
every instantiation (unreachable/dead recovery path).

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/.../sqlite.py`
- Fix approach: _pending_ (define a real fallback or fail clearly; remove dead code)
- Tests / Acceptance: _pending_
