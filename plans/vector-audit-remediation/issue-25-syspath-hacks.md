# Issue 25 — sys.path.insert hacks

- **Severity:** MEDIUM · **Category:** Architecture
- **Source (audit):** 3+ instances — breaks virtualenv isolation
- **Status:** ⬜ TODO

## Issue (as reported)
`sys.path.insert(0, ...)` hacks (3+ instances) break virtualenv isolation and
cause the import fragility behind Issue 09.

## Analysis (to complete during analysis pass)
- Affected files: enumerate the `sys.path.insert` sites (note: prior
  `phase_status.md` deferred 16 such calls in districts/vectorcode as
  "legitimate runtime uses" — re-evaluate the 3+ the audit flags).
- Fix approach: _pending_ (proper packaging / editable install so paths resolve
  without manipulation; remove unnecessary inserts)
- Tests / Acceptance: _pending_
