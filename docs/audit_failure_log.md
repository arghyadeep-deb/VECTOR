# Audit failure log

Failures, blockers and process hiccups hit while running the Phase 3 whole-repo audit.
Bugs found in VECTOR itself are recorded in `docs/OPEN_ISSUES.md` item 26, not here.

## 2026-10-01 — communications / agency / design / karpathy_lab / interview_prep

1. **Auto-commit hook raced the manual commit.** The hook committed the item-26 edit as
   `d2bae2a4` before my own `git commit` ran, so that commit reported "nothing to commit". No data
   lost; pushed `d2bae2a4` instead.
2. **Command denied by the permission layer.** A combined `rm -rf sub && git add ... && git commit ...
   && git push` was denied. Re-ran the commit/push without the `rm -rf`, and removed the stray
   directory with a narrow `rm sub/r.json && rmdir sub`. Lesson: do not bundle `rm -rf` into a
   commit command.
3. **Stray `sub/r.json` in the repo root.** Created when subagents stashed their fixes to prove the
   new tests fail: the unfixed `ReportGenerator.export_report` wrote relative to the cwd (the very
   CWE-22 bug being fixed). Deleted; never committed. With the fix in place the same test writes inside
   the reports dir.
4. **`git stash` hit a transient `index.lock`** in the design subagent while other subagents ran git
   concurrently in the same working tree. Stash was re-applied and verified; no changes lost. Running
   5 agents in one checkout is workable only because their files are disjoint.
5. **pytest was not installed** in the container; the design subagent `pip install`ed it.
6. **Subagent report inconsistency.** The karpathy_lab report said "9 genuine bugs fixed" in its
   headline but listed 14 numbered fixes (and 17 tests). The diff matched the 14-item list; the
   headline was wrong. Counted from the diff, not the headline.
7. **Stop-hook fired mid-audit** while three subagents were still editing. Committed only the
   districts already reviewed and tested; did not commit unreviewed in-flight work.
8. **MCP servers unavailable** (`vector`, `vectorcode-intel` closed; `glif`, `NotFair-*` closed;
   `playwright` timed out). Not needed for this audit; no impact.

## Unresolved

None blocking. Flagged-not-fixed design items are listed in `docs/OPEN_ISSUES.md` item 26.
