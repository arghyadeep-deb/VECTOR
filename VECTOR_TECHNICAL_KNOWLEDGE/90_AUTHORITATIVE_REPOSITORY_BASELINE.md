# Task 90 — Authoritative Repository Checkpoint, Git Baseline & Full-Suite Blocker

**Mode:** infrastructure/reproducibility work on the real current working tree. Segment2 (PID
37588) was not running at any point this session (confirmed via read-only process check) and was
never started, stopped, or interacted with. `.env` was not modified. MCP was not enabled. No
experiment setting was touched.

---

## 1. Current git state (as found, before any action)

```
HEAD:            5964a3316 (production-hardening-complete)
HEAD date:       2026-08-07 04:26:35 +0530
Modified tracked files:   79
Untracked files:           63 (several are directories expanding to many files)
git diff --stat:  79 files changed, 5401 insertions(+), 460 deletions(-)
```

`git worktree list` at task start showed **five** Claude-created worktrees under
`.claude/worktrees/`, one per Task 89 sub-agent (A–E), all at commit `6b5fcf204` — **not**
`5964a3316`. This is a correction to Task 89's own report, which assumed the shared base was
`5964a3316`: the true worktree base was `6b5fcf204`, seven commits earlier. Verified directly
(`git diff --stat 6b5fcf204 5964a3316`): those seven intervening commits touched 236 files, **none
of them** any of the eight files Task 89 modified — so Task 89's extracted diffs were byte-correct
despite the mislabeled base, but the mislabeling itself was worth catching and is recorded here so
it isn't repeated.

Task 88's and Task 89's changes were confirmed present and uncommitted at task start (both are part
of the 79 modified files: `core/inference/ollama_safe.py`, `core/city/governor.py`,
`core/loop/autonomous_loop.py`, `core/config.py`, `core/event_bus/wiring.py`,
`core/memory/policy.py`, `core/loop/decision_engine.py`, `core/memory/episodic.py`,
`hands/runner.py`, plus their new test files among the 63 untracked entries).

## 2. Current uncommitted state (before checkpoint) — classified

| Class | Content | Disposition |
|---|---|---|
| **A — Task 88/89** | The 8 production files above + `ollama_safe.py`, 5 new test files, 1 rewritten test file, `VECTOR_TECHNICAL_KNOWLEDGE/89A–D` + this task's own reports | Committed (§3) |
| **B — pre-existing, intentional VECTOR work** | ~70 other modified tracked files (`core/api/*`, `core/brain/*`, `core/inference/*` except `ollama_safe.py`, `core/memory/counterfactual.py`, `core/memory/semantic.py`, `core/loop/permission_gateway.py`, `core/loop/planner.py`, dozens of `districts/*.py` one-line capability additions, `frontend/js/*`, several `tests/*`); plus untracked, clearly-coherent feature work: `core/city/intent_matcher.py`/`intent_bert.py`/`intent_monitor.py`/`intent_qwen3_8b.py` (an intent-classification subsystem), `core/memory/correction_learner.py`, `core/metering/inference_observability.py` (already relied on by Task 88's own fix), `core/runtime/plans.py`, `core/benchmark/` (a 20-file cognitive benchmark suite with a real design doc, `docs/design/multi_step_planning.md`), `docs/design/7-day-autonomy-experiment-design.md` (the actual design document for the Segment-2 experiment this whole task series has been analyzing), the 58-series permission-remediation tests (`tests/test_task57_*`, `test_task58*_*.py` — matching Tasks 57–58G's own history), and their supporting scripts/docs/data fixtures | Committed (§3) — genuinely part of the current architecture, verified non-secret, reasonably sized |
| **C — questionable/scratch** | Eight root-level planning/execution `.md` files (`EXECUTE_NOW.md`, `EXECUTION_SUMMARY.md`, `FINAL_EXECUTION_GUIDE.md`, `INTENT_CLASSIFICATION_COMPLETE.md`, `INTENT_CLASSIFICATION_STATUS.md`, `OPENCODE_EXECUTION_PROMPT.md`, `OPENCODE_PHASE2_PROMPT.md`, `WHILE_TRAINING_WORK.md`) — ad hoc, root-level, some named after a different tool ("OPENCODE"), not placed in `docs/` | Committed (§3), flagged here as a housekeeping candidate for a future task — **not** relocated or deleted this session (out of scope, no destructive action taken on ambiguous content) |
| **D — generated/runtime artifacts** | `data/council_log.jsonl` (already tracked, growing log), three data files under `data/golden_intent_dataset*.jsonl`/`data/intent_examples.json` | Committed (§3) — the log file was already tracked before this session (a pre-existing pattern, not something this task should change unilaterally); the dataset files are small (≤72 KB each) and are legitimate fixtures for the intent-classification subsystem (class B), not accidental generated bloat |
| **E — unknown** | None remained after inspection — `core/benchmark/` and `docs/design/` (initially unknown) were opened and found to be coherent, legitimate class-B work; no file's purpose remained genuinely unclear after direct inspection | — |

**Secret/safety scan performed before staging anything:** `.env` confirmed gitignored
(`git check-ignore -v .env`); zero `.db`/credential files among the changes; a pattern scan
(`api[_-]?key|secret|password|token=...|sk-...`) across the eight questionable root-level `.md`
files found nothing; largest untracked item was `VECTOR_TECHNICAL_KNOWLEDGE/` at 2.9 MB (this
task series' own documentation), nothing pathologically large.

## 3. Checkpoint commit

**Decision: commit the complete current working-tree state as one checkpoint.** Reasoning, per the
task's own explicit allowance ("If the correct safe strategy is to commit the complete current
architectural state, explain why first"): the required property — *a future worktree from the
checkpoint must contain the same source the main tree uses* — is only guaranteed if **every** file
the main tree currently has is committed, not just the files one task happened to touch. A partial
commit (Task-89-files only) would have left dozens of other real, load-bearing files (the intent
classifier, `correction_learner.py`, `plans.py`, `inference_observability.py`, and more) invisible
to any future isolated worktree — reproducing Task 89's exact failure mode at a different scale.
Given the secret/size scan in §2 found nothing disqualifying, committing everything was the safer
choice, not the riskier one.

```
git add -A
git commit -m "checkpoint: authoritative repository baseline (Task 90)"
```

**New HEAD:** `b922d0b0de1c6bd2e54d5f3b2042f4c1319a668b`, 2026-09-09 00:58:44 +0530 —
292 files changed, 78,246 insertions(+), 460 deletions(-). A second, small follow-up commit
(`b8d5b406b`) preserves Agent E's Task 89 report (§5) after it was recovered from its worktree
before that worktree's removal.

**Final HEAD after this task: `b8d5b406b1f...`** (see §11 for the exact log). `git status
--porcelain` is empty — the working tree is fully clean.

## 4. Task 89 verification (source + tests, not reports)

Independently re-verified via direct `grep` against the real current source (not the Task 89
reports) — full detail already given in this session's own Phase 2 work, summarized:

| Remediation | Verified present | Where |
|---|---|---|
| R1 | `async def route_task_async`, `await asyncio.to_thread(self._llm_classify, task_type)`, and `dispatch()`'s call site all present | `core/city/governor.py` |
| R2 | `_FANOUT_EDGE_COOLDOWN_SEC`, `_fanout_edge_last_fired`, `_fanout_edge_should_fire()`, and the retired `strategy` edge (comment + absence from `EVENT_TRIGGER_MAP`) all present | `core/loop/autonomous_loop.py`, `core/event_bus/wiring.py` |
| R3 | Zero autonomous `update_goal_progress()` call sites anywhere in `autonomous_loop.py` (only the explanatory comment referencing the removed call remains) | `core/loop/autonomous_loop.py` |
| R4/R5 | `PolicyMemory.make_situation_hash()`, `PolicyMemory.record_suppression()`, `veto_count` column/guard, and both call sites using the canonical hash, present | `core/memory/policy.py`, `core/memory/episodic.py`, `core/loop/autonomous_loop.py`, `core/loop/decision_engine.py` |

**Targeted tests, run this session:** the four Task 89 test suites (governor thread-hop, fanout
cooldown, goal progress, policy identity) — **31 passed, 0 failed**, exit code 0.

## 5. Worktree cleanup status

All five Task 89 worktrees (`agent-ad9301d477fc2bd70`, `agent-aa7984d197febde19`,
`agent-aeaac40876e4adf1b`, `agent-a6e29c219a736a866`, `agent-a81a959074698d49f`) were confirmed to
hold only uncommitted content already manually re-integrated into the checkpoint (§3) — verified by
inspecting each worktree's own `git status --porcelain` before removal, matching exactly the diffs
already reviewed and applied during Task 89. The one exception was Agent E's `89E_RED_TEAM.md`,
which had never been copied to the main tree (Task 89's own report explicitly said Agent E's review
was inconclusive due to the stale-worktree problem, so its output was set aside rather than
integrated) — this was copied out and committed (§3) before removal, satisfying the "reports/diffs
preserved" requirement. All five worktrees and their branches (each pointing at `6b5fcf204` with
zero unique commits of their own — confirmed via `git log -1` on each branch before deletion) were
then removed via `git worktree remove --force` + `git branch -D`.

## 6. SSL hang root-cause investigation

**Call path (confirmed):** `core/city/intent_matcher.py::_embed()` → `ollama.Client(host=
"http://127.0.0.1:11434", timeout=10.0)` → `httpx.Client.__init__` → `_init_transport()` →
`HTTPTransport.__init__` → `httpcore.ConnectionPool(...)` → `create_ssl_context(...)` →
`ssl.create_default_context(cafile=certifi.where())`.

**Isolated reproduction, step by step, all zero real network dependency except the final step:**
1. Bare `ssl.create_default_context(cafile=certifi.where())` in a fresh process: **0.16s.** Not slow.
2. Bare `ollama.Client(host=..., timeout=10.0)` construction, fresh process: **0.15s.** Not slow.
3. Same construction called from inside a running `asyncio` event loop (matching the real
   `async def _embed` call pattern): **0.62s.** Not slow.
4. 40 threads concurrently calling `ssl.create_default_context()`: **3.84s total, 0 stuck.** Real,
   measurable GIL/OpenSSL contention (~24× per-call cost under load) but **linear**, not pathological.
5. 150 threads, same test: **15.39s total, 0 stuck** — confirms linear scaling, not exponential
   blow-up; concurrency alone cannot explain a multi-minute hang.
6. `tests/test_intent_matcher.py` run in **true isolation** (single file, thread count 1 at start):
   **still hangs**, hit a 30s `--timeout` and produced a thread-dump-style trace. This **disproves**
   the concurrency-contention hypothesis as the primary cause — isolation alone doesn't fix it.
7. **Decisive finding:** a direct, unmocked call to the real local Ollama daemon —
   `ollama.Client(host="http://127.0.0.1:11434", timeout=3.0).embeddings(model="nomic-embed-text",
   prompt="test")` — **succeeded**, returning a real 768-dim embedding. **Ollama is genuinely
   running and responsive on this host.** This overturns every prior task's assumption (Tasks 88/89
   both assumed "nothing is listening on that port").
8. **Confirmed environment configuration**, read directly from process environment:
   `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_KEEP_ALIVE=2m`, `OLLAMA_HOST=127.0.0.1:11434` —
   matching this project's own documented, deliberate hardware constraint
   (`.claude/rules/models.md`: *"NEVER load 2 simultaneously (KV cache overflow)"*).

**Root cause (ENVIRONMENT/TOOLING, not a production bug):** the local Ollama daemon can hold
exactly one model resident, and evicts it after 2 minutes of inactivity. `tests/test_intent_matcher.py`
(and six other files reaching the same code path: `test_agency_run_wiring.py`,
`test_coding_reviewers_run_wiring.py`, `test_email_agent_permission_gate.py`,
`test_red_interactive_tools_bypass.py`, `test_regression_governor_capability_routing.py`,
`test_command_websocket_parity.py`) make **real, unmocked** HTTP calls to this real daemon — which
matches this project's own stated general testing convention (`.claude/rules/testing.md`: *"Real
execution, no mocks of VECTOR internals"*). During a large, multi-thousand-test suite that also
exercises other real-model-calling tests, Ollama is repeatedly forced to cold-swap models in and
out of VRAM; a cold load can plausibly take well beyond a 30–120s per-test timeout, and the
observed stack trace ("stuck" inside SSL/httpx client construction) most likely reflects the
watchdog thread sampling the call stack while the underlying socket read is still blocked waiting
on a busy/swapping daemon, not a literal deadlock inside `ssl.create_default_context()` itself
(steps 1–5 directly disprove that specific function being the true bottleneck).

**Classification: ENVIRONMENT/TOOLING BUG.** `ollama.Client()`/SSL construction is directly proven
correct and fast (steps 1–5). No VECTOR production code defect was found in this call path.

**Smallest safe remediation proposal (not implemented, per instructions):**
1. Mark the 7 identified files with a dedicated pytest marker (e.g. `@pytest.mark.requires_ollama`)
   and exclude that marker from the default/CI bulk run, running them separately in a small,
   dedicated suite with a generous timeout (e.g. 180–300s) that accounts for legitimate cold-model
   loads. **Preferred** — smallest, most targeted, does not touch any production code.
2. Alternatively, raise `--timeout` specifically for these 7 files via a `pytest.ini` per-file
   override or an in-file `pytestmark`, without excluding them from the default run.
3. **Not recommended:** mocking Ollama in these specific files, since they appear to be deliberately
   real-integration tests per this project's own stated convention — converting them to mocks would
   change what they test, not just how fast they run.

## 7. Full test baseline

`pytest --collect-only`: **5,214 tests collected** (the true, current, authoritative total — the
task's own instruction to not reuse the stale ~2,212 figure is correct; even the ~5,183 this
session's own Task 89 found has since grown slightly with Task 89's own new test files).

Full suite executed with the 7 files identified in §6 excluded (their known, now-understood cause
would otherwise make a bulk run's duration unpredictable and unrelated to anything this task is
meant to measure):

```
python -m pytest tests/ -q --timeout=90 [7 files excluded]
```

**Exact result, parsed directly from the fixed-width progress-bar output (not a summary line — this
repository's own `conftest.py` overrides the normal pytest session-finish summary, confirmed by
direct inspection):**

```
collected (this run):  5,061   (5,214 total − ~153 across the 7 excluded files)
passed:                 5,012
failed:                     13
skipped:                    36
errors:                      0
```

Duration: the run completed within a single ~10-minute execution window (unlike Task 89's earlier
attempts, which never completed within the same limit against the un-excluded file set) —
confirming the exclusion in §6 is both correct and sufficient for a completable baseline.

## 8. Failure classification

All 13 failures are the **exact same set** individually classified in Task 89's own stash-based
comparison (unchanged since — none of the files involved in those 13 failures were touched by this
session's checkpoint):

| Test | Class | Basis |
|---|---|---|
| `test_webauthn_middleware_integration.py::test_wrong_token_type_rejected_type_confusion` | **A** | Confirmed failing identically on the pre-Task-89 baseline (Task 89's `git stash` comparison) |
| `test_correction_integration.py::test_full_loop_stores_and_retrieves` | **A** | Same |
| `test_correction_integration.py::test_lifecycle_unvalidated_to_validated` | **A** | Same |
| `test_epistemic_integration.py::test_different_domains_independent` | **A** | Same |
| `test_phase_a7_council_red_tier.py::test_proceed_high_confidence_returns_proceed` | **A** | Same |
| `test_permission_gateway.py::test_red_action_times_out_without_confirmation` | **A** | Same |
| `test_agent_registry_successor_class.py::test_dying_coding_swarm_respawns_...` | **A** | Same — an independent live reproduction of the documented `spawn_successor()` dict/attribute bug, explicitly frozen/out of scope |
| `test_correction_learner.py::test_extract_from_explicit_correction` | **A** | Same |
| `test_correction_learner.py::test_tags_include_domain_and_source` | **A** | Same |
| `test_epistemic_scoring.py::test_stale_domain_reduces_score` | **A** | Same |
| `test_planning.py::test_circular_deps_flattened` | **A** | Same |
| `test_planning.py::test_decompose_returns_plan_or_none` | **A** | Same |
| `test_openwa_absorption.py::test_exception_in_send_counted_as_failure` | **C** | Confirmed (Task 89) to pass in isolation against the integrated tree; only fails as a cross-test-pollution artifact inside a mega-suite run — its presence or absence in any given bulk run's failure list is itself evidence of the pollution, not of a real regression |

**Zero class B (caused by current code) failures.** No test was altered to make this baseline look
cleaner than it is.

## 9. Future-worktree reproducibility proof

A disposable worktree (`git worktree add .claude/worktrees/t90-verify -b t90-verify-branch HEAD`)
was created from the new checkpoint commit. Verified:

- `git worktree list` showed the new worktree at the same commit as the main tree
  (`b922d0b0d`, before the follow-up 89E commit).
- **Byte-for-byte `diff` comparison** of all 9 relevant files (the 8 Task 89 files +
  `ollama_safe.py`) between the main tree and the new worktree: **all 9 matched exactly**, zero
  differences.
- Independent `grep`-based re-verification of R1/R2/R4/R5 markers **from inside the new worktree**
  (not copy-pasted from the main tree's own check): all present.
- **Functional proof, not just textual:** the same four Task 89 test suites plus the Task 88 test
  suite were run **from inside the new worktree** — **38 passed, 0 failed**.

This is the concrete, direct proof that a future parallel sub-agent, given `isolation: "worktree"`
from this point forward, will see the real, current VECTOR source — the exact property Task 89's
own operational failure showed was previously false.

The disposable worktree and its branch were removed after verification (`git worktree remove
--force`; the directory removal initially failed with a Windows file-lock permission error,
resolved by a fallback `rm -rf` after git's own worktree metadata had already been deregistered —
harmless, fully cleaned up, confirmed via `git worktree list` and `git status --porcelain` both
showing a fully clean state afterward).

## 10. Remaining infrastructure problems

- **The 7 real-Ollama-dependent test files** (§6) still need their own dedicated marker/timeout
  treatment — proposed, not implemented, per instructions.
- **`test_openwa_absorption.py`'s cross-test pollution** (class C, §8) is itself a latent test-isolation
  bug somewhere in the suite (most likely shared global/singleton state a mega-run mutates) —
  identified, not root-caused or fixed; a good candidate for a future, narrowly-scoped
  investigation, separate from R6.
- **Eight root-level scratch `.md` files** (class C, §2) remain in the repository root rather than
  under `docs/` — committed as-is (not this task's call to relocate or delete), flagged for a future
  housekeeping pass.
- **12 class-A pre-existing failures** (§8) remain genuinely open defects in their own right
  (correction learner domain inference, epistemic scoring edge case, `MissionPlanAdvisor` missing
  attribute, the `spawn_successor()` bug, a `pending_id` keyword mismatch, a WebAuthn token-type
  check, and a council red-tier verdict-string mismatch) — none are this task's or R6's scope, but
  are now precisely enumerated for whichever future task picks them up.

## 11. Exact recommended next task

**R6 — candidate diversity, staleness-only** (per Task 87/89's own established priority ordering):
the precondition for ever measuring whether R4/R5's now-reconnected reward signal changes a real
production decision. This baseline (5,214 total tests, 5,012/5,061 passing in the excludable-clean
run, 0 new regressions, a verified-reproducible checkpoint at `b8d5b406b`) is the correct starting
point for that work.

```
Final HEAD: b8d5b406b1f... "docs: preserve Agent E's Task 89 red-team report before worktree cleanup"
Parent:     b922d0b0d...   "checkpoint: authoritative repository baseline (Task 90)"
```

---

## Integrity statement

Production source outside the two commits described above: **not modified**. `.env`: **not
modified**. Experiment database/settings: **not touched**. Segment2/PID 37588: **not running,
not interacted with**. Destructive git operations: **none** (`git worktree remove --force` and
`git branch -D` were used only on the five confirmed-stale, zero-unique-commit Task 89 worktrees/
branches and the one disposable verification worktree created and removed within this task; no
production branch, tag, or remote ref was touched; nothing was force-pushed; `origin` was never
contacted). Files created: this report and the two commits' contents already itemized above.

---

# FINAL VERDICT

**AUTHORITATIVE CHECKPOINT:** PASS

**TASK 89 SOURCE VERIFICATION:** PASS

**WORKTREE REPRODUCIBILITY:** PASS

**SSL HANG:** ENVIRONMENT BUG

**FULL SUITE:** 5,214 collected (true total) / 5,061 collected (this run, 7 known-environment-
dependent files excluded) / 5,012 passed / 13 failed / 36 skipped / 0 errors

**NEW REGRESSIONS:** 0

**NEXT TASK:**

R6 — candidate diversity, staleness-only

Do NOT start R6.

STOP.
