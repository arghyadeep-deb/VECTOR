# Issue 21 — system/ vs vc_system/ divergent duplicates

- **Severity:** HIGH · **Category:** Architecture
- **Source (audit):** 7 files each, different code — which one runs?
- **Status:** ✅ RESOLVED

## Issue (as reported)
Two divergent directories (`system/` and `vc_system/`) hold ~7 files each with
different code; unclear which is actually imported at runtime.

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/system/*`, `vectorcode/src/vc_system/*`
- Canonical path: `vectorcode.src.vc_system`.
- Fix: legacy `vectorcode.src.system` modules now re-export canonical
  `vc_system` classes/functions instead of carrying divergent implementations.
- Tests / Acceptance:
  `test_system_legacy_package_reexports_canonical_vc_system` in
  `tests/backend/test_audit_followups.py`.
