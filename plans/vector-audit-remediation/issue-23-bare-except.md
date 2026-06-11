# Issue 23 — 544 bare `except Exception`

- **Severity:** HIGH · **Category:** Architecture / Maintainability
- **Source (audit):** repo-wide — swallows every error, debugging impossible
- **Status:** ⬜ TODO

## Issue (as reported)
~544 broad `except Exception` (often silent) swallow errors and make failures
invisible.

## Analysis (to complete during analysis pass)
- Scope: repo-wide; not all are wrong (resilience loops intentionally catch).
- Fix approach: _pending_ (triage — keep intentional ones but ensure they log at
  warning+; tighten the rest to specific exceptions; prioritize core decision/
  memory/gateway paths). This is a large, incremental task — likely its own
  sub-plan, not a single change.
- Tests / Acceptance: _pending_
