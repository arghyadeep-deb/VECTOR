# R21 → R23 Understanding Foundation Report

## 1. Authoritative Starting HEAD

Verified directly (not trusted from the mission prompt's own speculative reference of `6a03032f3...`): `b4df63d80ce8f8177f5f9b79f16335a22cf6b397` (branch `production-hardening-complete`, clean working tree, one worktree, no VECTOR autonomous process running — confirmed via `git status`/`git worktree list`/`Get-CimInstance Win32_Process`). See `VECTOR_TECHNICAL_KNOWLEDGE/R21_R23_ORCHESTRATOR_LEDGER.md` for the full phase-by-phase trace (9 parallel Phase 1 investigators, synthesis, implementation).

## 2. Final HEAD

*(filled in after R23 commits)*

## 3. Exact Milestones Executed

R21 (Generalization) — executed. R22 (Situation Understanding) and R23 (World/Self Model) — status per this report's own sections below, executed serially per the mission's mandatory ordering (R21 → verify → commit → R22 → verify → commit → R23 → verify → commit).

## 4. Architecture Discovered (Phase 1 synthesis)

Nine independent, parallel read-only investigators audited every existing generalization/situation/world-model/self-model mechanism, plus runtime/persistence isolation and cross-cutting safety, plus a fresh adversarial pre-implementation audit. Full findings are in the ledger. Headline discoveries, all independently cross-confirmed by 2+ investigators:

- **PolicyMemory and EpistemicTracker are exact-match by prior, deliberate, documented safety decisions** — R8's correction-penalty design explicitly rejected substring/semantic matching; R16 found and fixed a real cross-action-type collision in EpistemicTracker's domain-key (previously `action_type.split("_")[0]`, now the exact full `action_type`). Neither should be loosened for R21.
- **`core/memory/counterfactual.py::CounterfactualMemory` is real, already-production-wired generalization** — genuine token-Jaccard similarity (not exact-hash), called from `AutonomousLoop._act_on()`'s real "Gap 4" block on every real winning Candidate. Independently ranked the #1 R21 substrate by 3 separate investigators. Had a real, unscoped cross-action-type contamination gap (fixed as part of R21, see §7).
- **`vectorcode/src/reasoning_bank.py`'s "embedding" is a plain SHA256 hash tiled into a vector** — no real semantic locality; explicitly rejected as an R21 substrate (fake generalization, would have been actively misleading to build on).
- **`Candidate.context_snapshot` already exists, is already populated from real `ContextEngine.get_world_state()` data, and is already unit-tested for presence — but is never read by `_score_candidate()`.** Independently discovered by 3 separate investigators (Phase 1 Agents C, G+H, and cross-confirmed by the fresh adversarial auditor) as THE precise missing causal link for R22.
- **No genuine coherent world model exists** — `build_world_snapshot()` is a UI/status dashboard, not a decision input. Real, scattered, individually-queryable stores exist (GoalSystem, PersonModel, AgentRegistry, PlanStore) but each is read only by its own owning subsystem. `PlanStore.active_plans()` is already system-wide/unscoped — the smallest real substrate for a genuine world-model connection.
- **Real, already-wired self-model signals exist and change decisions today**: epistemic dampening and `MetaCognition`'s real bias-detection penalty (`_bias_penalty()`, penalizes detected overconfidence). But capability-existence is checked ONLY at Governor-dispatch time, never before a candidate is scored/selected — VECTOR can commit to (and only discover it cannot execute) an action with no live capable agent.

## 5. R21 — Generalization

### BEFORE Capability

`g_first_revenue`-class real rejections (real `ThreatDetector`/`RedTeamAgent`/owner-rejection events, already fed into `CounterfactualMemory` via `_record_external_rejection()`) had no VERIFIED, PROVEN transfer boundary — the underlying `get_similar_rejections()` query was completely unscoped (`SELECT * FROM rejections ORDER BY created_at DESC`, zero action_type/goal filtering). No test in the repository had ever proven (a) that a real rejection genuinely transfers to a materially different, related real situation through the real production path, (b) that an unrelated situation does not receive it, or (c) bounded the mechanism's real cross-action-type collision risk — a risk this milestone's own audit found and empirically confirmed (two real proposals differing ONLY in action_type, identical params, scored 0.75 — above the real 0.7 veto threshold `_act_on()` itself uses).

### Implementation

`core/memory/counterfactual.py` — `get_similar_rejections()`/`should_avoid()` gained a new, backward-compatible `scope_to_action_type: bool = True` parameter (default True — every existing real caller, including `_act_on()`'s own Gap-4 block, gets the safer scoping automatically with no call-site change needed). When enabled, a candidate rejection row is only compared against proposals sharing the SAME action_type (extracted as the first whitespace-delimited token of the proposal string, matching every real proposal's own `f"{action_type} {json.dumps(params)}"` construction). This preserves genuine transfer WITHIN an action_type (the real capability R21 must demonstrate) while closing the real cross-action-type false-positive the audit found. `scope_to_action_type=False` remains available for an explicit, deliberate future cross-action-type query (no real production caller does this today).

No new subsystem, no new memory store, no ML/embedding infrastructure was added — the existing, already-wired, real Jaccard-similarity mechanism was proven and its one real safety gap was closed.

### AFTER Capability

A real rejection (situation A) genuinely transfers its blocking influence to a materially different but related real situation (situation B — same action_type, different params), through the real, unmodified `AutonomousLoop._act_on()` production path, while an unrelated situation (C) does not receive the transfer, and a same-params-but-different-action-type situation (D) — which WOULD have been wrongly blocked by the transfer under the pre-fix unscoped behavior — is not blocked by it post-fix (D is still independently rejected by its own, unrelated real ThreatDetector match, proving the fix narrows the COUNTERFACTUAL mechanism specifically, not blanket safety).

### Real Production Trace

```
Situation A: real Candidate (via real DecisionEngine.evaluate())
  -> real AutonomousLoop._act_on()
  -> real _scan_threats() -> real ThreatDetector.analyze_input()
     -> real regex match: "sudo-commands" pattern, severity 0.9
  -> real _record_external_rejection() -> real CounterfactualMemory
     .record_rejection() -> real SQLite row written

Situation B (materially different, same action_type, INDEPENDENTLY
confirmed "otherwise safe" -- a real ThreatDetector scan of B's own
text, run before B ever reaches CounterfactualMemory, finds zero
critical signals):
  -> real Candidate (fresh real DecisionEngine.evaluate() call)
  -> real _act_on() -> real CounterfactualMemory.should_avoid()
     (runs BEFORE the ThreatDetector scan in _act_on()'s own real code)
     -> real Jaccard(A,B)=0.727 >= 0.7 threshold -> real veto
  -> real record_rejection() with reason "auto-blocked: similar to
     past rejection (score=0.73)" -- attributably the TRANSFER, not an
     independent trigger (B's own row is the SECOND real rejection,
     recorded before ThreatDetector's line is ever reached, and B was
     independently confirmed threat-free on its own)
  -> return, real execution never proceeds further

Situation C (unrelated): real Jaccard(A,C)=0.14 < 0.7
  -> should_avoid() returns False -> NOT vetoed -> proceeds to real
     ThreatDetector scan (no match) -> real Governor.dispatch() ->
     "no_agents" (isolated test registry has no agent registered) --
     zero real LLM call, real honest refusal

Situation D (cross-action-type, same params as A): real raw
Jaccard(A,D)=0.75 -- pre-fix would ALSO have been vetoed by the
transfer, identically to B.
  -> post-fix should_avoid() returns False (scope_to_action_type
     excludes A's row -- different action_type) -> proceeds ->
     real, INDEPENDENT ThreatDetector match on D's own "sudo bash"
     text -> real rejection recorded, reason "blocked by
     ThreatDetector" (NOT "auto-blocked: similar to past rejection")
     -- proves the counterfactual transfer specifically did not fire
```

### Behavioral Proof

`tests/test_r21_generalization.py` — 10 tests, 0 real LLM calls (ThreatDetector is pure regex pattern matching; no agent is registered in the isolated test registry, so any candidate that reaches dispatch gets a real, fast, honest refusal rather than a real handler execution):

| Category | Test(s) |
|---|---|
| Substrate validity | `test_a_b_materially_different_but_related_high_similarity`, `test_c_unrelated_low_similarity`, `test_d_cross_action_type_raw_similarity_would_have_falsely_matched` |
| Safety fix (load-bearing, not cosmetic) | `test_safety_fix_blocks_cross_action_type_match_by_default`, `test_same_action_type_transfer_still_works_after_the_fix`, `test_opt_out_still_available_for_explicit_cross_action_type_use` |
| Flagship (real production boundary) | `TestFlagshipRealGeneralization::test_real_rejection_transfers_to_related_situation_not_to_unrelated_or_cross_type` |
| Safety | `test_classify_is_pure_static_function_unreachable_from_counterfactual`, `test_red_tier_unaffected_by_a_maximally_similar_real_rejection`, `test_no_dynamic_mutation_of_permission_tiers_from_counterfactual_module` |

Result: 10/10 pass, ≤7 seconds total (flagship included).

### Persistence Proof

Flagship closes the real `CounterfactualMemory` SQLite connection and reopens a fresh instance against the SAME on-disk file (`db_path=` explicit, isolated per-test); B's real veto is re-confirmed via the same real `should_avoid()` API, with the decayed score matching the pre-restart value within tolerance.

### Causal Controls

- **No manual policy injection / no manually selected winner**: every winner in the flagship comes from a real `DecisionEngine.evaluate([...])` call; source-audited (`inspect.getsource`) for absence of hardcoded winners, direct `PolicyMemory.update_from_outcome()` calls, etc. (see `TestSafety`/fast unit tests — the flagship itself contains none).
- **No fabricated reward/outcome**: A's rejection reason comes from the real `ThreatDetector` signal; B's veto score is the real, computed `_jaccard()`/`_decay_factor()` result; C's non-veto and D's independent-rejection-reason are both read back from real SQLite rows, never asserted from memory.
- **No hand-built Candidate used as the only proof**: every `_act_on()` call in the flagship receives `decision.winner` from a real `evaluate()` return value.

## 6. R21 Adversarial Review

A fresh, independent, read-only agent (no prior context) reviewed all 10 required R21 checklist claims by reading `git diff HEAD` itself, hand-computing the real `_jaccard()` scores for every situation pair independently (not trusting this file's own claimed numbers), tracing `_act_on()`'s exact real check ordering, and live-running the full test suite (9 fast + 1 flagship, both passed, flagship in 6.09s with zero real LLM call, confirmed by checking that `"script"`/`"idea_validate"` are GREEN-tier so `RedTeamAgent` never fires).

**Verdict: all 10 claims CONFIRMED.** Overall: **PASS WITH CONCERNS** — one legitimate, non-blocking finding: the original situation B ("sudo bash restart_staging_server.sh") was ITSELF independently ThreatDetector-triggering (containing "sudo bash" too), so while the test rigorously proved real ATTRIBUTION (the CounterfactualMemory block runs and returns before ThreatDetector, with a distinguishable reason string), it did not prove the transfer ALONE changes an otherwise-PERMITTED action's fate — a real narrative weakness, not a disproof of any claim.

**Repaired** (repair attempt 1 of the mission's allowed 3, resolved on first attempt): B was redesigned to share every field with A EXCEPT the risky "cmd" (now "systemctl restart production-server.service" — verified via a direct call to the real `ThreatDetector` class, both standalone and now inline inside the flagship test itself, to produce ZERO critical signals on its own). Real Jaccard(A,B) = 0.727 (still clears the real 0.7 veto threshold `_act_on()` uses); real Jaccard(A,C) = 0.14. B is now demonstrably an "otherwise safe" action blocked ONLY by the real counterfactual transfer from A — the flagship itself now asserts this via a direct, real `ThreatDetector().analyze_input()` precheck on B's own text before B is ever passed to `_act_on()`. Re-verified: 10/10 pass; full regression re-run (101/101 pass across all directly-affected + R18-EQ/R19/R20/R21 suites).

No second adversarial review pass was launched given: the fix directly and verifiably addresses the only concern raised (confirmed via the real `ThreatDetector` class, not merely asserted), the reviewer's own verdict was already PASS (not FAIL) with this as the sole non-blocking note, and all 10 other claims were independently confirmed via the reviewer's own hand-computation rather than trust in this file's numbers.

## 7. R21 Safety Review

- `PermissionGateway._classify()` is confirmed (source-read, R19/R20/R21 sessions) a pure static function of `action_type` against `core/config.py`'s module-level GREEN/YELLOW/RED/FORBIDDEN lists — zero references to `CounterfactualMemory`, `PolicyMemory`, or `EpistemicTracker` anywhere in it or its callers.
- A maximally-similar real rejection for a RED action_type (`code_task`) changes nothing about its real permission tier — confirmed via `test_red_tier_unaffected_by_a_maximally_similar_real_rejection`.
- The new `scope_to_action_type` safety fix strictly NARROWS the generalization mechanism's blast radius; it does not introduce any new capability, external communication, or authorization path.
- Transferred/generalized knowledge (a Jaccard-similarity veto) is exclusively a pre-dispatch SCORING/gating input inside `_act_on()` — it can only ever cause an early `return` (never execute), never grant, promote, or bypass an authorization tier.

## 8. R21 Regression

Directly-affected files (`test_counterfactual_block_penalizes_policy.py`, `test_reasoning_chain_dataset.py`, `test_m1d_development_test_safety.py`, `test_r10_decision_provenance.py`, `test_task92_r7_decision_candidate_correlation.py`, R18-EQ/R19/R20's own fast suites) — 90/91 pass on first sweep; the one failure was R18-EQ's own DB-safety allowlist test needing R21's file list added (same precedent established during R19/R20), fixed and re-verified (1/1 pass).

## 9. R21 Files Changed

`core/memory/counterfactual.py` (safety fix, +~35 lines), `tests/test_r21_generalization.py` (new, 10 tests), `tests/test_r18_eq_equation_capability.py` (DB-safety allowlist extended, same precedent as R19/R20).

---

# R22 — Situation Understanding

## 10. R22 BEFORE Capability

`DecisionEngine.evaluate()` already, before this milestone, called the real, production `ContextEngine.get_world_state()` (RULE 1) and attached the real, structured result to every `Candidate` as `c.context_snapshot` — already unit-tested for presence (`tests/test_decision_engine.py::test_context_snapshot_populated_on_candidates`, pre-existing). But `_score_candidate()`, called immediately after, never read it — the code's own pre-existing comment admitted this outright ("Does NOT change the score formula itself — that's a deliberate, separate decision"). Two REAL, materially different real action_types with different real situational context (e.g. whether the owner is genuinely present) scored, and were decided between, IDENTICALLY — the distinction was captured but structurally lost before it could ever change a real decision. The one pre-existing real counter-example (`idea_validator.py`'s Regime gate) lives entirely inside one district handler's own business logic, never reaching `DecisionEngine`'s own central, shared scoring path.

## 11. R22 Implementation

`core/loop/decision_engine.py::DecisionEngine._situational_factor()` — one new, small, bounded, POST-score multiplier, architecturally identical in shape to the pre-existing `_epistemic_penalty()`. Reads exactly one already-real field (`context_snapshot["presence"]`, sourced from the real FaceDetector via `ContextEngine`'s sense cache — values `"present"`/`"absent"`/`"unknown"`). When `presence == "absent"` AND the candidate's action_type is already GREEN (checked via the real, unmodified `PermissionGateway.classify()` — never any other mechanism), the candidate's score is multiplied by `1.05`. `"present"` and the honest `"unknown"` (detector never ran) both apply zero adjustment — uncertainty is never silently promoted to certainty. Any malformed/unexpected `context_snapshot` shape returns `1.0` (fails safe, never raises). A non-GREEN candidate is never boosted, by construction — the guard checks `PermissionGateway.classify()` before ever considering a boost.

Semantics are deliberately the smallest defensible mapping, tied directly to VECTOR's own documented purpose (CLAUDE.md: "a Darwinian multi-agent autonomous AI running 24/7") rather than an invented, action-type-specific business rule — this extends the Regime gate's own already-legitimate "real situational fact changes a real decision" pattern into `DecisionEngine`'s central, shared path (per the Phase 1 fresh adversarial investigator's own explicit caution against re-labeling the Regime gate's pattern as new without this exact generalization).

No new subsystem, no new memory store, no new sensor/data-collection point was added — the existing, already-real, already-populated field was proven and connected.

## 12. R22 AFTER Capability

Two real, materially different action_types (`idea_validate`, GREEN; `commit_code`, YELLOW), with real, controlled `confidence` values chosen so the real, unmodified-by-R22 formula gives `commit_code` a narrow real lead — a real, close race, not a landslide (`commit_code`=0.4125 vs `idea_validate`=0.40 when not boosted). The real, unmodified `DecisionEngine.evaluate()` now genuinely flips the winner based on real, different situational context: `commit_code` wins when `presence="present"`; `idea_validate` wins when `presence="absent"` (0.42 > 0.4125) — the real 1.05x boost applied only to the already-GREEN candidate is what causes the flip.

## 13. R22 Real Production Trace

```
DecisionEngine.evaluate(candidates)
  -> real ContextEngine.get_world_state()            [only this ONE external
     -> real world_state dict, c.context_snapshot      sensor boundary is
        = world_state for every candidate               isolated per-test]
  -> real _score_candidate(c) for every candidate
     -> real 5-factor formula (goal_alignment, confidence,
        policy_score, urgency, timing, cost)
     -> real _epistemic_penalty()                     [pre-existing]
     -> real _situational_factor(c)                   [R22, new]
        -> reads c.context_snapshot["presence"]
        -> real PermissionGateway.classify(c.action_type)
        -> 1.05x if GREEN+absent, else 1.0x
  -> real ranked = sorted(candidates, key=total_score)
  -> real winner = _select_staleness_aware_winner(ranked)
```

## 14. R22 Behavioral Proof

`tests/test_r22_situation_understanding.py` — 20 tests, 0 real LLM calls (pure scoring, no dispatch/execution):

| Category | Test(s) |
|---|---|
| Mechanics (bounded, GREEN-only, uncertainty-safe) | `TestSituationalFactorMechanics` (6 tests, incl. 8 parametrized malformed-input cases) |
| BEFORE — missing distinction proven | `TestBeforeMissingDistinction::test_pre_r22_formula_component_is_blind_to_context` |
| AFTER / Flagship — real winner flip | `TestFlagshipSituationalDecisionChange` (2 tests: real flip + a no-difference control) |
| Safety | `TestSafety` (3 tests) |

Result: 20/20 pass, ≤8 seconds total.

## 15. R22 Persistence

Not claimed — `_situational_factor()` is a pure, stateless, per-evaluate()-call function of `context_snapshot` (itself freshly populated every real `evaluate()` call from a live sensor read); there is no new persistent state to prove restart-survival for. (Per the mission's own gate: "Persistence: Required whenever the capability claims persistent state" — this capability does not.)

## 16. R22 Causal Controls

- **No hardcoded expected answer**: the flagship asserts on `decision.winner.action_type`, a real, computed value from a real `evaluate()` call — never bypassed.
- **Novel/unseen situation**: this exact confidence pairing (0.5 vs 0.55) and action_type pair, under this specific controlled context, is not duplicated by any pre-existing fixture (confirmed via `test_decision_engine.py`'s own existing `context_snapshot` test only asserting field PRESENCE, never scoring behavior).
- **Control**: `test_control_no_context_difference_no_winner_change` — identical real context across two real `evaluate()` calls produces a stable winner, ruling out hidden randomness.
- **Isolation technique legitimacy**: `_FixedWorldStateContextEngine` supplies a fixed, real-shaped return value ONLY for `ContextEngine.get_world_state()` (the one genuinely external, sensor-dependent, non-deterministic call) — every other real production function (`evaluate()`, `_score_candidate()`, `_situational_factor()`, real ranking/winner-selection) runs completely unmodified and unmocked, matching this repo's own established "isolate only the deepest external dependency" precedent (R18-EQ's LLM-provider chain, R19's PostJobTracker path isolation) — not "manually injecting a belief."

## 17. R22 Adversarial Review

A fresh, independent, read-only agent (no prior context) reviewed all 10 required R22 checklist claims. It independently re-derived the flagship's exact arithmetic by hand from the real 5-factor weights (`W_GOAL=0.30, W_CONF=0.25, W_POLICY=0.20, W_URGENCY=0.15, W_TIMING=0.10, W_COST=0.05`) and real defaults (`Candidate.timing_score` defaults to 1.0; `PolicyMemory.DEFAULT_SCORE=0.5`; `goal_score=0` since the probe goal id matches no real seeded goal) — reproducing `idea_validate=0.40`, `commit_code=0.4125`, boosted `idea_validate=0.42` exactly, independently confirming the numbers are "real, generic defaults falling out of the formula, not scenario-specific hacks." It compared `_FixedWorldStateContextEngine`'s stand-in dict key-for-key against the real `ContextEngine.get_world_state()` (confirmed identical 17-key shape). It ran the real regression suite itself (31/31 pass) and confirmed the pre-existing `test_context_snapshot_populated_on_candidates` test already existed and already asserted `context_snapshot` population before this milestone (R22 did not invent that pre-existing fact).

**Verdict: all 10 claims CONFIRMED. Overall: PASS.**

One cosmetic finding (repaired, not a functional defect): the pre-existing comment above `evaluate()`'s real-world-state injection said context_snapshot "does NOT change the score formula itself" — accurate when originally written, no longer accurate after R22's own wiring. Fixed: the comment now points to `_situational_factor()`'s own docstring and this report for the real capability it closes. Re-verified: 31/31 pass (`test_decision_engine.py` + `test_r22_situation_understanding.py`).

No repair cycle was needed for any of the 10 substantive claims — the reviewer's only other note (the 1.05x magnitude being "a judgment call rather than derived from data") was explicitly acknowledged as "reasonable and low-risk given the GREEN-only, bounded [1.0, 1.05] guard" and "acceptable for a first-cut milestone," not a defect requiring repair.

## 18. R22 Safety Review

- `PermissionGateway._classify()` unaffected — `_situational_factor()`'s diff contains zero mutation of `GREEN`/`YELLOW`/`RED`/`FORBIDDEN` (source-audited: no `X.append(`, no `X =` assignment to a classification variable).
- A YELLOW (`commit_code`) or RED (`code_task`) candidate can never receive the boost — the guard checks `PermissionGateway.classify()` before ever considering it, confirmed both by direct source reading and by `TestSafety::test_yellow_action_never_boosted_even_when_absent`/`test_red_action_never_boosted_even_when_absent`.
- The factor is strictly bounded `[1.0, 1.05]` — never a penalty, never unbounded (`test_boost_is_bounded_and_never_negative`).
- Uncertainty (`"unknown"`) is never treated as the boosted state (`test_unknown_presence_is_not_falsely_treated_as_certainty`).

## 19. R22 Regression

Directly-affected files (`test_decision_engine.py`, `test_r10_decision_provenance.py`, `test_task91_r6_candidate_diversity.py`, `test_task92_r7_decision_candidate_correlation.py`, `test_r15_autonomous_green_to_green_switching.py`, `test_r16_epistemic_decision_integration.py`, `test_r17_plan_derived_strategy_diversity.py`, R18-EQ/R19/R20/R21's own fast suites) — 177/177 pass, zero regression.

## 20. R22 Files Changed

`core/loop/decision_engine.py` (+~75 lines: `_situational_factor()` + wiring into `_score_candidate()`'s formula/reasoning_chain/reasoning_steps), `tests/test_r22_situation_understanding.py` (new, 20 tests).

---

# R23 — World Model + Self Model

## 21. R23 BEFORE Capability

**World model:** no genuine, coherent, cross-subsystem world model existed (Phase 1 Agent E, cross-confirmed): `core/runtime/world_model.py::build_world_snapshot()` is a real UI/status dashboard, consumed only by a GET endpoint and one informational-only field — never branched on by any real decision. Real, individually-queryable, already system-wide stores existed (`PlanStore.active_plans()` chief among them — already unscoped, zero new infra needed) but each was read only by its own owning subsystem: `PlanStore.active_plans()` was read only inside `AutonomousLoop._get_plan_candidates()` (to *generate* plan-step candidates for their own goal), never by `_score_candidate()` as a fact about OTHER, unrelated candidates.

**Self model:** real, already-wired self-observation signals existed and already changed decisions (`_epistemic_penalty()`; `MetaCognition._bias_penalty()`, real `detect_bias()`-driven overconfidence penalty) — but capability EXISTENCE was checked only at `Governor.dispatch()` time (core/city/governor.py, lines ~2289/2298), strictly AFTER a winning `Candidate` had already been selected by `DecisionEngine`. `goal_system.py`/`decision_engine.py` had zero references to `AgentRegistry` anywhere prior to this milestone (confirmed independently by both Phase 1 Agent F and the post-implementation adversarial reviewer via direct grep) — VECTOR could commit to (score highest, "win") a candidate for a capability that does not currently exist, discovering the gap only after the fact, at dispatch.

## 22. R23 Implementation

Two new, small, bounded, POST-score multipliers in `core/loop/decision_engine.py`, architecturally identical in shape to `_epistemic_penalty()`/`_situational_factor()`:

- **`_capability_factor()` (self-model):** reads `self._get_agent_registry()` — a new lazy-init getter returning the real, live, module-level `AgentRegistry` singleton via `core.city.agent_registry.get_registry()`, the SAME singleton `Governor.dispatch()` itself reads. If any registered agent's `capabilities` list contains the candidate's exact `action_type`, factor stays `1.0` ("capable"). If no live agent declares it, factor becomes `0.85` ("no_capable_agent") — a real, bounded self-knowledge penalty, never a hard block. Registry error/unavailable fails safe to `1.0` (an inability to self-inspect is never treated as evidence of incapability).
- **`_workload_factor()` (world-model):** reads `self._get_plan_store()` — a new lazy-init getter returning the real, live `PlanStore` via `core.runtime.plans.get_plan_store()`, the SAME store `AutonomousLoop._get_plan_candidates()` itself reads. If at least one real Plan is genuinely active AND the candidate is NOT itself a continuation of an existing plan (`candidate.source` does not start with `"plan:"`), factor becomes `0.97` — a small, real-world-state-driven preference for finishing committed work over starting something new. A plan-step continuation, or no active plans at all, stays neutral (`1.0`). Store error/unavailable fails safe to `1.0`.

Both factors are wired into `_score_candidate()` immediately after R22's `_situational_factor()`, with matching `reasoning_chain`/`reasoning_steps` entries (`"self_model_capability"`, `"world_model_workload"`) appended only when the factor deviates from neutral — the same established pattern R21/R22 both use.

No new subsystem, no new memory store, no new persisted state — both factors query existing, already-real, already-live production singletons that real production code already depends on for other purposes.

## 23. R23 AFTER Capability

**Self-model:** two real, materially different action_types (`idea_validate`, confidence 0.5; `commit_code`, confidence 0.55 — a real, narrow merit edge for `commit_code`) now genuinely flip winner based on real, live agent registration: `commit_code` wins when neither action_type has a live capable agent (uniform penalty, merit-only race); `idea_validate` wins once a real, live `IdeaValidator` (which genuinely declares the `"idea_validate"` capability) is registered and no agent declares `"commit_code"`.

**World-model:** a fresh native candidate (`idea_validate`, confidence 0.52) and a plan-continuation candidate (`script`, confidence 0.50, `source` prefixed `"plan:"`) now genuinely flip winner based on real, live in-flight commitments: the native candidate wins with no active plans; the plan-continuing candidate wins once a real, active `Plan` (built via R19's own real `build_wedge_content_plan()`) exists in a real `PlanStore` — VECTOR now genuinely prefers finishing real committed work over starting something new when real in-flight plans exist.

## 24. R23 Real Production Trace

```
DecisionEngine.evaluate(candidates)
  -> real ContextEngine.get_world_state()      [R22's boundary, unchanged]
  -> real _score_candidate(c) for every candidate
     -> real 5-factor formula
     -> real _epistemic_penalty()              [pre-existing]
     -> real _situational_factor(c)            [R22]
     -> real _capability_factor(c)             [R23, new]
        -> real self._get_agent_registry().get_all_agents()
        -> 1.0 if any real agent declares c.action_type, else 0.85
     -> real _workload_factor(c)               [R23, new]
        -> real self._get_plan_store().active_plans()
        -> 0.97 if active plans exist AND c is not a plan continuation, else 1.0
  -> real ranked = sorted(candidates, key=total_score)
  -> real winner = _select_staleness_aware_winner(ranked)
```

## 25. R23 Behavioral Proof

`tests/test_r23_world_self_model.py` — 23 tests, 0 real LLM calls (pure scoring via real `evaluate()` calls, no dispatch/execution):

| Category | Test(s) |
|---|---|
| Mechanics (bounded, penalty-only, fail-safe) | `TestCapabilityFactorMechanics` (5), `TestWorkloadFactorMechanics` (5) |
| BEFORE — pre-R23 formula blind to both facts | `TestBeforeMissingDistinction` (1) |
| AFTER / Flagship — real winner flips (self-model) | `TestFlagshipSelfModel` (3: real flip, control, self-authorization safety) |
| AFTER / Flagship — real winner flips (world-model) | `TestFlagshipWorldModel` (3: real flip, control, self-authorization safety) |
| Persistence | `TestPersistence` (2: PlanStore real restart-survival; AgentRegistry honest non-persistence) |
| Safety | `TestSafety` (4) |

Result: 23/23 pass, a few seconds total. Independently re-run and re-confirmed by the post-implementation adversarial reviewer (see §27).

## 26. R23 Persistence

**World-model (`PlanStore`) — claimed and proven.** `PlanStore` persists via atomic JSON write (`save()`); `test_plan_store_world_state_survives_real_restart` builds a plan, adds it to one `PlanStore` instance, then constructs a SECOND, FRESH `PlanStore` instance against the same on-disk file and confirms `active_plans()` round-trips identically — genuine restart-survival, not merely in-process state.

**Self-model (`AgentRegistry`) — honestly NOT claimed.** `AgentRegistry` has no `save`/`load` path anywhere in its source (confirmed by direct source read and by `test_agent_registry_is_honestly_not_a_persisted_store`'s `hasattr` check) — it is real, live, in-memory registration state, by deliberate real production design: agents register themselves fresh at every real process start (`run_vector.py::bootstrap_agents()`). Per the mission's own "if the capability cannot honestly be proven, say NOT PROVEN" principle, this is documented as a real, legitimate capability-boundary limitation rather than forced or fabricated.

## 27. R23 Causal Controls

- **No hardcoded expected answer**: both flagships assert on `decision.winner.action_type` from a real, computed `evaluate()` call.
- **Control pairs, not just positive cases**: `test_control_when_neither_capable_relative_order_unaffected` (empty registry — uniform penalty preserves the real merit-based order) and `test_control_no_active_plans_relative_order_unaffected` (empty PlanStore — native candidate's real confidence edge stays decisive) each isolate the SAME two candidates with ONLY the registry/store contents changed.
- **Cross-factor isolation**: flagship tests hold R22's `_situational_factor()` neutral via `_FixedWorldStateContextEngine("present")` and hold the other R23 factor neutral (empty `PlanStore`/`AgentRegistry` as appropriate) so each new factor's effect is independently attributable, not a combined/confounded result.
- **Real agents, not fabricated capability**: the capability flagship registers a real, live `IdeaValidator()` instance (whose real `self.capabilities` list, read directly from `districts/startups/idea_validator.py`, genuinely includes `"idea_validate"`) — never a mock or hand-authored capability string.
- **Real plans, not fabricated commitments**: the workload flagship uses R19's own real, already-proven `build_wedge_content_plan()` composer, added to a real `PlanStore`, not a hand-constructed dict.
- **Isolation technique legitimacy**: only the `AgentRegistry`/`PlanStore` attributes (both already lazy-init-cached instance attributes, same established override pattern as `engine._context_engine` in R22 and `engine._epistemic` in R13) are substituted with isolated-but-real instances — every other real production function runs unmodified.

## 28. R23 Adversarial Review

A fresh, independent, read-only agent (no prior context) reviewed all 10 required R23 checklist claims against direct source reads, independent arithmetic reconstruction, and its own independently-executed test runs (not trusted from this report or the ledger). It confirmed: the capability/world-model deltas are genuinely new (zero pre-R23 `AgentRegistry` reference in `decision_engine.py`; `PlanStore.active_plans()` previously read only by its own owning goal); both factors are called from the real `evaluate()` → `_score_candidate()` production path (not dead/test-only code); both flagship tests use real `evaluate()` calls with real registered agents/real plans (never a hand-set `total_score` or fabricated winner), with genuine, non-trivial control tests; persistence claims are honest in both directions (`PlanStore` round-trips through a fresh instance; `AgentRegistry` has no save/load path, confirmed by source read); neither factor's executable body references `PermissionGateway`, `core.config`, or any GREEN/YELLOW/RED/FORBIDDEN mutation (docstring prose mentioning `PermissionGateway` to explain what is NOT touched was correctly distinguished from actual code); both factors fail safe to `1.0` on store/registry error, with explicit tests; both factors are strictly bounded (`_capability_factor` only ever returns `1.0` or `0.85`; `_workload_factor` only ever returns `1.0` or `0.97` — literal, non-composable return values, confirmed by source read); and the R16 regression repair (§29) is a genuine, honest consequence of the new capability signal, not a cover-up, with the downstream RED-tier safety proof still exercised (via a pre-existing mock, not newly introduced by R23).

**Verdict: all 10 claims CONFIRMED. Overall: PASS.**

One additional, non-blocking finding (explicitly confirmed by the reviewer to PRE-DATE R23's diff, not introduced by it): `tests/test_r16_epistemic_decision_integration.py`'s "Phase 12" safety proof mocks `PermissionGateway` wholesale, which is technically at odds with `.claude/rules/testing.md`'s "never mock permission_gateway.py" rule — now more visible because the real winner in that scenario changed from RED-tier (`code_task`) to GREEN-tier (`read_code`) as a direct, honest consequence of R23's new capability signal. Recorded as a DEFERRED finding (§ Limitations/Deferred, below) rather than fixed here, per the mission's own scope discipline: the real `PermissionGateway._classify()` function itself is independently confirmed completely untouched and still a pure static function of `action_type` against static config lists, so no real safety gap exists today — only a pre-existing test-realism gap in one assertion belonging to a prior milestone, outside R23's own required scope.

## 29. R23 Safety Review

- Neither `_capability_factor()`'s nor `_workload_factor()`'s executable body references `PermissionGateway`, `core.config`, or performs any `GREEN`/`YELLOW`/`RED`/`FORBIDDEN` assignment (confirmed by both this session's own source-level test, `TestSafety::test_capability_factor_never_calls_permission_gateway`, scanning the stripped function body specifically to avoid a docstring-prose false-positive, and independently by the adversarial reviewer's own separate source read).
- `PermissionGateway._classify()` remains, independently re-confirmed, a pure static function of `action_type` against `core/config.py`'s static GREEN/YELLOW/RED/FORBIDDEN lists — zero dependency on `AgentRegistry` or `PlanStore`.
- Both factors are penalty-only or neutral — `_capability_factor() ∈ {0.85, 1.0}`, `_workload_factor() ∈ {0.97, 1.0}` — neither can ever BOOST a candidate, confirmed by direct enumeration of every return statement in both functions' source.
- The self-model explicitly describes capability, never creates authority: a candidate the self-model considers "capable" (factor=1.0, no penalty) never has its real permission tier altered — `test_self_model_cannot_self_authorize` confirms a RED-tier action (`code_task`) stays RED-classified by the real `PermissionGateway` even when a live agent happens to declare it capable.
- The world-model is a pure scoring preference, never an authorization change — `test_world_model_cannot_self_authorize` confirms `_workload_factor()`'s source contains no `PermissionGateway`/config/tier-list reference.
- Both factors fail safe (`1.0`, i.e. no penalty) on any registry/store error — an inability to self-inspect is never treated as evidence of incapability or overcommitment, confirmed by explicit tests injecting a raising getter.

## 30. R23 Regression

**Genuine regression found and repaired (not a test bug in the new milestone's own suite):** the full sweep (`test_decision_engine.py` + `test_r10_decision_provenance.py` + `test_task91_r6_candidate_diversity.py` + `test_task92_r7_decision_candidate_correlation.py` + `test_r15_autonomous_green_to_green_switching.py` + `test_r16_epistemic_decision_integration.py` + `test_r17_plan_derived_strategy_diversity.py` + R18-EQ/R19/R20/R21/R22/R23's own suites) surfaced one real failure in `test_r16_epistemic_decision_integration.py::TestEpistemicProductionPathFlagship::test_real_epistemic_staleness_measurably_dampens_a_real_later_decision`: its isolated 2-agent registry fixture (`GitBot`+`ArchitectBot`, a pre-existing R13-era fixture) has no agent declaring `"code_task"` — confirmed, via repo-wide grep, that NO agent anywhere in `districts/` ever declares it — so R23's new, real `_capability_factor()` honestly penalizes `code_task` (0.4→0.34) while `read_code` (genuinely declared by `ArchitectBot`) stays unpenalized (0.388→0.388), flipping the real winner. Independently re-derived by hand and re-confirmed by the adversarial reviewer as R23's capability signal working CORRECTLY, not a defect. Per the mission's "no manufactured cognition" rule, did not fabricate a `code_task` capability on either agent — instead updated R16's assertion (`code_task`→`read_code`) and its surrounding comments to honestly describe the new two-factor arithmetic. R16's downstream RED-tier "must not auto-execute" safety proof already used a mocked gateway classification independent of the real winner's real tier (pre-existing, not introduced by this fix), so that safety property remains fully exercised — now explicitly documented as simulated, since the real winner (`read_code`) is itself GREEN-tier.

Final result: 203/203 pass across the full sweep (`test_decision_engine.py` 11 + `test_r10_decision_provenance.py` 4 + `test_task91_r6_candidate_diversity.py` 14 + `test_task92_r7_decision_candidate_correlation.py` 8 + `test_r15_...` 14 + `test_r16_...` 8 + `test_r17_...` 20 + `test_r18_eq_...` 10 + `test_r19_...` 10 + `test_r20_...` 20 + `test_r21_...` 10 + `test_r22_...` 20 + `test_r23_...` 23 — counts per the adversarial reviewer's own independent collection), zero unresolved regression, including `test_r18_eq_equation_capability.py`'s DB-safety allowlist check (extended to cover the R16 test file touch, matching the established R19/R20/R21 precedent).

## 31. R23 Files Changed

`core/loop/decision_engine.py` (+~110 lines: `_capability_factor()` + `_workload_factor()` + `_get_agent_registry()`/`_get_plan_store()` lazy-init getters + wiring into `_score_candidate()`'s formula/reasoning_chain/reasoning_steps), `tests/test_r23_world_self_model.py` (new, 23 tests), `tests/test_r16_epistemic_decision_integration.py` (regression repair — one assertion + surrounding comments updated, no test logic removed or weakened), `tests/test_r18_eq_equation_capability.py` (DB-safety allowlist extended to cover the R16 touch, same precedent as R19/R20/R21).
