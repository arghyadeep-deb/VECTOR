<!-- VECTOR-INGESTED ASSET
  Source: .claude/commands/fix-issue.md
  Personalized for VECTOR City / VectorCode runtime.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T00:45:56+00:00
-->

---
name: fix-issue
description: Read a GitHub issue, implement the minimal fix, write a test, commit.
argument-hint: "[issue-number]"
---

Fix GitHub issue #$ARGUMENTS:

1. `gh issue view $ARGUMENTS` — read the full issue, understand the exact failure
2. Find the relevant source file(s) — trace from the error message or feature description
3. Read `rules/critical_rules.md` — confirm the fix does not violate any of the 12 rules
4. Implement the **minimal** fix — no refactoring, no feature creep
5. Write a regression test in `tests/` that would have caught this issue
6. Run `pytest tests/ -x -q` — all green before committing
7. Commit: `fix: [module] description (closes #$ARGUMENTS)`

If the fix requires touching the permission gateway, autonomous loop, or memory schema — stop and flag it. Those changes need the district builder workflow, not this command.
