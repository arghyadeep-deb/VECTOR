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

## 2026-10-01 — skills/reflection/personal_growth/chief_of_staff/calls/relationships/privacy/pattern_detective/legal_compliance/self_dev/science

1. **Non-discriminating tests passed on the pre-fix code (found by the new "PASSED-on-old" check).**
   Every agent claimed its tests fail on old code, but none could run it (git writes forbidden). I added a
   baseline check (`oldcheck.sh`: copy the new test file into a worktree at `66c9c9bc`, list tests that
   still PASS) and read every suspect:
   - **legal_compliance** — two tests passed on old for an unrelated reason (evidence rejected elsewhere /
     an empty `prohibited_clauses` list made the evidence incomplete). Probed the old code with the exact
     intended inputs (string `prohibited_phrases`, string `required_clauses` → `passed: True`), confirming
     the bug was real, then rewrote both tests to change ONE field of the valid example evidence and assert
     the new check by name. Now fail on old.
   - **calls** — three tests (`empty_transcription`, `blank_audio_path`, `tts_output_path_confined`) passed
     on old ONLY because `whisper`/`kokoro_onnx` are not installed here and the old code did a needless
     `import whisper` / `import kokoro_onnx` that errored first — masking the bug. Rewrote with fixtures
     injecting fake `whisper`, `kokoro_onnx` and `scipy.io.wavfile` modules so the old logic runs (a fake
     `wavfile.write` really creates the file, making the unconfined write observable). Now fail on old.
   - **Accepted as legitimate controls:** `test_route_policy_goes_local_for_these_kwargs` (core routing),
     `test_cad_valid_still_ok`, `test_valid_examples_still_pass`, `test_clean_agent_passes_exec_check`,
     reflection `test_run_params_none_is_safe` (agent disclosed it), physics params 4/5 (pendulum length 0
     / -1 — old engine already rejected; the other six cases fail on old).
   - **skills** `test_gap_run_params_none` passes on old: the agent's claim "params None crashed
     gap_analyst" was overstated — the old `AttributeError` was caught by the surrounding `try` and also
     returned `error`. Kept as a regression guard, not counted as a bug.
2. **Shared tests edited by several agents again** — split by owner, each committed with its district:
   `test_calls_run_wiring.py` + `test_phase3b_districts.py` (VoiceResponder) → calls;
   `test_phase3a_districts.py` (CommunicationAnalyst) → relationships; `test_phase2_districts.py` (four
   `*_llm_unavailable` tests that asserted `ok is True` during an outage) → reflection. All encoded the bug.
3. **Scratch-dir collision.** The relationships agent put its own "old" copy in the same
   `scratchpad/old` my baseline worktree used. Checked `git status` of the worktree afterwards: only my
   copied test files were untracked, no sources overwritten.
4. **Baseline = the pre-audit commit, not HEAD** (lesson from the data_analytics `auto:` snapshots last
   round): all comparisons this round used `66c9c9bc`. No mid-edit `auto:` snapshot reached the remote
   this round — every committed district was reviewed first.
5. **Core defects that block fixes inside districts** (core/ is out of scope): `recall()` hides read
   errors; `chat()` fails open if `route_policy` raises; `_is_local` substring matching; narrow secret
   markers. Four districts worked around the first by reporting `no_data`; the privacy/calls leaks were
   fixed at the call sites (`district`/`sensitive`/`allow_cloud`) rather than by adding `calls` to
   `route_policy._SENSITIVE_DISTRICTS`, which would be the more robust fix.
6. **Report accuracy:** several headline counts differed from the numbered lists (chief_of_staff "10" vs 12
   items, relationships/pattern_detective 13+17 with 11 groups); counted from diffs. The self_dev agent
   did not read the permission gateway ("nothing to gate") — verified independently by search that the
   baseline has no write/subprocess/git/network primitives (only a denylist of method names).
7. **Stop-hook fired mid-run**; only reviewed/tested districts were committed.

## 2026-10-01 — core/trading (agents, dataflows+crypto, graph+llm_clients, cli+package tests)

1. **The absorbed package had never been run inside VECTOR.** `core/trading/cli` could not be imported
   (stale `from cli.models import …`) and three of the package's own test files failed at collection /
   errored (`test_api_key_env`, `test_ollama_base_url`, `test_ticker_symbol_handling`). The dataflows agent
   had to `--deselect` two of them ("No module named 'cli'") until the CLI agent's import-path fix landed.
   Import-path-only edits to those tests (reviewed) — no assertion changed.
2. **A broken baseline hides behaviour bugs.** Because the old CLI cannot import, *every* new CLI test fails
   on the pre-fix tree for that one reason, which proves nothing about the other fixes. To isolate them I
   patched only the import paths in the throwaway baseline worktree and re-ran: 10 behaviour tests then
   fail on old for their real reasons; the 5 that pass are the import test (by construction), a happy-path
   control, an empty-literals control and two deeply-nested `literal_eval` cases that only guard newer
   Pythons (disclosed by the agent).
3. **Auto-commit hook snapshotted a test file mid-edit** (`a6c9f09d auto: test_audit_phase3_trading_cli.py`
   — a new test file only; no source). Reviewed and re-verified before the final CLI commit; no
   unreviewed source reached the remote this round.
4. **Independent verification of the headline claim.** The graph agent's "checkpoint resume re-ran every
   completed node" is a claim about LangGraph semantics; reproduced it myself on a toy graph with
   `MemorySaver` (old: calls `['a','b','a','b']`, 2 human messages; `invoke(None)`: `['a','b','b']`, 1).
   Likewise confirmed `invoke_structured_or_freetext` catches the new pydantic `ValidationError` (the agent
   admitted it had not checked), so the stricter schema degrades to free text instead of crashing.
5. **Environment (not repo) changes:** agents `pip install`ed pandas, yfinance, stockstats, requests,
   python-dateutil, loguru (dataflows) and typer, questionary, rich, langchain-core/openai/anthropic/
   google-genai, langgraph, langgraph-checkpoint-sqlite (cli). `requirements.txt` untouched. If CI lacks
   these, `core/trading/tests` will not collect there.
6. **Tool-output blow-up:** one parametrized test ID is a ~10k-character string of nested parentheses; it
   flooded my result listing (saved to a tool-results file). Re-read results with names truncated.
7. **Report accuracy:** the dataflows agent's "29 tests, 5 pass on old" matched my run exactly (24 fail on
   old; the 5 passes are happy-path controls plus an existing CWE-22 guard). The agents agent's schema
   fix is Buy-only by design (Sell stop side is ambiguous) — flagged, not guessed.
8. **Stop-hook fired twice mid-run**; only reviewed/tested areas were committed, in the order each agent
   finished.

## 2026-10-01 — core/mcp_tools (3 areas) + core/scraper (4 areas)

1. **Test seam missing in the OLD code made "fail-on-old" unreliable (two separate ways).** The old
   `expansion_modules/*` compute `ROOT` as a local inside `add_*_tools` from `__file__`, so a test cannot
   redirect it; the new code adds a module-level `_ROOT` for testing.
   - **expansion A:** three tests passed on old (`file_read` sibling-prefix, `security_path_check` sibling-prefix,
     real-repo dash-ref checkout) because the old root was the real repo and the `../repo-evil` path simply
     landed outside it — denied for the wrong reason. Bug proven instead from the baseline SOURCE
     (`str(resolved).startswith(str(ROOT.resolve()))` at old `files.py:34` / `security.py:64`). My direct
     execution demo of the old tools failed on a baseline-worktree `core.config` import-order problem and was
     abandoned in favour of the source evidence; the NEW tools were demonstrated to deny the sibling.
   - **expansion B:** on the unmodified baseline 83 of 102 tests ERRORed at fixture setup
     (`monkeypatch.setattr(mod, "_ROOT", …)` AttributeError), i.e. they never reached the logic. Re-ran with a
     bare `_ROOT` attribute shimmed onto the six old modules (logic untouched) and `pytest-timeout=20s`:
     **98 FAILED / 0 ERROR / 4 PASSED**; the 4 passes are `doc_*` tests with the same redirect limitation;
     old `doc_move/doc_copy` (no containment) and `doc_delete` (`startswith` then `unlink`) confirmed from source.
2. **My own check script mis-parsed results twice.** It counted captured log lines starting with `ERROR` as test
   errors (browsers showed "4 ERROR" while all 81 tests passed) — fixed to match `ERROR tests/…` only. An earlier
   run of the expansion-B old-code check hit my 110s limit (old `perf_stress`/`perf_load` are unbounded) and
   printed zeros; re-ran with a hard per-test timeout so a hang counts as a failure.
3. **Scratch-dir collision again.** A subagent had already used `scratchpad/old` as a plain directory, so my
   `git worktree add …/old` failed ("already exists") and an `oldcheck` run silently found no worktree. Moved
   the baseline to `scratchpad/base`. The old-code runs of expansion B can write/delete real files in the
   baseline worktree (`doc_delete`, `test_create`, `doc_copy`) — restored with `git checkout -- .` +
   `git clean` after each run; the main repo was verified clean.
4. **Auto-commit hook snapshots again** touched only test files this round
   (`291a0d94 auto: test_audit_phase3_scraper_browsers.py`, `a6c9f09d`-style), never source; every source
   change was reviewed before its commit. The three previous baselines were therefore still valid for
   `core/mcp_tools` and `core/scraper` (no source commits since `9089265a`).
5. **Environment (not repo) changes:** agents `pip install`ed cssselect, lxml, orjson, w3lib, tldextract
   (parser), protego, tld, browserforge, msgspec, patchright, playwright, curl_cffi, click, ipython,
   markdownify (spiders); I installed `pytest-timeout`. `requirements.txt` untouched.
6. **Pre-existing failures verified unrelated:** `tests/test_mcp_server_main_dispatch_fix.py` (2 tests) runs
   `python core/mcp_server.py` as a subprocess and fails `ModuleNotFoundError: No module named 'core'` on the
   UNMODIFIED baseline too (no PYTHONPATH); `core/scraper/vector_scraper.py` cannot be run as a script
   (`sys.path[0]` makes `core` resolve to `core/scraper/core`).
7. **Agent report accuracy:** several agents said they "could not run fail-on-old" (git writes forbidden / `rm`
   denied); all verified by me. The spiders agent's pickle-checkpoint change and the browsers agent's
   `--no-sandbox` rejection are behaviour changes, called out in item 26. Agents correctly refrained from
   editing `core/security/ssrf_guard.py` (documented owner decision) and from inventing MCP tier policy.
8. **Stop-hook fired repeatedly mid-run**; only reviewed/tested areas were committed, in completion order.

## Unresolved

None blocking. Flagged-not-fixed design items are listed in `docs/OPEN_ISSUES.md` item 26.
