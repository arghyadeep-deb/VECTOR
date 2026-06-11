# Issue 22 — tools/ vs vc_tools/ divergent duplicates

- **Severity:** HIGH · **Category:** Architecture
- **Source (audit):** 8+ files with different import paths
- **Status:** ⬜ TODO

## Issue (as reported)
`tools/` and `vc_tools/` are divergent duplicates (8+ files) with different
import paths; unclear which is live.

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/tools/*`, `vectorcode/src/vc_tools/*`
- Fix approach: _pending_ (determine canonical, shim/delete the other, fix importers)
- Tests / Acceptance: _pending_
- Note: Issues 03/04/05 reference both `tools/` and `vc_tools/` — resolve this
  first so we harden only the live copy.
