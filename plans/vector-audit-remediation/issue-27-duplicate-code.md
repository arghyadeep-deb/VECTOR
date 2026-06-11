# Issue 27 — Duplicate code

- **Severity:** mixed (SecurityBlockError = HIGH correctness; rest = maintainability) · **Category:** Architecture
- **Source (audit):** duplicate-code table
- **Status:** ⬜ TODO (per-pair triage below)

## Issue (as reported)
Multiple divergent duplicate modules; bug fixes land in only one copy, and one
pair causes a real `isinstance()` break.

| # | Duplicate pair | Files | Risk | Tracked / status |
|---|----------------|-------|------|------------------|
| 27a | `system/` ↔ `vc_system/` | all 7 | divergent — fixes miss one copy | → see [Issue 21](./issue-21-system-vc-system-duplicate.md) |
| 27b | `tools/` ↔ `vc_tools/` | 8+ | different import paths | → see [Issue 22](./issue-22-tools-vc-tools-duplicate.md) |
| 27c | `tools/storage/` ↔ `vc_tools/storage/` | `chunking.py`, `ingest.py` | divergent impls | sub-case of 22 — resolve with it |
| 27d | `telemetry/` (20 files) | all re-export shims | bare `core.*` imports fail off-path | relates to [Issue 09](./issue-09-broken-core-imports.md) — same root cause |
| 27e | **`SecurityBlockError`** | `boundary.py` + `guardrails.py` | **same name, different class → `isinstance()` breaks** | **NEW — HIGH (correctness bug, not cosmetic)** |
| 27f | `user_profile_manage.py` ↔ `memory_manage.py` | near-identical CRUD | should share a base class | NEW — MED |

## Analysis (to complete during analysis pass)
- **27e is the priority** — two distinct `SecurityBlockError` classes mean
  `except SecurityBlockError` / `isinstance(e, SecurityBlockError)` silently
  fails to catch the *other* one, so a security block can leak through. Fix:
  single canonical exception in one module, re-export from the other. Verify
  which raise/except sites use which.
- 27a/27b/27c: consolidate divergent dirs (trace the live copy, shim the dead
  one) — do BEFORE hardening the security tools (Issues 03/04/05) so we patch
  only what runs.
- 27d: telemetry shims — fix the bare `core.*` imports (Issue 09) or collapse
  the 20 shims.
- 27f: extract a shared CRUD base for the two `*_manage.py` modules.
- Tests / Acceptance: _pending_ per pair (esp. 27e: a test that
  `isinstance(raised, SecurityBlockError)` holds across both raise sites).
