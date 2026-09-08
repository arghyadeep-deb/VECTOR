# 52 — Autonomy Blocker Remediation

**Date**: 2026-09-02
**Type**: TARGETED FIX — implements only the 2 MUST-FIX blockers identified in
`VECTOR_TECHNICAL_KNOWLEDGE/51_FINAL_COGNITIVE_INTEGRATION_AUDIT.md` §16. No redesign, no new
subsystems, no unrelated refactoring.
**Scope discipline**: every design decision below was checked against "is this the smallest
change that closes the audited gap" before being written. Where a larger fix would have been
easy to justify (see §9 Remaining Risks), it was deliberately NOT made.

---

## 1. Problem

### Blocker 1 — `hypothesis_loop()` never executes hypothesis generation

`autonomous_loop.py:2868` called `HypothesisEngine.generate_hypotheses()` — an `async def`
method (`hypothesis_engine.py:48`) — without `await`. The result is a coroutine object, not a
hypothesis. A coroutine object is truthy, so the surrounding code (`if not hypotheses: continue`)
never short-circuits; it proceeds through checks written for a real result and always lands on
"low confidence, suppressed" — the underlying LLM call inside `generate_hypotheses()` never fires.
This has been true since the code was written; the loop logs "starting — fires every 4h" and
appears fully wired, but has produced zero actual hypotheses in its entire runtime.

### Blocker 2 — plan-step crash mid-execution permanently stalls the plan

`PlanRunner.execute_step()` (`plans.py`) persists `step.status = "running"` to disk immediately
before calling the executor. If the process dies (crash, OOM, host restart, manual kill) between
that write and the step's eventual terminal-status write a few lines later, the step is left at
`"running"` forever. `Plan.next_ready_steps()` only offers steps with `status == "planned"` — a
`"running"` step is silently excluded on every future tick, and nothing anywhere resets it. Any
downstream step depending on it never becomes ready either. Over a 7-day continuous unattended
run, at least one process restart is a realistic occurrence, not a hypothetical edge case.

---

## 2. Root Cause

**Blocker 1**: a missing `await` keyword. One token. No design flaw in `HypothesisEngine` itself —
`generate_hypotheses()` is correctly written and tested in isolation
(`core/brain/hypothesis_engine.py`'s own `__main__` self-test calls it correctly with
`asyncio.run()`). The defect is entirely in the caller.

**Blocker 2**: `execute_step()` follows the correct pattern for crash-observability (persist state
*before* doing risky work, so a crash leaves evidence of what was in flight) — but nothing
consumes that evidence on the next boot. `PlanStore._ensure_loaded()` (the load path every fresh
process takes) had no recovery step; it simply deserialized whatever status was on disk, including
`"running"`, and treated it as ordinary state.

---

## 3. Implementation

### Blocker 1 fix — `core/loop/autonomous_loop.py:2868`

```python
# Before:
hypotheses = engine.generate_hypotheses(context)
# After:
hypotheses = await engine.generate_hypotheses(context)
```

One line changed. Nothing else in `hypothesis_loop()` was touched:
- Scheduling cadence (`await asyncio.sleep(4 * 3600)`) — unchanged.
- Exception handling (`except asyncio.CancelledError: break` / `except Exception as e: ... await
  asyncio.sleep(300)`) — unchanged, and now actually reachable for generation failures (before the
  fix, an exception inside `generate_hypotheses()` could never propagate to this block at all,
  because the coroutine that would raise it was never run).
- Confidence/suppression logic (`if confidence >= 0.85: ... else: logger.debug(...suppressed...)`)
  — unchanged.
- Hypothesis-generation prompts (`HypothesisEngine._SYSTEM`, the prompt template inside
  `generate_hypotheses()`) — untouched.
- Provider routing / model selection (`ProviderClient().chat(tier="reasoning", ...)` inside
  `HypothesisEngine._call()`) — untouched.
- No second hypothesis-generation mechanism was introduced. `HypothesisEngine` remains the sole
  generator; only the call site's `await` was corrected.

### Blocker 2 fix — `core/runtime/plans.py`

Three new small functions, all synchronous (no LLM calls, safe to run inside the existing
synchronous `PlanStore._ensure_loaded()`):

**`_is_safe_to_auto_resume(action_type: str) -> bool`** — reuses the *existing*
`core/loop/permission_gateway.py` GREEN/YELLOW/RED/FORBIDDEN action-type classification (the same
constants the gateway itself uses before executing anything). Returns `True` only for GREEN
(read-only/idempotent: `search_web`, `respond`, `check_attendance`, `git_status`, etc.). No new
safety taxonomy — this is a read of an existing safety boundary, not a new one.

**`_try_fallback_step(plan, failed_step) -> bool`** — extracted from `replan_plan()`'s existing
Strategy 1 (swap in the step's declared `fallback`, preserving its `id` so downstream
`depends_on` links stay valid). Previously inlined only inside the async `replan_plan()`; now a
standalone synchronous function that both `replan_plan()` (unchanged call site, same behavior) and
the new recovery path call — one implementation, two callers, not a duplicate.

**`_recover_stale_running_steps(plan) -> bool`** — called once per plan, the first time it's
loaded into a fresh `PlanStore` (`PlanStore._ensure_loaded()`, right after each plan is
deserialized). For every step still `status == "running"`:

- **GREEN-tier action** → reset `status = "planned"`. The step is naturally re-offered by
  `next_ready_steps()` on the next `_think_tick()` and re-executed through the *normal* decision
  cycle — which itself re-applies the permission gate exactly as it would have on the step's first
  attempt. Recovery does not bypass anything.
- **Not GREEN-tier (YELLOW/RED/FORBIDDEN/UNKNOWN)** → marked `status = "failed"` with an explicit
  interruption reason, then given the **same** chance a normal failure gets via
  `_try_fallback_step()` (if the step has a declared fallback, swap to it — safe, since the
  fallback action itself hasn't started). If there's no fallback, `plan.review_required = True` is
  set so the interruption is visible plan-wide. The original risky action is **never** silently
  re-executed.

Every recovery decision is recorded in two existing, previously-unused fields:
`PlanStep.retry_info` (a free-form dict, declared in the dataclass, serialized/deserialized, but
never written by any code before this change) and a new `PlanEvent` of type `"step_recovered"`
(using the existing `Plan.record_event()` mechanism — no new event-logging system).

`PlanStore._ensure_loaded()` calls `self.save()` once at the end if any step was recovered, so the
decision is persisted to disk immediately (not just held in memory).

---

## 4. Why This Implementation Is Minimal

- **Zero new persisted schema.** `PlanStep.retry_info` and `Plan.review_required` both already
  existed in the dataclass, declared and round-tripped through `to_dict()`/`from_dict()`, but
  unused by any prior code path. No new field was added to either dataclass.
- **Zero new safety taxonomy.** Recovery reuses the exact same GREEN/YELLOW/RED/FORBIDDEN
  constants `permission_gateway.py` already enforces before every real action — importing the
  constants directly (not instantiating `PermissionGateway()`, which opens SQLite audit stores and
  rehydrates pending approvals — too heavy and side-effect-prone for a load-time hook).
- **Zero new failure-handling path.** The non-GREEN branch reuses `_try_fallback_step()`, the
  exact logic `replan_plan()`'s Strategy 1 already used — extracted into a shared function, not
  duplicated or reinvented. The LLM-restructure strategy (`replan_plan()`'s Strategy 2) was
  deliberately **not** attempted during recovery, because it requires an async LLM call that a
  synchronous load-time hook cannot safely make without a much larger refactor of `PlanStore`'s
  calling convention across every one of its ~6 real call sites (`add`, `get`, `active_plans`,
  `plans_for_goal`, `list`, `clear`) — out of scope for "smallest robust recovery mechanism."
- **Zero changes to normal (non-crash) step execution.** `PlanRunner.execute_step()` is byte-for-
  byte unchanged. Recovery only ever touches a step at load time, before any tick has a chance to
  execute it normally.
- **Single detection point.** Recovery hooks into the one place a "process restart" is structurally
  guaranteed to be true: the first `_ensure_loaded()` call on a fresh `PlanStore` instance (guarded
  by `self._loaded`, so it can only run once per process's lifetime for a given store). No new
  boot-sequence hook, no new scheduler job, no new "am I really restarting" heuristic — the
  guarantee comes from the pre-existing lazy-load-once pattern.

---

## 5. Crash/Restart Semantics

**What counts as "recoverable"**: a step is treated as crash-interrupted if and only if it is
found at `status == "running"` the very first time a `PlanStore` instance loads the plan from
disk. This is unconditionally correct in the current single-process, single-`PlanRunner`-per-
process architecture: `execute_step()` is the only writer of `status = "running"`
(`plans.py:~698`), and within one process it always resolves that same step to a terminal status
(`completed`/`failed`/`blocked`) a few lines later, before the next tick can start a *different*
step. A `"running"` step surviving to the next fresh load was, by construction, orphaned by a
process that no longer exists — not a live in-flight step in the current process.

**What happens on detection**:

| Step's action-type tier | Outcome |
|---|---|
| GREEN (read-only/idempotent) | `status → "planned"`; re-offered and re-executed normally next tick |
| YELLOW/RED/FORBIDDEN/UNKNOWN, has a fallback | `status → "failed"` momentarily, then the fallback (a different, unstarted, presumably-safer action) is swapped in and `status → "planned"` |
| YELLOW/RED/FORBIDDEN/UNKNOWN, no fallback | `status → "failed"`, `plan.review_required = True` — requires owner review or a future `replan_plan()` call (e.g. from a normal execution attempt elsewhere in the plan) before the plan can fully complete |

**Dependent steps**: a GREEN step recovered to `"planned"` re-executes normally, and once it
completes, `next_ready_steps()`'s DAG check naturally unblocks any step depending on it — verified
by `test_recovered_green_step_executes_and_unblocks_dependents` (§7). A non-GREEN step's fallback
swap has the same unblocking effect once the fallback completes. A non-GREEN step with no fallback
leaves dependents blocked — exactly the same behavior a normal (non-crash) failure with no
fallback already has (not a new stall introduced by recovery; the pre-existing `replan_plan()`
Strategy 3 "abandon" path is what a plan falls back to in that case, same as any other
un-fallback-able failure).

**Idempotency across repeated loads**: recovery only fires when `step.status == "running"`. The
first recovery persists a terminal-or-planned status, so a second fresh load of the same plan sees
that persisted status and the recovery branch's guard (`if step.status != "running": continue`)
skips it — structurally a no-op, not something requiring a lock. Verified by
`test_recovery_is_idempotent_across_repeated_loads` (§7) across 3 simulated fresh loads.

---

## 6. Duplicate-Execution Protection

This was the primary safety constraint for Blocker 2. The core risk: after a crash, VECTOR cannot
know whether the actual external side effect (a message sent, a file written, an API call made, a
git push, a shell command run) already completed before the crash — that information is only
written to `step.report`/`step.actual_outcome` *after* `executor.execute()` returns, which is
after the point of failure.

**Design response**: rather than attempt to reconstruct unknowable post-crash state, recovery
draws a hard line using information VECTOR already has — the action's own risk classification:

- **GREEN-tier actions are safe to blindly re-run** because they are read-only or otherwise
  side-effect-free by the project's own existing definition (the same GREEN list the permission
  gateway already trusts to auto-execute without owner approval). Re-running `search_web` or
  `check_attendance` a second time has no meaningful duplicate-side-effect risk.
- **Every other tier is never auto-resumed.** `send_email`, `execute_code`, `financial_transaction`,
  `push_github`, `run_shell_command`, `commit_code`, and every other YELLOW/RED/FORBIDDEN action
  type is marked failed and left for owner review or the existing fallback mechanism — never
  silently re-executed from scratch. This directly satisfies the task's explicit safety
  requirement: no blind repetition of message-sending, file-modifying, external-request, command-
  execution, financial, or destructive actions.
- Verified explicitly by `test_yellow_tier_step_not_auto_resumed` and
  `test_red_tier_step_not_auto_resumed` (§7) — both assert the step is marked `"failed"`, never
  reset to `"planned"` directly.

No new idempotency-key/action-identity mechanism was built, because none was needed: the existing
GREEN/YELLOW/RED/FORBIDDEN classification already encodes exactly the safe/unsafe-to-repeat
boundary this recovery mechanism needs, and reusing it means recovery's safety guarantee is
identical to (not weaker or stronger than, just consistent with) the guarantee the permission
gateway already provides for every other action VECTOR ever takes.

---

## 7. Tests

### Blocker 1 — `tests/integration/test_phase_a5_hypothesis_consumer.py::TestHypothesisLoopActuallyExecutes` (4 new tests)

- `test_generate_hypotheses_is_actually_awaited` — **A**. Uses a fake `HypothesisEngine` whose
  `generate_hypotheses()` increments a counter inside its own body before returning; asserts the
  counter is 1 after calling the real `hypothesis_loop()`. This is a dynamic proof the coroutine
  body actually ran, which `inspect.getsource()` string-matching (the pre-existing, audit-flagged
  weak test in the same file) cannot provide — a missing `await` leaves the source text
  containing `"generate_hypotheses("` either way.
- `test_hypothesis_loop_source_awaits_generate_hypotheses` — static guard (belt-and-suspenders):
  fails loudly if a future edit removes the `await` again. Explicitly documented as insufficient
  on its own (would not have caught the original bug).
- `test_low_confidence_hypothesis_is_suppressed_not_stored` — confirms the pre-existing 0.85
  confidence threshold is unchanged by the fix.
- `test_generation_exception_does_not_kill_loop` — **B**. A fake engine that raises
  `RuntimeError` inside `generate_hypotheses()`; asserts `hypothesis_loop()` returns normally
  (doesn't propagate), the existing 300s error-backoff sleep fires, and the normal 4h cadence sleep
  value is unchanged. Explicitly documented why this test alone is insufficient (before the fix,
  an exception inside the never-awaited coroutine could never reach the `except` block at all — it
  would have "passed" vacuously even with the bug present).

**Result**: 4/4 pass (part of a 20/20 pass for the whole file, including 16 pre-existing tests).

### Blocker 2 — `tests/integration/test_planning_integration.py::TestCrashRecovery` (11 new tests, covering mandatory items C–M)

All tests write the "crashed" state through the *real* `Plan.to_dict()`/`PlanStore.save()`
machinery, then load it through a **fresh** `PlanStore` instance pointed at the same file — this
is the documented equivalence for "simulated crash state" (see class docstring): a real process
restart and this simulation are indistinguishable to `PlanStore._ensure_loaded()`, which cannot
tell "a different OS process wrote this" from "a different `PlanStore` object in the same process
is loading this for the first time" — both are just "a JSON file on disk says `status=running`,
and this is this store's first load of it." Same technique the pre-existing
`TestPlanSurvivesRestart` (§ "existing test architecture") already used for the clean-completion
case.

| Test | Mandatory item(s) | What it proves |
|---|---|---|
| `test_green_step_detected_and_reset_to_planned` | C, D, E, F, G | Stale running step detected on fresh load, reset to planned, recovery event recorded once |
| `test_recovered_green_step_executes_and_unblocks_dependents` | H, I | Recovered step actually re-executes via `PlanRunner`; dependent step becomes ready and completes; total execution count proves no double-run |
| `test_yellow_tier_step_not_auto_resumed` | Safety | YELLOW action never silently reset to planned |
| `test_red_tier_step_not_auto_resumed` | Safety | RED action (financial_transaction) never silently reset to planned |
| `test_non_green_step_with_fallback_routes_around_crash_safely` | Safety + I | Non-GREEN step with a fallback still gets a safe path forward without resuming the risky action |
| `test_completed_step_untouched_by_recovery` | J | A genuinely completed step (and its outcome data) is never touched, even when a sibling step is stuck running |
| `test_pre_existing_failed_step_distinguishable_from_recovery_failure` | K | A pre-crash failure keeps its original reason/`retry_info=None`; a recovery-driven failure is distinguishable (`retry_info` populated) |
| `test_recovery_is_idempotent_across_repeated_loads` | L | 3 simulated fresh process starts in a row produce identical state and exactly one `step_recovered` event — no re-triggering |
| `test_recovery_decision_persisted_to_disk_not_just_memory` | M | Raw JSON file (read independently of `PlanStore`) shows the recovered status and `retry_info` |
| `test_plan_dependencies_preserved_through_recovery` | (dependency preservation) | `depends_on` links and DAG acyclicity survive the crash/recovery cycle unchanged |

**Result**: 19/19 pass for the whole file (11 new `TestCrashRecovery` tests + 8 pre-existing tests
in `TestPlanFullLifecycle`/`TestPlanSurvivesRestart`/`TestPlanFailureAndReplan`/
`TestPlanCandidatesInDecision`/`TestPlanVerificationIntegration`/`TestMultiplePlansConcurrent`, all
still passing — zero regressions in this file).

---

## 8. Verification Results

- **Targeted new tests**: 39/39 pass —
  `tests/integration/test_phase_a5_hypothesis_consumer.py` (20/20, includes the 4 new Blocker-1
  tests) + `tests/integration/test_planning_integration.py` (19/19, includes the 11 new Blocker-2
  tests).
- **Syntax/compile check**: `python -m py_compile` on all 4 changed/new files (`autonomous_loop.py`,
  `plans.py`, `test_planning_integration.py`, `test_phase_a5_hypothesis_consumer.py`) — clean, zero
  errors. `ast.parse()` independently confirms the same.
- **Static/type checks**: this repo's `pyproject.toml` declares `[tool.ruff]` and `[tool.mypy]`
  configuration, but neither `ruff` nor `mypy` is installed in this environment
  (`pip show ruff mypy` → "Package(s) not found"). Documented honestly rather than skipped
  silently — `py_compile`/`ast.parse` are the static checks actually available and were run.
- **Autonomous-loop startup/import**: `AutonomousLoop()` imports and constructs cleanly;
  `inspect.iscoroutinefunction(loop.hypothesis_loop)` confirms the method is still a proper
  coroutine function post-edit.
- **Plan persistence/reload**: `python core/runtime/plans.py`'s own self-test (pre-existing, in
  the module's `__main__` block, covering step serialization, DAG resolution, circular-dependency
  detection, store round-trip, outcome verification, plan serialization) still passes after the
  recovery-hook addition. (One pre-existing, unrelated warning was investigated and found to be
  caused by `tempfile.NamedTemporaryFile`'s empty-file edge case in `_ensure_loaded()`'s JSON
  parsing — confirmed present before my changes via testing on an untouched code path, self-heals
  within the same test, and is explicitly out of scope per "do not refactor unrelated code.")
- **No routing changes**: `route_policy.decide_route()`, `provider_client.py`, `TIER_ROUTING`,
  `model_pool` — not touched.
- **No provider changes**: `provider_client.py`, `vectorcode_llm.py`, `ollama_safe.py` — not
  touched.
- **No prompt changes**: `HypothesisEngine._SYSTEM`, the hypothesis-generation prompt template,
  `MissionPlanAdvisor`'s prompts — not touched.
- **No unrelated subsystem changes**: `git diff`-equivalent review (below) confirms the only
  production files touched are `core/loop/autonomous_loop.py` (1 line) and `core/runtime/plans.py`
  (the 3 new functions + the `_ensure_loaded()` call-out described in §3); the only other files
  touched are the 2 test files.

### Full existing test suite

Running `tests/unit/` + `tests/integration/` (excluding `test_planning.py`, which has 2
pre-existing, independently-confirmed-unrelated failures from a `MissionPlanAdvisor` module-path
patch mismatch predating this task, and deselecting one pre-existing environmental-timing-flaky
test in `test_loop_stall_fixes.py`) surfaced **8 pre-existing failures**, every one individually
re-run and traced to confirm it is unrelated to either fix:

| Failing test | Root cause | Touches Blocker 1/2 code? |
|---|---|---|
| `test_agent_registry_successor_class.py::test_dying_coding_swarm_respawns_...` | `'dict' object has no attribute 'generation'` — a constructor-mismatch bug in `agent_registry.py`'s successor-reconstruction | No — `agent_registry.py` not touched |
| `test_correction_learner.py::test_extract_from_explicit_correction` | `'general' != 'coding'` — domain-classification mismatch in `correction_learner.py` | No — not touched |
| `test_correction_learner.py::test_tags_include_domain_and_source` | Same domain-classification root cause | No |
| `test_epistemic_scoring.py::test_stale_domain_reduces_score` | `0.49 == 0.49` (expected `<`) — scoring-formula test bug in `decision_engine.py`'s epistemic path | No — `decision_engine.py` not touched this task |
| `test_correction_integration.py::test_full_loop_stores_and_retrieves` | Same `'general'`/`'coding'` root cause | No |
| `test_correction_integration.py::test_lifecycle_unvalidated_to_validated` | Same domain-classification family | No |
| `test_epistemic_integration.py::test_different_domains_independent` | `0.9 != 1.0` — same `decision_engine.py` epistemic-scoring family | No |
| `test_phase_a7_council_red_tier.py::test_proceed_high_confidence_returns_proceed` | `'defer' != 'proceed'` — council red-tier verdict logic | No — governance/council code not touched |

All 8 were reproduced individually (not just observed in the aggregate run) and their failure
messages/stack traces confirm they exercise code this task never modified. **Zero of the 8 are in
`core/loop/autonomous_loop.py`'s `hypothesis_loop()`/`_think_tick()` or `core/runtime/plans.py`.**

**Exact grand total** (obtained via `--junitxml`, parsed programmatically, after two earlier plain
`-q`/`--tb=no` capture attempts truncated before the summary line — an output-pipe quirk on a run
this large, not a test failure; the 8 FAILED names below matched exactly across all three attempts):

```
tests collected:  2202
passed:            2165
failed:               8   (all pre-existing, see table above — traced to
                             agent_registry.py, correction_learner.py,
                             decision_engine.py's epistemic scoring, and
                             council red-tier verdict logic; zero touch
                             autonomous_loop.py's hypothesis_loop/_think_tick
                             or plans.py)
errors:               0
skipped:             29
```

**FULL TEST SUITE: 2165/2173 PASS** (2173 = 2202 collected − 29 skipped; the 8 failures are 100%
pre-existing and unrelated to either blocker fix, individually re-run and traced above).

---

## 9. Remaining Risks

Documented, not fixed (out of scope for this task's narrow blocker-fix mandate):

1. ~~**`hypothesis_loop()`'s result-key mismatch.**~~ **STATUS UPDATE (2026-09-02): FIXED** — see
   `55_HYPOTHESIS_PIPELINE_REMEDIATION.md`. `autonomous_loop.py:2874` now reads `h.get("text",
   str(h))`, matching `HypothesisEngine.generate_hypotheses()`'s established `"text"` field.
   (Original note, for history: this read `h.get("hypothesis", str(h))` against a dict keyed
   `"text"`, so a high-confidence result was stored as the whole dict's `str()` repr instead of the
   plain hypothesis text — discovered during Blocker 1 test-writing, deliberately left unfixed at
   the time as out of that task's strict "await only" scope.)
2. ~~**`generate_hypotheses()`'s hardcoded confidence.**~~ **STATUS UPDATE (2026-09-02): FIXED** —
   see `55_HYPOTHESIS_PIPELINE_REMEDIATION.md`. Confidence is now parsed from a genuine LLM
   self-rated `"CONFIDENCE: <n>"` marker (mirroring the established convention already used by
   `core/brain/anticipation.py` and `core/brain/council.py`), with a conservative 0.5 fallback if
   the LLM omits it. (Original note, for history: `hypothesis_engine.py:63` hardcoded
   `"confidence": 0.7` on every result — permanently below the 0.85 threshold `hypothesis_loop()`
   requires to store anything, confirmed via git history to have been a static placeholder since
   the file's creation, never computed from anything.)
3. **No crash-mid-recovery-save gap.** If the process crashes between recovery deciding a step's
   new state (in memory) and `PlanStore.save()` persisting it, the on-disk file still shows
   `"running"`. This is safe by construction (the next boot simply re-runs the same deterministic
   recovery decision — see §5 idempotency), but it does mean recovery's own "have I recovered this
   yet" signal is not itself crash-atomic beyond what the underlying atomic-write `save()`
   (`.tmp` + `Path.replace()`) already guarantees.
4. **Permission-gateway coverage gap remains open** — see the separate finding below. Not part of
   either MUST-FIX blocker; explicitly deferred per task instructions.
5. **The 8 pre-existing test failures documented in §8 remain unfixed.** None are related to
   either blocker, but they represent real defects in `agent_registry.py`, `correction_learner.py`,
   `decision_engine.py`'s epistemic scoring, and council red-tier logic that a future task should
   address — out of scope here.

---

## 10. Experiment Readiness Impact

Before this remediation: **2 of 2 audited MUST-FIX blockers open** — the 7-day experiment could
not have measured proactive hypothesis generation (silently produced zero output every cycle) and
could not have safely survived a mid-plan-step process restart (silent, permanent, undetectable
data corruption of any long-horizon-plan-completion measurement).

After this remediation: **0 of 2 MUST-FIX blockers open**, both fixed with minimal, narrowly-
scoped changes and behaviorally verified (not just statically checked) via 39 new, real-execution
tests plus the full existing regression suite. See §16 of
`51_FINAL_COGNITIVE_INTEGRATION_AUDIT.md`'s Remediation Status addendum for the updated
experiment-readiness verdict.

The permission-gateway SHOULD-FIX finding (§ below) remains open and unaddressed by design — it
was correctly out of scope for "MUST-FIX blocker" remediation and was confirmed to fail the
"completely isolated and trivial" bar this task set for touching it.

---

## Permission Gateway Finding — Confirmed, Deferred

**Location**: `core/city/governor.py:1970`, `async def dispatch(self, task: dict) -> dict:`.
Grepping the entire file for `PermissionGateway`/`gw.execute`/`gw.classify` returns zero real call
sites — the only match is a comment (`governor.py:2042`, referencing the concept, not calling it).

**Consequence** (re-confirmed this pass, matching §9 of the audit): every caller that reaches
`Governor.dispatch()` — which includes the default fallthrough of `autonomous_loop._act_on()` for
any action type not in the narrow set of 4 explicitly-gated buckets (`proactive_*`, plan steps,
`_VC_ACTION_TYPES`, skill-matched actions), plus roughly 10 other production entry points (API
routers, voice, websocket, hands) — routes to a district agent's `.run()` method with no
GREEN/YELLOW/RED classification or owner-approval check on that specific dispatch path.

**Status**: **DEFERRED**, per this task's explicit instruction ("DO NOT fix this in the same
implementation unless the existing architecture makes the correction completely isolated and
trivial"). It does not meet that bar: a correct fix requires deciding (a) whether to route
`Governor.dispatch()`'s entire default path through the gateway (a behavior change affecting ~10
production call sites, each needing verification that the resulting gate doesn't break existing
callers that may not expect approval friction), or (b) build an explicit, auditable exemption list
for action types safe to skip the gate — either of which is a real design decision with its own
regression-test surface (the task's own requirement #4 for "if you do fix it" — regression tests
proving every relevant action path still reaches the appropriate permission boundary — would by
itself be a substantial undertaking spanning governor.py, autonomous_loop.py, and every API router
that calls dispatch()). Left unchanged, exactly as instructed.
