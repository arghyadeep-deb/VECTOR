# Issue 22 — tools/ vs vc_tools/ divergent duplicates

- **Severity:** HIGH · **Category:** Architecture
- **Source (audit):** 8+ files with different import paths
- **Status:** ✅ RESOLVED

## Resolution (2026-06-14)
Verified every same-basename file across `vectorcode/src/tools/` and
`vectorcode/src/vc_tools/` (`__init__.py`, `_abc.py`, `knowledge_search.py`,
`knowledge_sql.py`, `scan_chunks.py`, `think.py`) — **all `tools/` copies are now
compatibility re-export shims** that import the canonical implementation from
`vc_tools`. No divergent logic remains. Files unique to `tools/` are distinct
legacy tools, not duplicates. Closed.


## Issue (as reported)
`tools/` and `vc_tools/` are divergent duplicates (8+ files) with different
import paths; unclear which is live.

## Analysis (to complete during analysis pass)
- Affected files: `vectorcode/src/tools/*`, `vectorcode/src/vc_tools/*`
- Canonical path for shared agent tools/storage: `vectorcode.src.vc_tools`.
- Fixed in this pass:
  - `vectorcode/src/tools/storage/_abc.py` now re-exports canonical backend
    types.
  - `vectorcode/src/tools/storage/chunking.py` adapts canonical chunking while
    preserving legacy `list[str]` return shape.
  - `vectorcode/src/tools/storage/ingest.py` delegates to canonical ingestion
    instead of returning `0`.
  - Added missing legacy shims for `tools.storage.__init__`,
    `tools.storage.sqlite`, and `tools.storage.context`.
- Remaining: the broad `vectorcode/src/tools/` package contains many legacy and
  non-duplicate tool implementations. Only the storage duplicate cluster is
  consolidated here.
- Tests / Acceptance:
  `test_tools_storage_legacy_adapters_use_canonical_implementations` in
  `tests/backend/test_audit_followups.py`.
