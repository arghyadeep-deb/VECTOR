---
name: vector-change-control
description: Load when changing VECTOR code — classifying a change, deciding what needs gating/review, or before deleting/refactoring anything. The project's non-negotiable rules with the incident behind each. Triggers: "is it safe to change", "can I delete", "commit", "refactor", "before merging", "change control".
---

# VECTOR Change Control

Runbook for a mid-level engineer or Sonnet-class model making changes to VECTOR
without breaking it. Every rule here has a real incident behind it. Ground
truth as of 2026-07-07. Verify anything marked (verify) before relying on it.

## When NOT to use this skill
Skip for pure read/analysis tasks. For *how to debug* a failure use
`vector-debugging-playbook`; for *why* an architecture rule exists use
`vector-architecture-contract`.

## The non-negotiables (break these = real damage)

### 1. Never rename/drop the 5 sacred memory tables
`episodic_memory`, `semantic_memory`, `policy_memory`, `reasoning_chains`,
`agent_history`. Adding columns is fine; renaming/dropping is a CRITICAL
violation. See `.claude/rules/memory.md`. Incident: memory schema is load-bearing
for the whole Darwinian HP/ghost system.

### 2. The main DB is SQLCipher-encrypted — never open it with plain sqlite3
Go through `core.memory.episodic.get_db_connection()` /
`close_db_connection()`. Incident (2026-06-11): 5 modules opened the encrypted
DB with plain `sqlite3`, and a whole FAMILY of driver-class bugs followed —
SQLCipher's `IntegrityError`/`ProgrammingError`/`Row` are NOT subclasses of
`sqlite3`'s, so `except sqlite3.X` silently missed them; one playbook renamed
the live DB. If you catch DB exceptions, catch the SQLCipher driver's classes.

### 3. FTS5 DELETE only tombstones — to shrink you must DROP+CREATE
Incident (2026-06-29): the DB ballooned 2.3GB→131MB. Root cause was NOT
retention — `context_budget.py` was dumping 56KB prompt offloads into the
FTS-indexed `episodic_memory` (write-only dead weight). `DELETE` left the FTS
index full; only `DROP TABLE` + recreate actually reclaimed space.

### 4. Windows console is cp1252 — non-ASCII prints crash
Incident (2026-06-29): emoji/arrow characters in `print()` raised
`UnicodeEncodeError` and crashed 246 call sites. Fixed at `core/__init__` +
bootstrap + a 41-file codemod. RULE: any script that prints non-ASCII must
`sys.stdout.reconfigure(encoding="utf-8", errors="replace")` at the top (or run
with `PYTHONUTF8=1`). Prefer ASCII (`->` not `→`) in new prints.

### 5. Import order: torchvision BEFORE openwakeword (and similar)
Incident (2026-07-03): `openwakeword.train` pulls torchmetrics→torchvision,
whose `register_fake` frame-walk detonates speechbrain's broken lazy imports
under torch 2.11. Import `torchvision` first so its meta-registration completes
cleanly. General lesson: heavy ML deps have load-order landmines — reproduce
imports in isolation when a training/inference import crashes weirdly.

### 6. Commit discipline
- Auto-commit hook = PostToolUse on Edit/Write ONLY. Bash-based file writes
  bypass it — commit those manually.
- NEVER add `Co-Authored-By: Claude` trailers (repo is public, owner wants sole
  attribution; 107 existing trailers were already stripped from history).
- Default branch is `production-hardening-complete` (not `main`).
- Commit messages: `auto: [module]` for hook commits; descriptive for manual.

### 7. Wire, don't delete (dead-code discipline)
Never delete code on reachability alone. WIRE useful-but-disconnected code;
delete only genuinely-dead code, LAST, after all features work + owner sign-off.
Incident basis: repeated audits found "dead" code that was actually
unwired-but-valuable (absorbed OSS). Exception: when the owner explicitly signs
off on deleting a specific thing (e.g. paid video backends 2026-07-04), do it
cleanly — rewire every dependent first, then delete.

## Change classification (what needs gating)
| Change type | Gate |
|---|---|
| Read-only / analysis | none |
| Config/flag flip | note it; owner decides behavior-changing ones |
| New feature / district | brainstorming → writing-plans → executing (per CLAUDE.md) |
| Anything touching permission_gateway / memory tables / HP system | do NOT mock in tests; test the real thing (`.claude/rules/testing.md`) |
| RED-tier actions (send_email, payments, deploy, delete_files) | owner approval via permission_gateway — never bypass |
| Deleting/refactoring | wire-don't-delete + sign-off (rule 7) |

## Before you claim "done"
Run the evidence gate (see `vector-validation-and-qa`): `python
scripts/smoke_test.py` (expect 38/38) + `python scripts/integration_check.py`
(expect 51/51) + relevant pytest. Never assert success without running the check.

## Provenance and maintenance
- Facts dated 2026-07-07 from project memory (`~/.claude/projects/.../memory/`)
  and `.claude/rules/*`. Re-verify:
  - Sacred tables: `grep -n "Never Rename" .claude/rules/memory.md`
  - Smoke/integration counts: `python scripts/smoke_test.py | tail -2`
  - Default branch: `git rev-parse --abbrev-ref HEAD`
- If an incident here no longer reproduces, mark it RESOLVED here rather than deleting.
