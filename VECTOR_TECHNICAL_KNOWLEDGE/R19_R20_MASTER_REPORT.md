# R19 → R20 Master Report

## 1. Authoritative HEAD

- Starting HEAD (verified directly, not trusted from any prior report): `193a33e30bb8f23b5106a95114dc2ba897a4c308` (branch `production-hardening-complete`, clean working tree, one worktree, no VECTOR autonomous process running — confirmed via `git status`/`git worktree list`/`Get-CimInstance Win32_Process`).
- Confirms R18-EQ's two commits (`72e053879`, `193a33e30`) are the real, current tip.
- See `VECTOR_TECHNICAL_KNOWLEDGE/R19_R20_ORCHESTRATOR_LEDGER.md` for the full phase-by-phase trace (7 parallel Phase 1 investigators, synthesis, implementation, verification).

## 2. Architecture Discovered (Phase 1 synthesis)

Seven independent, parallel read-only investigators (Agents A–G) audited: startups/content-district capability composition candidates, the real `PlanStore`/`PlanRunner` planning machinery, the Candidate/DecisionEngine/PolicyMemory/R6/epistemic learning layer, the Equation goals' doctrine semantics, safety/authorization of composition paths, runtime/persistence characteristics, and adversarially re-evaluated the whole proposition. Full findings are recorded in the ledger. Key discoveries:

- `core/runtime/plans.py`'s `Plan`/`PlanStep`/`PlanStore`/`PlanRunner` (from an earlier, pre-R19 milestone) already provide real DAG-dependency gating (`next_ready_steps()`), real crash/stale-step/retry recovery, and native `Candidate` integration (`AutonomousLoop._get_plan_candidates()` — the same `DecisionEngine.evaluate()` path every other candidate uses, not a parallel system).
- `PlanRunner`'s real execution backend (`AutonomousExecutor` → `PermissionGateway.execute()` → `_execute_action()`) is a **stronger** per-step gate than the native `_act_on()` generic fallback R18-EQ exercised — it genuinely calls `classify()` and enforces FORBIDDEN/YELLOW/RED, not merely GREEN pass-through.
- `_execute_action()` had **no generic dispatch-to-Governor path** for an arbitrary action_type — only `hand_`-prefixed actions reached `Governor().dispatch()`; everything else returned `not_implemented`, even though the exact same action_type already worked via `_act_on()`'s OTHER (native goal candidate) path.
- No step-to-step real data-handoff mechanism existed anywhere in the codebase (a step's `params` were fixed at plan-creation time; a completed step's real result was discarded, never read back).
- A real pre-existing vulnerability CLASS exists elsewhere (`Governor._maybe_decompose()`, splits certain task types into subtasks dispatched recursively inside one top-level permission check) — R19 was explicitly designed to never resemble this pattern.

## 3. R19 Capability Gap

`g_first_revenue`'s two R18-EQ strategies (`script`, `idea_validate`) were fully independent — no goal state ever advanced from one real action's real output to a second, dependent real action. Three startups-district composition candidates (`idea_validate`→`script`, `idea_validate`→`market_scan`, `idea_validate`→`revenue_model`) were proposed and adversarially rejected (Phase 1 Agent G, independently re-confirmed by Agent A): each is a "coincidental string pass-through" (e.g. `idea_name`→`topic`/`niche`), never genuinely consuming the first step's real analysis (`verdict`/`scores`/`pros`/`cons`), or (for `revenue_model`) has an outright key/field mismatch plus zero real routing.

## 4. R19 Selected Solution

`g_first_revenue`: `script` → `schedule_post`, represented via a real, deterministic (no LLM) 2-step `Plan`, executed through the pre-existing `PlanRunner`/DAG machinery. Doctrine-grounded (`Blueprint/(C) The Real Blueprint` Part 4 names exactly this pipeline as the wedge's 90-day plan) and adversarially confirmed as genuine structural composition, not cosmetic: `ScriptGenerator.generate_script()`'s real `content` field is the actual, load-bearing payload `ContentScheduler.schedule_post()` needs — a schedule_post call without it would be degenerate.

Three narrow, precedented gaps closed (same "real capability, missing wiring" class R18-EQ fixed twice):
1. `core/config.py`: `"schedule_post"` added to GREEN.
2. `core/loop/permission_gateway.py::_execute_action()`: one new narrow `elif` branch (`_PLAN_COMPOSABLE_ACTION_TYPES = {"script","schedule_post"}`, mirrors the existing `hand_` block) so `PlanRunner`'s real execution backend can reach `Governor().dispatch()` for these two action_types.
3. `core/runtime/plans.py`: (a) `PlanStep.param_bindings: dict[str,str]` — explicit, declared, dispatch-time-resolved references to a real completed dependency's real output field; (b) `step.actual_outcome["result"]` now additively preserves the real handler's real structured result (previously discarded); (c) `build_wedge_content_plan()` — a deterministic, reusable, generic (parameterized by `goal_id`/`topic`, never hard-codes a specific goal id) 2-step builder.

**Explicitly not done**: no automatic goal-seed-time plan-creation wiring into `goal_system.py` (the plan is constructed via real, unmodified `Plan`/`PlanStep`/`PlanStore` classes, called explicitly — same methodological precedent as R11–R18's `GoalSystem.__new__` bypass pattern). No new district, no new handler, no new action_type — both `script` and `schedule_post` pre-existed R19.

## 5. R19 BEFORE/AFTER

**BEFORE**: `g_first_revenue` could propose `script` and `schedule_post` only as fully independent, isolated actions — no mechanism existed for `schedule_post`'s real dispatch to ever receive `script`'s real generated content (params were static, fixed at any hypothetical plan-creation time, and no code read a completed step's result back). `PlanRunner.execute_step()` for either action_type would have returned `not_implemented` (no dispatch path existed in `_execute_action()` for non-`hand_` action_types).

**AFTER**: A real, deterministic 2-step `Plan` DAG-gates `schedule_post` behind `script`'s real completion; `_resolve_step_params()` threads `script`'s real `content` output into `schedule_post`'s real dispatch params at execution time; both action_types now reach `Governor().dispatch()` via the new `_execute_action()` branch.

**PROOF** (flagship test, real passing run, 43.2s including one real LLM call):
```
Cycle 1: _get_plan_candidates() -> [Candidate(action_type="script", source="plan:...:step-1")]
DecisionEngine.evaluate() -> real winner (is-identical to the candidate object)
AutonomousLoop._act_on() -> _act_on_plan_step() -> PlanRunner.execute_step()
-> real Governor.dispatch() -> real ScriptGenerator.run() -> real LLM call
-> step-1.actual_outcome["result"]["content"] = <real generated script text>
-> real PolicyMemory score written (!= DEFAULT_SCORE)

Cycle 2: _get_plan_candidates() -> [Candidate(action_type="schedule_post", ...)]
  (schedule_post only becomes ready NOW -- step-1 DAG-gated it)
DecisionEngine.evaluate() -> real winner
AutonomousLoop._act_on() -> _act_on_plan_step() -> PlanRunner.execute_step()
-> _resolve_step_params() reads step-1's REAL content
-> real Governor.dispatch() -> real ContentScheduler.schedule_post()
-> step-2.actual_outcome["result"]["params"]["content"] == step-1's real content
   (byte-identical assertion -- proves genuine structural handoff)
-> real local PostJob row created (job_ids present)
-> real PolicyMemory score written (!= DEFAULT_SCORE)

plan.status == "completed", plan.progress == 1.0
Restart: PlanStore reload recovers both real actual_outcome dicts unchanged;
PolicyMemory scores survive a real close_db_connection()+reopen.
```

## 6. R19 Production Path

```
build_wedge_content_plan(goal_id, topic)          [real, deterministic, no LLM]
  -> real PlanStore.add(plan)
AutonomousLoop._get_plan_candidates()               [real, unmodified production method]
  -> real Candidate (source="plan:<id>:<step>")
DecisionEngine.evaluate()                            [real, same path every candidate uses]
  -> real winner, real decision_id/candidate_id
AutonomousLoop._act_on(winner)
  -> winner.source.startswith("plan:") -> _act_on_plan_step(winner)
  -> PlanRunner.execute_step(plan, step)
     -> _resolve_step_params(plan, step)              [R19: real dependency-output resolution]
     -> AutonomousExecutor.execute(action_type, params)
        -> PermissionGateway.execute(Action(...))
           -> FORBIDDEN check -> capability check -> GREEN/YELLOW/RED tier routing
           -> _execute_action()
              -> action_type in _PLAN_COMPOSABLE_ACTION_TYPES   [R19: new branch]
                 -> Governor().dispatch({"type":..., "params":...})
                    -> DISTRICT_TASK_MAP exact match -> real district agent .run()
     -> step.actual_outcome["result"] = real handler result     [R19: preserved, was discarded]
  -> real PolicyMemory.update_from_outcome() under the canonical make_situation_hash()
```

No parallel decision system, no plan-only DecisionEngine, no hard-coded winner, no manual Candidate injection — confirmed by direct source reading and by the flagship test's `is`-identity assertions.

## 7. R19 Tests

`tests/test_r19_capability_composition.py` — 20 tests, mapped to the mission's A–O categories:

| Category | Test(s) |
|---|---|
| A/B. Goal discovery + composition construction | `TestCompositionConstruction` (4 tests) |
| C/D. Dependency/order + data handoff | `TestDependencyAndDataHandoff` (4 tests, incl. malformed-input category M) |
| E/F. Candidate + DecisionEngine integration | `TestCandidateAndDecisionIntegration` (2 tests) |
| G/H. Governor + permission verification | `TestGovernorAndPermission` (5 tests, incl. category O adversarial-composition checks) |
| I/J/K/L. Real execution, intermediate/final output, persistence | `TestFlagshipRealComposition` (1 flagship test, real LLM call) |
| Safety | `TestSafety` (3 tests) |

**Result**: 20/20 pass (19 fast, ≤8s total; 1 flagship, real LLM call, 43.2s).

## 8. R19 Safety

- `schedule_post` classified GREEN — verified safe by direct source read: `ContentScheduler.schedule_post()` only creates a local `PostJob` row via `PostJobTracker.create()` (SQLite, zero network call). The actual external, irreversible publish (`ContentScheduler.run_pending()`) is a SEPARATE method behind its OWN, already-RED `content_publish` action_type requiring real `PermissionGateway` owner approval, fail-closed on gateway error — `schedule_post`'s dispatch path never reaches it (confirmed: `test_run_pending_remains_the_only_publish_path_and_stays_gated`).
- New `_PLAN_COMPOSABLE_ACTION_TYPES` branch is narrowly scoped (exactly `{"script","schedule_post"}`, never any RED action_type — asserted in `test_plan_composable_action_types_narrowly_scoped`) and is reached only downstream of `execute()`'s FORBIDDEN check and GREEN/YELLOW/RED tier routing (source-level assertion).
- `PlanRunner.execute_step()` dispatches exactly ONE real action per call (`test_no_maybe_decompose_style_bundling` — source-level count of `executor.execute(` calls == 1) — never resembles `Governor._maybe_decompose()`'s real, pre-existing "one top-level permission check, multiple real sub-dispatches" pattern.
- Each plan step gets its own real, independent `Candidate`/decision cycle/`_act_on()` call/`PermissionGateway.execute()` call — never bundled behind a single check (satisfies the mandatory Phase 1 Agent E safety requirement).

## 9. R19 Adversarial Review

A fresh, independent, read-only agent (no prior context, no stake) was launched to try to disprove all 10 required R19 claims. It read the full diff itself, read both real handlers end-to-end, traced the full dispatch chain (`PlanRunner.execute_step` → `_resolve_step_params` → `AutonomousExecutor.execute` → `PermissionGateway.execute` → `_execute_action` → `Governor.dispatch` → real handler → back up), read the full 545-line test file, and live-ran the 19 fast tests (19 passed, 1 deselected — the flagship, correctly not re-run per instruction to avoid a redundant real LLM call).

**Verdict: all 10 claims CONFIRMED, zero disproven.** One claim (#7, "no fake outcome") required active tracing rather than a surface read — the reviewer initially suspected `step.actual_outcome["result"]["params"]["content"]` (asserted byte-identical to step-1's real content in the flagship) might never actually populate, since neither `Governor.dispatch()`'s return dict nor `ContentScheduler.schedule_post()`'s return dict contains a `"params"` key by itself. Tracing further, `_execute_action()` initializes `result = {"status":..., "action":..., "params": action.params, ...}` **before** the new `_PLAN_COMPOSABLE_ACTION_TYPES` branch runs, and that branch's `result.update(dispatch_result)` does not clobber the pre-seeded `"params"` key (the district handler's own return dict has no `"params"` key to collide with) — so the real resolved params (including the real, handed-off `content`) do correctly survive to `step.actual_outcome["result"]["params"]["content"]`. Confirmed, not merely assumed.

No experimenter steering was found (zero `bias_toward`/manual-confidence calls; the reviewer additionally noted steering is structurally moot here since the DAG never presents more than one ready candidate at a time — R19 demonstrates dependency-gated sequencing, not competitive selection among alternatives, which is R20's separate concern). No goal-ID curve-fitting (zero occurrences of the literal string `"g_first_revenue"` in any of the three modified production files). `content_publish` (the real external-publish action_type) confirmed untouched and still RED. `schedule_post()` confirmed to contain zero network/subprocess/shell code.

**Overall verdict: PASS.** *(Process note: the first independent-review attempt failed with a session rate-limit error before producing any findings — a Claude Code API/session-limit event unrelated to R19's own correctness, not a review result. The retry above is the actual, complete, independent review this gate required; no self-review substitution was needed.)*

## 10. R19 Commit

See the final status block at the end of this report for the commit hash, recorded after commit.
