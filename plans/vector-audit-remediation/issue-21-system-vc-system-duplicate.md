# Issue 21 — system/ vs vc_system/ divergent duplicates

- **Severity:** HIGH · **Category:** Architecture
- **Source (audit):** 7 files each, different code — which one runs?
- **Status:** ⬜ TODO

## Issue (as reported)
Two divergent directories (`system/` and `vc_system/`) hold ~7 files each with
different code; unclear which is actually imported at runtime.

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/system/*`, `vectorcode/src/vc_system/*`
- Fix approach: _pending_ (trace which is imported; delete/redirect the dead one to a shim; consolidate)
- Tests / Acceptance: _pending_ (only one canonical module path remains; importers green)
- Note: relates to Issues 03/04/05/22 (the offending tools may live in the dead copy)
