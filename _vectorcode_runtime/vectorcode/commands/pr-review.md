<!-- VECTOR-INGESTED ASSET
  Source: .claude/commands/pr-review.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

---
name: pr-review
description: Full PR review against VECTOR standards before merge.
argument-hint: "[pr-number-or-branch]"
---

Review PR $ARGUMENTS against VECTOR standards:

**Step 1 — Read changes**
`gh pr diff $ARGUMENTS` or `git diff main...HEAD` — every changed file

**Step 2 — Rules check (block if violated)**
- [ ] No `.env` or credentials in diff
- [ ] No `VectorCode API (local Ollama)` called at runtime (Rule 11)
- [ ] No direct LLM access — all through `permission_gateway.py` (Rule 3)
- [ ] `run_forever()` loops have exception handlers (Rule 2)
- [ ] `session_hydration_prompt()` present in every new LLM call (Rule 1)
- [ ] Memory schema table names unchanged (Rule 8)

**Step 3 — Code quality**
- [ ] loguru used, no bare `print()` in production paths
- [ ] All configurable values in `core/config.py`, no hardcoded paths/keys
- [ ] Functions under 60 lines, no duplication
- [ ] `if __name__ == "__main__"` block present in new Python files

**Step 4 — HP + Darwin system**
- Any new agent? → HP wired to task outcomes, ghost memory on death
- Any district changes? → Registered with Mayor's Office

**Step 5 — Report**
Format: CRITICAL (block merge) / WARNING (fix preferred) / SUGGESTION (optional)
Merge only if zero CRITICALs.
