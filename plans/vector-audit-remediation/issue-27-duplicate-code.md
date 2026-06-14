# Issue 27 — Duplicate code

- **Severity:** mixed (SecurityBlockError = HIGH correctness; rest = maintainability) · **Category:** Architecture
- **Source (audit):** duplicate-code table
- **Status:** 🟨 PARTIAL (system/storage/digest/27e fixed; broader tools remain)

## Issue (as reported)
Multiple divergent duplicate modules; bug fixes land in only one copy, and one
pair causes a real `isinstance()` break.

| # | Duplicate pair | Files | Risk | Tracked / status |
|---|----------------|-------|------|------------------|
| 27a | `system/` ↔ `vc_system/` | all 7 | divergent — fixes miss one copy | ✅ fixed via legacy `system` shims |
| 27b | `tools/` ↔ `vc_tools/` | 8+ | different import paths | 🟨 partial — see [Issue 22](./issue-22-tools-vc-tools-duplicate.md) |
| 27c | `tools/storage/` ↔ `vc_tools/storage/` | `chunking.py`, `ingest.py` | divergent impls | ✅ fixed via storage compatibility adapters |
| 27d | `telemetry/` (20 files) | all re-export shims | bare `core.*` imports fail off-path | relates to [Issue 09](./issue-09-broken-core-imports.md) — same root cause |
| 27e | **`SecurityBlockError`** | `boundary.py` + `guardrails.py` | **same name, different class → `isinstance()` breaks** | ✅ fixed: `boundary.py` imports canonical guardrails error |
| 27f | `user_profile_manage.py` ↔ `memory_manage.py` | near-identical CRUD | should share a base class | ✅ fixed: both now subclass `vc_tools/_markdown_store.py:MarkdownStoreTool`; CRUD lives only on the base (test-enforced) |
| 27g | `agents/digest_store.py` ↔ `vc_agents/digest_store.py` | duplicate SQLite store | CLI/server could drift | ✅ collapsed legacy path to canonical `vc_agents` shim |

## Analysis (to complete during analysis pass)
- ✅ **27e fixed** — two distinct `SecurityBlockError` classes meant
  `except SecurityBlockError` / `isinstance(e, SecurityBlockError)` silently
  failed to catch the *other* one. `boundary.py` now uses the canonical class
  from `guardrails.py`; test verifies class identity.
- ✅ `agents/digest_store.py` now re-exports `vc_agents.digest_store`, so CLI
  imports use the hardened canonical implementation.
- ✅ legacy `system/*` modules now re-export canonical `vc_system/*`.
- ✅ legacy `tools/storage/*` modules now use canonical `vc_tools/storage/*`
  while preserving old compatibility shapes where needed.
- 27a/27b/27c: consolidate divergent dirs (trace the live copy, shim the dead
  one) — do BEFORE hardening the security tools (Issues 03/04/05) so we patch
  only what runs.
- 27d: telemetry shims — fix the bare `core.*` imports (Issue 09) or collapse
  the 20 shims.
- 27f: extract a shared CRUD base for the two `*_manage.py` modules.
- Tests / Acceptance: `python -m pytest -q tests/backend/test_audit_followups.py`
  covers `SecurityBlockError` class identity and digest-store compatibility.
