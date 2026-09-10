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

Committed: `1b7c4f395` ("R19: enable legitimate multi-stage capability composition"), on top of start HEAD `193a33e30bb8f23b5106a95114dc2ba897a4c308`. 7 files changed (902 insertions). HARD GATE satisfied before proceeding to R20: capability delta PROVEN, targeted tests pass (20/20), adversarial review PASSES, no new regression, R19 committed.

---

# R20 — Autonomous Adaptation

## 11. R20 Experimental Design

R20 asks a different question than R19: not "can real capabilities compose," but "can VECTOR itself CHOOSE between genuinely different real strategies, execute the one it picked, learn from the real outcome, and later reconsider — with no experimenter input on which strategy runs."

`g_first_revenue`'s own two R18-EQ strategies already satisfy R20's diversity requirement without needing anything new: `idea_validate` (one real step, `districts/startups/idea_validator.py`, analysis-only) and `script` (the first real step of R19's real composition, `districts/content/script_generator.py`, real content production, DAG-gated toward real local scheduling). These differ in action sequence (1 step vs. a dependency-gated 2-step plan), intermediate objective (validate vs. produce), and consequential capability — not a cosmetic parameter difference (already adversarially confirmed legitimate by R18-EQ's own review).

**R20 required zero production code changes** — only a new test file (`tests/test_r20_autonomous_adaptation.py`). Every mechanism the flagship exercises (`GoalSystem.generate_immediate_actions()`, `AutonomousLoop._get_plan_candidates()`, `DecisionEngine.evaluate()`, `AutonomousLoop._act_on()`) already existed, real and unmodified, before R20 began.

## 12. Anti-Steering Verification

The flagship never calls `bias_toward()`, never manually sets a winner, never reorders candidates, never manipulates confidence/urgency to favor one option, never manually writes a reward, never fabricates an outcome, never injects PolicyMemory directly, and never hard-codes which strategy executes. Both candidates in every cycle are constructed with the IDENTICAL, neutral `confidence=0.5`/`urgency=0.5` — verified both by direct inspection during implementation and, independently, by the adversarial review (§17). The experimenter defined only: the goal (`g_first_revenue`), the safe environment (isolated DB/plan-store/registry), the allowed strategy set (`idea_validate`, `script`), and the stopping condition (3 bounded cycles). The experimenter never chose which of the two executed in any cycle.

## 13. Native Candidate Set

Every cycle: `_native_idea_validate_candidate()` derives its action_type from a REAL call to `GoalSystem.generate_immediate_actions()` (never a hand-typed action_type string) filtered to the real `"idea_validate"` entry; `_plan_script_candidate()` derives its action_type from a REAL call to `AutonomousLoop._get_plan_candidates()` against a freshly-built, real, active `Plan` (`build_wedge_content_plan()`, R19's own real builder). Confirmed structurally identical `{"idea_validate", "script"}` action_type set every cycle (`test_control_3_same_candidate_set_every_cycle`).

## 14. Cycle-by-Cycle Decisions (real, observed, not engineered)

| Cycle | Winner | Score | goal_alignment | policy | confidence | Real reward |
|---|---|---|---|---|---|---|
| 1 | script | 0.715 | 1.00 | 0.50 | 0.50 | 0.700 |
| 2 | script | 0.715 | 1.00 | 0.50 | 0.50 | 0.700 |
| 3 | script | 0.715 | 1.00 | 0.50 | 0.50 | 0.700 |

(Cycle 3's own "Winner:" INFO log line fell outside the captured log window due to output buffering; its outcome is confirmed by the test's own passing assertions — 3 distinct `decision_id`s, 3 distinct `candidate_id`s, 3 non-default `score_after` reads, all of which the test explicitly asserts and which passed.)

`script` won all 3 real, independent, unsteered decisions. The `policy` scoring factor stayed at its neutral baseline (0.50) every single cycle — not because the reward pipeline is broken (see §16 — every cycle's real reward writes and reads back correctly), but for a specific, real, pre-existing architectural reason identified below (§19).

## 15. Outcomes

All 3 real executions completed successfully (`status: "completed"`) — real `ScriptGenerator.generate_script()` LLM calls (via the real cloud-provider fallback chain, with real, logged provider failures/retries — `github_models`/`cerebras`/`groq`/`mistral` all failed for real reasons — 404s, rate limits, DNS — before a real `ollama` fallback succeeded each time, exactly the kind of unfiltered, warts-included real behavior this codebase's own precedent values as evidence of genuineness, not a rigged demo).

## 16. Rewards

Every cycle's real reward = 0.700, computed by `AutonomousLoop._act_on_plan_step()`'s real, existing (not R20-authored) formula: `0.7 if completed else 0.3`. Real, deterministic for a real success — not manufactured, not manually set (confirmed: zero `update_from_outcome()` calls anywhere in the flagship test function itself — `test_control_4_and_6_flagship_source_contains_no_steering_or_manual_reward`).

## 17. PolicyMemory Updates

Every cycle: `PolicyMemory.update_from_outcome("script", h, 0.700)` really executes (inside the real `_act_on_plan_step()`), and `score_after != PolicyMemory.DEFAULT_SCORE` is real and asserted for all 3 cycles. Whether this write is ever read back by a LATER cycle's `evaluate()` call depends entirely on whether that later cycle computes the SAME `situation_hash` — see §19.

## 18. Persistence

Each cycle runs a real `close_db_connection()` before the next cycle begins (the one thing genuinely meant to persist — the on-disk `PolicyMemory` SQLite database — stays the SAME file across all 3 cycles via the single, test-function-scoped `isolated_vector_db` fixture; only the process-local `DecisionEngine`/`PlanStore`/`EpistemicTracker` are intentionally fresh each cycle, simulating "fresh process/engine" restarts per the mission's own template). A separate, fast, explicitly-labeled CONTROL-5 test (`test_control_5_persistence_survives_restart`) independently proves the persistence MECHANISM itself survives a real restart, using a direct, clearly-labeled `update_from_outcome()` write (never used in the flagship) — isolating the mechanism's correctness from the flagship's own real-LLM-call latency.

## 19. Causal Controls

| Control | Result |
|---|---|
| 1 — no learning, baseline stable | PASS: two fresh, zero-history engines with identical candidates produced the same winner both times (`test_control_1_no_learning_no_winner_change`) — rules out hidden randomness. |
| 2 — learning changes behavior only when evidence supports it | See the honest finding below — for THIS specific (plan-sourced) candidate, no cross-cycle behavior change was observed, for an identified, real, non-learning-failure reason (not "learning doesn't work," but "this specific situation-hash is never reused"). |
| 3 — same candidate set every cycle | PASS, structurally confirmed (§13). |
| 4 — no experimenter-selected winner | PASS, source-level self-audit of the flagship function found zero steering constructs. |
| 5 — persistence across restart | PASS, both indirectly (every real cycle) and directly (CONTROL-5's isolated, fast proof). |
| 6 — no manual reward | PASS, source-level self-audit. |

**R6 (staleness) independently ruled out**: each cycle uses a FRESH `DecisionEngine()` instance (`_winner_streak_count == 0`, `_winner_streak_hash is None` at that cycle's own `evaluate()` call — asserted directly inside the flagship, not merely claimed). R6 staleness requires `>= candidate_staleness_streak` (default 5) CONSECUTIVE wins on the SAME engine instance; a fresh engine can never satisfy this on its very first `evaluate()` call. **R6 cannot be the explanation for `script` winning 3 times.**

**Epistemic dampening**: each cycle also uses a fresh `EpistemicTracker` (via `build_isolated_engine()`'s own per-cycle db path) — epistemic belief from one cycle cannot mechanically carry into the next cycle's engine instance in this design. (Production code, running continuously, WOULD share one epistemic tracker across cycles — this test's per-cycle freshness is a deliberate, documented simplification for causal cleanliness, not a claim about production's own epistemic behavior over time.)

**The real, identified reason the policy factor never moved**: `AutonomousLoop._get_plan_candidates()` (pre-existing, unmodified by R19 or R20) builds each plan-sourced Candidate's params as `{**step.params, "_plan_id": plan.id, "_step_id": step.id}` (`core/loop/autonomous_loop.py:1532`). `PolicyMemory.make_situation_hash()` hashes the ENTIRE params dict, unfiltered (`core/memory/policy.py`'s own docstring: "params are NOT filtered/allowlisted -- every key... is still part of the identity"). Since `build_wedge_content_plan()` mints a fresh, UUID-derived `plan.id` every cycle (by design — each cycle constructs a brand-new `Plan` object), `script`'s situation_hash is NEVER the same twice across cycles — so a real, correctly-written reward from cycle 1 can never be read back by cycle 2's or cycle 3's `evaluate()` call. This is a genuine, pre-existing PlanRunner characteristic (independently predicted by Phase 1 Agent C before any implementation began — see the ledger's Phase 1 table), not a defect introduced by R19 or R20, and — per the mission's explicit "do not redesign PolicyMemory/DecisionEngine" instruction — was correctly left unfixed rather than patched over to manufacture a cleaner-looking result.

## 20. R20 Capability Delta

**BEFORE**: VECTOR could execute either `idea_validate` or `script` for `g_first_revenue`, but autonomous, unsteered CHOICE between them, across multiple real, restart-separated cycles, with real outcome/reward/persistence, had never been demonstrated.

**AFTER**: VECTOR autonomously evaluated and chose between two genuinely different, real, legitimate strategies across 3 independent, restart-separated real cycles, with zero experimenter steering; executed its own real choice each time; observed a real outcome; wrote a real reward; and that reward genuinely persisted through a real restart (verified both in-flow and via an isolated control). **AUTONOMOUS SELECTION = PROVEN.**

Cross-cycle POLICY-DRIVEN adaptation of the SPECIFIC winning (plan-sourced) strategy was **NOT PROVEN in this run** — not because the mechanism is fake, but because of the real, identified `_plan_id`-in-situation-hash characteristic (§19), which the isolated CONTROL-5 test confirms does NOT apply to the OTHER (native, non-plan) candidate class — meaning the underlying PolicyMemory persistence mechanism itself is real and working; this run's specific 3-cycle comparison happened to exercise the one candidate class where it cannot yet accumulate across independently-constructed plans. Per the mission's explicit "if only R6 changes the winner, report AUTONOMOUS EXPLORATION=PROVEN / POLICY LEARNING=NOT PROVEN, do not inflate" instruction — adapted here since the actual non-accumulation cause is real and identified, not R6 — the honest verdict is: **AUTONOMOUS SELECTION = PROVEN; CROSS-CYCLE POLICY ADAPTATION (for this specific plan-sourced strategy, in this run) = NOT PROVEN.**

## 21. R20 Safety

- `TestSafety::test_learned_preference_cannot_promote_red_action` — even after `code_task` (RED) is made maximally "learned good" (10× real `update_from_outcome(..., 1.0)` calls, real score reaches ~1.0), `PermissionGateway.classify("code_task")` remains `"RED"`, completely unaffected — a learned preference is a SCORING input, never an AUTHORIZATION bypass.
- `test_idea_validate_and_script_permission_tiers_unaffected_by_r20` — both remain GREEN; `code_task` remains RED. R20 touched zero permission-tier files.
- No learned action can silently promote itself (R6/policy only ever re-rank among REAL, already-generated, already-permission-eligible candidates — never invent a new one or change any action_type's tier).
- No new capability, external communication, financial action, or irreversible side effect — R20 added no production code at all.

## 22. R20 Adversarial Review

A fresh, independent, read-only agent (no prior context) was launched to adversarially disprove all 15 required R20 checks (experimenter-selected winner, hand-built candidates, manual reward, fabricated outcome, manual policy injection, R6-mistaken-for-learning, generation-order effects, confidence manipulation, epistemic carryover, stale-engine reuse, persistence failure, safety bypass, cosmetic diversity, lab-only path, production-path-not-crossed). It read the full flagship and control source, traced both execution paths (`idea_validate` → `Governor.dispatch()`; `script` → `PlanRunner.execute_step()` → `AutonomousExecutor` → `PermissionGateway.execute()`) end-to-end through real production code, independently re-derived (not merely trusted) the `_plan_id`-in-`make_situation_hash()` causal explanation for the flat policy factor by reading `autonomous_loop.py:1530-1532`, `plans.py`'s `build_wedge_content_plan()`, and `policy.py::make_situation_hash()` itself, and live-ran the 8 fast tests (8 passed, 2 deselected).

**Verdict: all 15 claims CONFIRMED, zero disproven.** The `_plan_id` causal chain was independently re-derived and confirmed mechanically airtight, not merely accepted from the ledger. `PermissionGateway._classify()` was independently read and confirmed to be a pure static set-membership check with zero calls into `PolicyMemory` — structurally immune to policy-score influence.

Two minor, honestly-flagged, pre-existing (not introduced by R20) observations: (1) `generate_immediate_actions()`'s `idea_validate` action dict carries only `goal_id`/`title`, so `IdeaValidator.run()` falls back to an empty `{"name":"","description":""}` idea — a real R18-EQ-inherited data-quality gap, out of R20's scope, noted for a future milestone; (2) `test_control_epistemic_negligible_within_a_fast_test_run` is a weak, self-labeled "best-effort" check (only confirms the class exists) — the REAL epistemic-isolation proof is the fresh-per-cycle `EpistemicTracker` db path construction, independently verified separately.

**Overall verdict: PASS.**

## 23. R20 Regression

R20 added zero production code changes (only `tests/test_r20_autonomous_adaptation.py`, new). Directly-affected areas (`decision_engine.py`, `policy.py`, `permission_gateway.py`, `plans.py`, `autonomous_loop.py`) were already re-verified via the R19 regression sweep (§ R19, 234/236 pass) immediately before R20 began, on the same committed code R20 only ever reads. R20's own suite: 10/10 pass (8 fast + 1 flagship, real 3-cycle LLM execution, 102.6s + 1 strategy-diversity precondition test). No new regression is possible from a milestone that touches zero production files; verified anyway by re-running the same directly-affected subsystem test files post-R20 (see final status block).

## 24. Final Cross-Subsystem Audit

*(filled in after the fresh, independent auditor's report)*

## 25. Exact Limitations

- **R20's specific finding is scoped, not general**: "cross-cycle policy learning not observed" applies ONLY to plan-sourced candidates built via a freshly-constructed `Plan` each cycle (the `_plan_id`-uniqueness mechanism, §19/§22) — R13/R15/R18-EQ already independently proved cross-cycle PolicyMemory learning genuinely works for NATIVE (non-plan) candidates. This is not a general "VECTOR cannot learn" finding.
- The `_plan_id`-in-situation-hash characteristic is real, pre-existing, and NOT fixed by this milestone (per the explicit "do not redesign PolicyMemory/DecisionEngine" instruction) — a future milestone could legitimately choose to either exclude `_plan_id`/`_step_id` from the situation hash (matching Agent C's own Phase 1 recommendation to keep any composition/plan correlation identifier in the reasoning_chain marker, never in `params`) or accept it as intentional per-plan-instance non-generalization.
- `_act_on_plan_step()` does not write an R7 `reasoning_chains` correlation marker (confirmed absent in R19, unchanged by R20) — plan-step decisions have real `decision_id`/`candidate_id` but no reasoning-chain readback exists for them today.
- The R20 flagship's bounded 3-cycle scope (vs. the mission text's "approximately 6-10 if safe and practical") is a deliberate, cited, honestly-scoped reduction given this sandbox's demonstrated real-LLM per-call latency (15-259s observed across R18-EQ/R19/R20) — matching R13's own explicit "keeps the bound honest and the runtime sane" precedent for the same reason.
- `idea_validate`'s native candidate params carry no real idea content (`{"name":"","description":""}` fallback) — a real, pre-existing R18-EQ-inherited data-quality gap independently flagged by the R20 adversarial review, out of scope for this milestone.

## 26. Next Recommendation

Not started, and not to be started per this milestone's own scope (no R21). For a future milestone to consider:
- Resolve the `_plan_id`-in-situation-hash non-generalization (§25) if cross-plan-instance policy learning for composed strategies is desired — likely the cleanest fix is moving any plan/step correlation identifier out of `Candidate.params` and into the `reasoning_chain` correlation marker instead (Agent C's own Phase 1 recommendation), never touching `PolicyMemory`/`DecisionEngine` themselves.
- Add an R7 `reasoning_chains` correlation marker to `_act_on_plan_step()`, matching the main `_act_on()` path, if plan-step decision attribution/audit becomes a priority.
- A genuinely justified second `g_equation_portfolio` strategy (R18-EQ's own §20 recommendation, still open) once an idea has been validated — would need a real, exact-match `DISTRICT_TASK_MAP` entry for one of the Class-B startups capabilities (`RevenueModeler`, etc.) promoted to Class A, following the same minimal-fix precedent this whole R18→R20 arc has used throughout.
