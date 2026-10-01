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

## 2026-10-01 — languages / startups / projects / predictive_analytics / memory_curator / home_assistant

1. **Stash hazard avoided.** Last round's subagents used `git stash` in the shared tree (index.lock,
   stray `sub/r.json`). This round they were forbidden from any git write and I proved fail-on-old myself
   with a throwaway `git worktree` at `HEAD`, copying each new test file in. Worktree removed afterwards.
2. **Subagents did not run fail-on-old themselves** (all six said "by reasoning from the diff"). Verified
   independently: languages 10/10 fail on old, memory_curator 6/6 (the agent predicted 5), startups 25/25,
   projects 20/20, predictive 21 fail + 1 skipped, home_assistant 22/24 runnable fail and the `connect()`
   test never returns on the old code (killed by `timeout`) — which is the bug being fixed.
3. **Command timeout.** A combined run that included the old-code `connect()` hang test exceeded the 120s
   tool limit and was backgrounded. Re-ran with `timeout` and the hanging tests deselected/isolated.
4. **Missing packages in the container** (not repo bugs): `ollama`, `fastapi`, `numpy`, `pyyaml`, `pytest`
   were absent; installed with pip (environment only). `GitPython` is still absent, so
   `tests/unit/test_permission_gateway_extra.py::TestOwnerReadonlyDispatchStatusHonesty` (3 tests:
   `git_status`/`recent_commits`) fail with `ModuleNotFoundError: git` — verified they fail **identically on
   the pre-change code**, so unrelated. `pandas` absent, so the Prophet-timestamp test is skipped here.
5. **Shared-tree guard test.** `tests/test_r18_eq_equation_capability.py::...only_expected_files_modified`
   fails whenever other uncommitted files exist (it allow-lists `git status`). It failed mid-audit because
   of in-flight subagent edits and passes on the clean tree — not a regression.
6. **Existing tests edited by a subagent.** The projects agent changed two `tests/test_phase2_districts.py`
   doc_writer tests. Reviewed: they asserted success while the LLM was mocked offline (encoding the bug);
   changed to mock a real reply, same intent. Called out in the commit message.
7. **Stop-hook fired repeatedly while subagents were still editing.** Only committed districts that had
   been reviewed and tested; never committed in-flight work.
8. **Reports overstated/understated slightly:** memory_curator predicted 5/6 failing-on-old (actual 6/6);
   projects/home_assistant counts were taken from the diff, not the report headline.

## 2026-10-01 — news_trends / growth / emergency / time_calendar / learning / data_analytics

1. **Partial unreviewed edits reached the remote via the auto-commit hook.** While the data_analytics
   subagent was still editing, the hook committed five mid-edit snapshots of
   `districts/data_analytics/data_engineer.py` (`6c2c9c83`, `56c64091`, `6b6ba40c`, `14f03887`,
   `44ae8f3a`); my subsequent pushes for other districts carried them to
   `claude/vector-audit-phase-3-continued-zdc5e9`. They were not reviewed/tested at that point. The final,
   verified version landed in `51daa617`, which supersedes them (net diff reviewed against baseline
   `d8eb4e7b`; all 22 new tests fail there, pass now). Root cause: the hook commits on every edit and
   shares the working tree with agents. Mitigation next round: tell agents to edit in a scratch copy, or
   accept that `auto:` snapshots are expected and always review the net diff against the pre-audit commit,
   not `HEAD`.
2. **Old-code baseline corrupted by the same hook.** My throwaway worktree was created at `HEAD`, which by
   then already contained those snapshots, so it was not a valid "old" for data_analytics. Re-pointed that
   directory to `d8eb4e7b` before comparing. (The data_analytics agent had independently noticed this and
   used a scratchpad plugin.) Other districts were unaffected (their files were still uncommitted at
   worktree creation).
3. **Shared test file edited by two agents.** `tests/test_phase3b_districts.py` was edited by the learning
   and news_trends agents concurrently. Split by hunk (`git apply --cached` of the learning hunk only) so
   no commit contained a test edit whose code wasn't in the same commit.
4. **Stray files from old-code runs.** Running the new news_trends tests against the pre-fix code created
   `02 Projects/` and `data/venture/` in the scratch worktree's CWD — the exact `venture_pipeline` bug
   being fixed. Contained to the throwaway worktree; main repo clean.
5. **Existing tests edited by subagents (all reviewed, all encoded the bug):**
   `tests/integration/test_spec07_emergency.py` (2 runbook tests asserted success for unsent
   notifications), `tests/test_phase3b_districts.py` (summarize_lecture; two TestAINewsBot tests asserting
   simulated/canned results). Each called out in its commit message.
6. **Environment gaps, not repo bugs:** `agno` missing →
   `tests/backend/test_audit_followups.py::test_issue_26_investment_runtime_stubs_fail_closed_without_notimplemented`;
   `soundfile`/`keyring` missing → `tests/test_growth_router.py::test_form_served_and_post_gated`;
   `TestTranscriptionBot` (calls district) needs network/LLM providers. None touched by these changes.
7. **Report wording:** news_trends headline said "17 bugs" but listed 22 numbered edits; counted from the
   diff. Several agents again did not run fail-on-old themselves (forbidden to use git writes); verified by
   me.
8. **Stop-hook fired again mid-run**; only reviewed/tested districts were committed.

## Unresolved

None blocking. Flagged-not-fixed design items are listed in `docs/OPEN_ISSUES.md` item 26.
