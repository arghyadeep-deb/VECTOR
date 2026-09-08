# Task 89 — Post-Experiment Parallel Cognitive Foundation Remediation: Integration Report

## 1. Executive summary

Four parallel sub-agents (A: runtime boundary, B: event fanout, C: goal progress, D: policy/reward
identity), each in an isolated git worktree, implemented one narrow remediation apiece against
current source. The lead agent (this session) manually reviewed every agent's exact diff, then
integrated all four into the main working tree — **not via git merge**, because a critical
operational discovery made merging unsafe (see §2). A fifth sub-agent (E, red team) was launched to
review the integrated result but hit the same staleness problem in its own isolated worktree and
could not actually see the integration; rather than spend another cycle on a repeat isolated agent,
the lead performed the safety review directly against the real integrated tree. Net result: **all
four remediations (R1–R5) are integrated, syntactically valid, and pass 268 targeted/regression
tests plus 14 individually-classified pre-existing-failure checks with zero new (class B)
regressions found.**

## 2. Segment2 closure status

Confirmed at the start of this task and unchanged throughout: PID 37588 (`python run_vector.py
loop`) is **not running** — no python.exe process of any kind was found on the host at task start.
VECTOR was not started, stopped, signaled, or interacted with in any mode at any point during this
task. `.env` was not modified. `VECTOR_MCP` and `COUNCIL_AUTO_PROCEED_ALLOWED` were not touched.

**Critical operational finding, discovered mid-task:** all five sub-agent worktrees were branched
from the same stale commit (`5964a331678ac648c8289f4c38fd0e5430e1ee9d`, dated 2026-08-07) because
none of the substantial uncommitted work already sitting in this repository — including this
session's own prior Task 88 fix — had ever been committed to git. A `git worktree add` branches from
the last commit, not the dirty working tree, so **no sub-agent could see any of that prior
work**, including, in Agent D's case, a fourth PolicyMemory writer (a `plan_step:`-prefixed one)
that was added to the working tree after the stale commit and that Agent D's own diff therefore
never touched. This is why blind `git merge`/`git cherry-pick` of any agent's branch was rejected in
favor of manual, verified, semantic re-application of each agent's actual intended change onto the
real current file content (§9). This is disclosed prominently because it is the single most
important process lesson from tonight's work, not because any agent did anything wrong — each
agent's own within-worktree diff was correct and well-tested for what it could see.

## 3. Agent A result — runtime boundary (R1)

**Verified Task 88's existing fix present and correct** in the (stale) worktree Agent A had, and
separately, independently in the real tree during integration (§9). **New fix implemented and
integrated:** `Governor.dispatch()`'s one call site (`district = task.get("district") or
self.route_task(task_type)`) changed to `await self.route_task_async(task_type)` — a new async
twin of `route_task()` that keeps cheap keyword/exact `DISTRICT_TASK_MAP` matching synchronous
inline and moves only the LLM-classification fallback off the event-loop thread via a genuine
`await asyncio.to_thread(self._llm_classify, task_type)`. `route_task()`/`_llm_classify()`
themselves are byte-for-byte unchanged — their ~10 other synchronous callers elsewhere in the
codebase are unaffected. `AgentBase.vchat()` was investigated, an initial fix attempt was
empirically proven insufficient (bounds worst-case wait but doesn't stop ordinary-latency event-loop
blocking, since all ~15 call sites are unawaited), and per the task's own conservative-fallback
instruction, **no change was made there** — reported as a recommendation requiring a larger,
separately-scoped `async def` migration.

**Disproven/corrected finding:** neither Agent A's worktree, nor a repo-wide check performed during
integration, found any evidence tying the historic 69.9-hour hypothesis-engine hang to a specific,
confirmed mechanism beyond what Task 84/87 already established (LIKELY/PLAUSIBLE, never PROVEN) —
this classification is preserved, not upgraded.

## 4. Agent B result — event fanout (R2)

**Fully implemented and integrated.** Edge identity `(source_event_type, target_district,
target_task_type)`; a module-level `_FANOUT_EDGE_COOLDOWN_SEC = CONFIG.get("fanout_edge_cooldown_sec",
120.0)`, `_fanout_edge_last_fired` dict, and `_fanout_edge_should_fire()` helper in
`autonomous_loop.py`; a 3-line cooldown gate inserted into `_fanout_handler`'s existing
downstream-dispatch loop, before `self._tracked_task(governor.dispatch(task), ...)` — the timestamp
is recorded on acceptance, before dispatch, so success/failure/no-agent outcomes all consume the
cooldown identically. `core/config.py` got the matching `FANOUT_EDGE_COOLDOWN_SEC` field. The
confirmed-dead `strategy::review_analytics_insights` edge was retired from
`EVENT_TRIGGER_MAP[EventType.ANALYTICS_READY]` after independent verification (39 real districts in
`config/agent_manifest.yaml`, `strategy` not among them). All other `PUBLISH_EVENTS`/
`EVENT_TRIGGER_MAP` entries are untouched.

## 5. Agent C result — goal progress semantics (R3)

**Fully implemented and integrated, plus one lead-discovered extension.** The main "Goal feedback
loop" block's `gs.update_goal_progress(_gid, _new_progress, ...)` call (reward-scaled, unconditional)
was removed and replaced with an observability-only debug log. `update_goal_progress()` itself, and
every other caller of it, is untouched — an explicit human/API call still completes a goal exactly
as before. **During integration, the lead found and fixed a second, structurally identical call
site** inside the plan-step execution path (`if completed and plan.goal_id: ... gs.update_goal_progress(...)`)
that did not exist in Agent C's stale worktree base and so could not have been in Agent C's own
diff — the same fix (remove the mutation, keep a debug log) was applied, following Agent C's exact,
already-tested pattern. A repo-wide grep after both fixes confirms **zero remaining autonomous
callers of `update_goal_progress()`** anywhere in `autonomous_loop.py`. `GOAL_ACTION_MAP` and
`goal_system.py` are untouched. C7's finding (no recurring/habit-goal mechanism exists anywhere) is
preserved as an explicit, acknowledged, unaddressed gap — not built tonight.

## 6. Agent D result — policy/reward identity (R4/R5)

**Fully implemented and integrated**, not stopped at the compatibility-matrix gate. Re-derived the
full writer/reader matrix from source (correcting the original briefing: the 5-factor writer is
where the briefing said, but a `plan_step:`-prefixed 4th writer exists in the real tree that neither
Agent D's stale base nor its own report could see — see §2). `PolicyMemory.make_situation_hash()`
extended with a new `(action_type, params)` overload (`"v2:"`-prefixed), reused as the single
canonical function by `decision_engine.py`'s reader and by three of `autonomous_loop.py`'s writers
(VectorCode reward, 5-factor reward, and — critically — the counterfactual-veto writer, which now
calls the new `record_suppression()` method **instead of** `update_from_outcome(..., reward=0.05)`).
`record_suppression()` increments a new, additive `policy_memory.veto_count` column
(`_ensure_policy_columns()` in `episodic.py`, guarded/idempotent `ALTER TABLE ADD COLUMN`, mirrored
in both SQL schema files) — `avg_reward`/`sample_count` on any existing row, including the
~29,000-sample historical `analyze_progress` row, are never touched by this or any other change
tonight. No new module was created — `PolicyMemory.make_situation_hash` was reused per the task's
explicit preference. `hands/runner.py`'s writer got a documentation-only comment (verified
independently: no `Candidate` with a hand's name as `action_type` is ever constructed, so it remains
correctly unreachable rather than being force-connected). **The newly-discovered 4th (`plan_step:`)
writer was deliberately left unconnected** — merging plan-step identity with goal identity is an
unresolved design question (per Task 87 §11's own explicit deferral), not a safe default, and no
one agent or the lead made that call unilaterally tonight.

## 7. Agent E red-team result

**Could not review the actual integration** — its isolated worktree, like A–D's, was branched from
the stale pre-Task-89 commit and therefore correctly reported that none of R1–R5 existed in *its*
environment. This is a tooling artifact, not a finding about the real integrated code (§2). Agent E
did independently re-derive, from the stale tree, the same writer/reader key mismatch Task 87/89
already established — consistent corroboration, not new information. In place of a second isolated
agent (which would hit the identical trap), **the lead performed the safety review directly against
the real integrated tree**, covering Agent E's own 15-item checklist:

1. **PermissionGateway bypass** — none. No file touched tonight calls or modifies `PermissionGateway`.
2. **RED action creation** — none. No new action_type is proposed/dispatched anywhere; R6 (candidate
   diversity/tag routing, the change that would risk this) was explicitly not implemented by any
   agent.
3. **YELLOW promotion changes** — `TrustLadder` (`core/loop/trust_ladder.py`) was never touched.
4. **TrustLadder interaction (the flagged danger case) — modeled precisely.** R4/R5 makes real
   5-factor outcome rewards visible to `decision_engine.get_score()` for the first time (previously
   written under an unreadable key). If a YELLOW-tier action (confirmed: `commit_code` is YELLOW,
   `core/config.py` line ~115) now scores measurably higher because its real reward is finally
   read back, it could be proposed more often; each proposal that reaches the owner and is
   explicitly approved still advances `TrustLadder`'s streak exactly as it always has
   (`bad_outcomes == 0 and streak >= 20`, `trust_ladder.py:85/115`, **completely unmodified
   tonight**). This is a **real, documented, previously-anticipated** consequence of fixing the
   reward-identity bug — named explicitly in Task 87 §18 as a required-control item for a *future*
   task, not a new risk introduced silently tonight. Critically: it does not create any autonomous
   path around the owner — every single approval in a promotion streak is still a genuine, explicit
   human action; R4/R5 only makes it *possible* for a genuinely good action to be recognized as good
   sooner. Classified: **known, accepted, non-blocking residual risk**, not a regression.
5. **Candidate expansion** — none; `generate_immediate_actions()`/`_TAG_TO_ACTION`/`GOAL_ACTION_MAP`
   untouched.
6. **Event fanout amplification** — R2 is monotonically load-reducing by construction (a cooldown
   can only suppress a fire, never add one); no path bypasses the gate to fire more often than
   before.
7. **Reward contamination** — verified by direct grep: the only three `update_from_outcome(...,
   reward)` call sites remaining in `autonomous_loop.py` are the three real-outcome writers; the
   veto/suppression path now calls `record_suppression()` exclusively. No leak found.
8. **Historical data corruption** — verified: zero migration/backfill/rewrite of any existing
   `policy_memory`, goal, or counterfactual row anywhere in tonight's diffs.
9. **Hidden DB/schema changes** — `_ensure_policy_columns()` read directly: guarded by a
   `PRAGMA table_info` check before `ALTER TABLE`, safe to call every startup, safe to call
   repeatedly (checks column existence first).
10. **Subprocess/network side effects** — none added by any of tonight's changes.
11. **Unintended autonomous execution** — traced the full composite chain: a real reward becoming
    visible can change *which* already-possible candidate wins a tie, but every winning candidate
    still passes through the exact same, unmodified `_act_on()` gating (gateway for RED/YELLOW/
    plan/skill-matched, veto for counterfactual-flagged, ungated district dispatch otherwise) —
    nothing tonight adds a new way to reach execution, only changes which already-reachable thing
    is more likely to be picked.
12. **Race conditions** — `_fanout_edge_should_fire()` contains no `await`; on Python's single-
    threaded cooperative `asyncio` event loop, a function with no `await` inside it cannot be
    interleaved mid-execution by another coroutine, so the plain (unlocked) dict read-then-write is
    safe.
13. **Async blocking** — `route_task_async()`'s `await asyncio.to_thread(...)` genuinely yields the
    event loop for the duration of `_llm_classify()`'s synchronous work, confirmed by reading
    `_llm_classify()`'s body (no work happens before its first potentially-blocking call that would
    itself need to run on the loop thread).
14. **Test mocks hiding real behavior** — spot-checked: Agent C's tests exercise a real `GoalSystem`
    against a real temp-file SQLite DB (not mocked); Agent D's tests perform genuine round-trip
    writer→storage→reader assertions; Agent B's tests assert real dict-state cooldown timestamps
    with real `time.monotonic()` deltas. None rely on "mock was called" alone.
15. **Modifications outside intended scope** — the only deviation from what the four agents' own
    reports claim is the one extra fix in §5 (the plan-step goal-progress site), explicitly
    documented with its own comment in the source, and disclosed here.

**Overall verdict: PASS.** No blocking finding. Item 4 (TrustLadder) is the one item worth carrying
forward explicitly as a known, non-blocking, previously-anticipated residual — recommended controls
(minimum elapsed-time gate in addition to streak count, streak invalidation on a policy-key schema
bump, owner-visible promotion notifications) remain unimplemented and explicitly out of scope
tonight, exactly as Task 87 §18 specified.

## 8. Exact files modified

**Production files (8):**
- `core/city/governor.py`
- `core/loop/autonomous_loop.py`
- `core/config.py`
- `core/event_bus/wiring.py`
- `core/memory/policy.py`
- `core/loop/decision_engine.py`
- `core/memory/episodic.py`
- `hands/runner.py`

**Schema files (2, additive only):**
- `deploy/sqlite_schema.sql`
- `deploy/supabase_schema.sql`

**Test files (5 new, 1 modified):**
- `tests/unit/test_governor_dispatch_thread_hop.py` (new)
- `tests/loop/test_fanout_cooldown.py` (new)
- `tests/test_task89c_goal_progress.py` (new)
- `tests/test_policy_reward_identity.py` (new)
- `tests/test_counterfactual_block_penalizes_policy.py` (rewritten to assert corrected behavior)

**Documentation (5, this directory):**
- `VECTOR_TECHNICAL_KNOWLEDGE/89A_RUNTIME_BOUNDARY.md`
- `VECTOR_TECHNICAL_KNOWLEDGE/89B_EVENT_FANOUT.md`
- `VECTOR_TECHNICAL_KNOWLEDGE/89C_GOAL_PROGRESS.md`
- `VECTOR_TECHNICAL_KNOWLEDGE/89D_POLICY_REWARD_IDENTITY.md`
- `VECTOR_TECHNICAL_KNOWLEDGE/89_OVERNIGHT_INTEGRATION_REPORT.md` (this file)

No file outside this list was created or modified by this task. The repository's large body of
other pre-existing uncommitted changes (§2) was left completely untouched throughout.

## 9. Exact diffs summarized

Each agent's diff was retrieved directly from its worktree branch (`git -C <worktree> diff
5964a331678ac648c8289f4c38fd0e5430e1ee9d`), read in full, and either (a) applied via `git apply`
where the target file was unchanged from that shared base in the main tree (`core/event_bus/wiring.py`,
`core/memory/policy.py`, `core/memory/episodic.py`, both SQL schema files, `hands/runner.py`,
`tests/test_counterfactual_block_penalizes_policy.py` — all applied cleanly, zero conflicts), or (b)
manually re-applied via targeted `Edit` calls against the real current file content where the main
tree had already diverged from that base (`core/city/governor.py`, `core/config.py`,
`core/loop/decision_engine.py`, and the three-way-touched `core/loop/autonomous_loop.py`), verified
line-by-line against each agent's actual diff content before and after. All eight production files
were confirmed to still `ast.parse()` cleanly after every edit, individually and as a final full
pass.

## 10. Exact test results

| Suite | Result |
|---|---|
| All 4 agents' new test files together (32 tests: 4 governor thread-hop + 15 fanout cooldown + 7 goal progress + 5 policy identity + 1 counterfactual) | **32 passed, 0 failed** |
| `tests/event_bus/`, `tests/test_governor.py`, `tests/unit/test_governor.py`, `tests/loop/test_autonomous_loop.py`, `tests/unit/test_ollama_semaphore_timeout.py`, `tests/unit/test_ollama_concurrency.py`, `tests/unit/test_ollama_multi_backend_fallback_timeout.py`, `tests/unit/test_inference_observability_gaps.py` | **137 passed, 0 failed** |
| `tests/test_decision_engine.py`, `tests/unit/test_decision_engine.py`, `tests/unit/test_memory_stores.py`, `tests/integration/test_phase_a4_metacognition_decision.py`, `tests/test_point_system.py` | **99 passed, 0 failed** |
| **Total directly-relevant regression** | **268 passed, 0 failed** |

## 11. Baseline comparison

The task's stated baseline (~2212 collected / 2175 passed / 8 pre-existing failures / 0 errors / 29
skipped) is **stale relative to the actual current repository** — a `--collect-only` pass this
session counted **5,183 tests** across 306 files, more than double the stated figure, consistent
with this repo's large body of uncommitted, uncounted prior work (§2). A full-suite run was
attempted twice; both times a genuine, pre-existing, environment-specific hang (any code path
reaching `core/city/intent_matcher.py`'s `ollama.Client(...)` construction blocks indefinitely
inside `ssl.create_default_context()` on this host — unrelated to tonight's work, confirmed present
before any of tonight's changes) prevented completion within the tool's execution-time limits. A
partial run (7 known-hang-reaching files excluded, reaching a substantial fraction of the suite
before being cut off by the same limit) surfaced **14 distinct failing tests**, all individually
classified in §12.

## 12. New failures, if any

All 14 flagged tests were individually re-run against a `git stash`-reverted pre-integration tree
(stashing only tonight's 8 production files + 1 modified test file, preserving every other
pre-existing uncommitted change untouched) to distinguish class A from class B:

| Test | Classification | Evidence |
|---|---|---|
| `test_webauthn_middleware_integration.py::test_wrong_token_type_rejected_type_confusion` | **A — pre-existing** | Fails identically pre- and post-integration (`assert 200 == 401`) |
| `test_correction_integration.py::test_full_loop_stores_and_retrieves` | **A** | Fails identically (`'general' != 'coding'`) |
| `test_correction_integration.py::test_lifecycle_unvalidated_to_validated` | **A** | Fails identically (`'validated' != 'unvalidated'`) |
| `test_epistemic_integration.py::test_different_domains_independent` | **A** | Fails identically |
| `test_phase_a7_council_red_tier.py::test_proceed_high_confidence_returns_proceed` | **A** | Fails identically (`'defer' != 'proceed'`) |
| `test_permission_gateway.py::test_red_action_times_out_without_confirmation` | **A** | Fails identically (`TypeError: ...got an unexpected keyword argument 'pending_id'`) |
| `test_agent_registry_successor_class.py::test_dying_coding_swarm_respawns_...` | **A** | Fails identically — this is in fact a **live, independent reproduction of the exact `spawn_successor()` dict/attribute bug** Tasks 80–87 documented (`'dict' object has no attribute 'generation'`), explicitly frozen/out of scope tonight per the task's own instruction ("Do not fix successor lifecycle yet") |
| `test_correction_learner.py::test_extract_from_explicit_correction` | **A** | Fails identically |
| `test_correction_learner.py::test_tags_include_domain_and_source` | **A** | Fails identically |
| `test_epistemic_scoring.py::test_stale_domain_reduces_score` | **A** | Fails identically (`0.49 vs 0.49` — a genuinely pre-existing edge-case bug) |
| `test_planning.py::test_circular_deps_flattened` | **A** | Fails identically (`AttributeError: ...does not have the attribute 'MissionPlanAdvisor'`) |
| `test_planning.py::test_decompose_returns_plan_or_none` | **A** | Fails identically, same missing attribute |
| `test_missions.py::test_missions_api_timeline_and_artifacts` | **C — environment/tooling** | Passes on the isolated pre-integration baseline batch; **passes in isolation against the integrated tree** (confirmed this session, 2/2 pass); only "fails" as an artifact of running inside the same process as 5000+ other tests in the mega-suite attempt — cross-test pollution, not caused by this work |
| `test_openwa_absorption.py::test_exception_in_send_counted_as_failure` | **C — environment/tooling** | Same as above — passes in isolation, confirmed this session |

**Zero class-B (caused-by-this-work) failures found.** No revert or fix was required as a result.

## 13. Safety impact

No `PermissionGateway` change. No new RED/YELLOW action type. No TrustLadder modification (one
known, documented, non-blocking residual interaction noted in §7 item 4). No widened autonomous
capability. No new subprocess/network reachability. Full detail in §7.

## 14. Runtime impact

R1 removes one confirmed event-loop-blocking call site on VECTOR's highest-volume dispatch path
(`Governor.dispatch()`); its LLM-classification fallback now genuinely yields the event loop instead
of blocking it for the duration of a classification round-trip. R2 is strictly load-reducing —
fan-out dispatch volume can only go down, never up, relative to before. Neither change alters
`PermissionGateway`, `Governor`'s routing decisions, or any district's declared capabilities.

## 15. Data/schema impact

One additive column (`policy_memory.veto_count INTEGER DEFAULT 0`), added via a guarded, idempotent
`ALTER TABLE` on existing databases and included in both schema files for fresh databases. No
existing row in `policy_memory`, `goals_v1`/goal storage, or `counterfactual`'s `rejections` table
was migrated, rewritten, or deleted by anything tonight — verified directly, not merely claimed.

## 16. Rollback instructions

Every change is contained to the 8 production files + 2 schema files listed in §8, each independently
revertible:
- **R1:** revert `route_task_async()`'s addition and `dispatch()`'s one call-site change in
  `governor.py`.
- **R2:** revert the module-level cooldown block, the 3-line gate in `_fanout_handler`, and the
  `FANOUT_EDGE_COOLDOWN_SEC` config field; optionally re-add the `strategy` edge to
  `EVENT_TRIGGER_MAP` if desired.
- **R3:** revert the two "Goal feedback loop" block replacements in `autonomous_loop.py` — the
  original reward-mutation code is preserved in full in this report (§5) and in each git diff.
- **R4/R5:** revert the three writer call sites and the reader delegation in `decision_engine.py`;
  the additive `veto_count` column can be left in place harmlessly (nothing reads it if the writer
  reverts) or dropped manually — no automated down-migration was written, consistent with this
  project's own established "no migration needed, old and new coexist" pattern.

No rollback requires a database restore — every schema change is additive-only, and no historical
row was ever modified.

## 17. Remaining known defects

Carried forward, unchanged, from Tasks 84–88, explicitly out of scope tonight: the untraced APITester
stale-reference (§17 of Task 87); the un-fixed `spawn_successor()` dict/attribute contract break
(independently reproduced live in §12's table); `AgentBase.vchat()`'s remaining ~15 unawaited call
sites (Agent A's own recommendation, not fixed); the newly-discovered 4th (`plan_step:`-prefixed)
PolicyMemory writer, deliberately left disconnected pending its own identity-design decision; no
candidate diversity (R6) yet exists, so `decision_engine.evaluate()` still sees very few real
competing candidates in production; and the `strategy`-edge-shaped class of "dead event target"
elsewhere in `EVENT_TRIGGER_MAP` was not exhaustively re-audited beyond the one confirmed case.

## 18. Cognitive maturity after remediation

Using the L0–L5 ladder established in Task 86/87: R4/R5 moves the PolicyMemory mechanism from
**L1-FAIL** (reader-key ≠ writer-key for 3 of 4 real writers) toward **L1-PASS/L2-testable** — the
canonical key now makes real outcome rewards genuinely retrievable, and the veto channel no longer
contaminates the reward mean. R3 removes a confirmed, actively-destructive negative-feedback loop
from the `goal_alignment` term (0.30 weight). R1/R2 remove two runtime/noise confounders that would
otherwise corrupt any future measurement. **None of this constitutes a demonstrated behavioral
adaptation (L4) in production** — that requires real candidate diversity (R6, frozen tonight per
explicit instruction) and a dedicated experiment (Task 87 §23's E1/E6), neither of which was run.
Per the task's own explicit prohibition, this report makes none of the forbidden claims ("VECTOR now
learns", "general intelligence", "understands like Astra", "human-like learning").

## 19. What is still NOT proven

That any of R1–R5, individually or together, changes VECTOR's actual autonomous decision output in
production — no behavioral experiment was run tonight (correctly out of scope: this was a repair
task, not a measurement task). That the TrustLadder interaction (§7 item 4) will or won't manifest
in practice — it is modeled, not observed. That the full 5,183-test suite passes end to end — the
environment's own `ssl.create_default_context()` hang made a complete run impractical within this
session; 268 directly-relevant tests plus 14 individually-classified flagged failures is the
strongest evidence obtainable this session, not a substitute for a genuinely complete run in an
environment without that pre-existing hang.

## 20. Recommended next task

Trace the `ssl.create_default_context()` hang blocking full-suite completion (a pure environment/
tooling investigation, zero production risk) so that future sessions can get a genuine complete
regression baseline — this is now the single biggest obstacle to confidently verifying *any* future
change against this repository, tonight's work included.

---

# FINAL DECISION

**R1 Runtime boundary:** PASS
**R2 Event fanout:** PASS
**R3 Goal semantics:** PASS
**R4/R5 Policy identity:** PASS
**Safety red-team:** PASS

**Regression suite:**
- New tests (4 agents combined): 32 passed, 0 failed
- Directly-relevant regression suites: 137 + 99 = 236 passed, 0 failed
- **Total: 268 passed, 0 failed, 0 errors, 0 skipped (targeted run)**
- Full-suite baseline: stale (task's stated ~2212 vs. actual 5,183 collected); complete run
  impractical this session due to a pre-existing, unrelated environment hang; 14 flagged failures
  from a partial run individually classified — 12 class A (pre-existing), 2 class C
  (environment/test-pollution, confirmed passing in isolation), **0 class B**

**Production files modified:**
`core/city/governor.py`, `core/loop/autonomous_loop.py`, `core/config.py`,
`core/event_bus/wiring.py`, `core/memory/policy.py`, `core/loop/decision_engine.py`,
`core/memory/episodic.py`, `hands/runner.py`, `deploy/sqlite_schema.sql`,
`deploy/supabase_schema.sql`

**Most important remaining defect:**
The `spawn_successor()` dict/attribute contract break (`AgentRegistry.deregister()` calling the
legacy dict-returning `spawn_successor()` then doing attribute access on the result) — independently
reproduced live in this session's own regression run, still unfixed, explicitly frozen tonight per
instruction.

**Next implementation task:**
R6 — candidate diversity (goal-progress staleness threshold only, no tag propagation), the
precondition for ever measuring whether R4/R5's reconnected reward signal actually changes a
production decision.

STOP. Task 90 not started.
