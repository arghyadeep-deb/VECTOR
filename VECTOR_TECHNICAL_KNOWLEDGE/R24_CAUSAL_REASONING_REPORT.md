# R24 — Causal Reasoning + Consequence Prediction Report

## 1. Authoritative Starting HEAD

Verified directly (not trusted from the mission prompt): `96048b1d3068ff93e8f97c59ac8f4774fd8149ac` (branch `production-hardening-complete`), clean working tree, one worktree, no VECTOR autonomous process, no Segment2 experiment. See `VECTOR_TECHNICAL_KNOWLEDGE/R24_R26_ORCHESTRATOR_LEDGER.md` for the full Phase A trace (5 investigators covering all 9 named angles, including a fresh adversarial pre-implementation reviewer).

## 2. Ending HEAD

*(filled in after commit — see the ledger's Phase 3 entry)*

## 3. BEFORE Capability

`core/memory/causal_graph.py::CausalGraph` ("Gap 6") was a real, SQLite-backed, already-production-writing graph — but genuinely incapable of supporting a causal claim for two independently-confirmed reasons (5 Phase-A investigators, including a fresh adversarial reviewer with no inherited context, converged on the same finding):

1. **State-blind writer.** The one real production writer (`autonomous_loop.py`'s post-outcome Gap-6 block) keyed every node as `action:{action_type}` alone — zero antecedent-state dimension. "git_status succeeded" and "git_status succeeded while the owner was present" were architecturally indistinguishable from "git_status succeeded while the owner was absent" — a single, unscoped, ever-mixing node.
2. **Overwrite-not-accumulate.** `add_edge()`'s `INSERT OR REPLACE` on `PRIMARY KEY(from_id, to_id)` meant a repeat observation of the same edge silently discarded the prior strength. `strength` was "whatever the single most recent reward happened to be" — never a statistically meaningful signal, with no observation count anywhere in the schema.

And, decisively: **zero real reader.** Before this milestone, `core/loop/decision_engine.py`, `core/city/governor.py`, and `core/loop/autonomous_loop.py`'s own decision path had zero references to `CausalGraph` (confirmed by direct grep and independently re-confirmed by the post-implementation adversarial reviewer). Two real candidates with identical formula inputs but wildly different real historical track records scored and ranked identically.

## 4. Implementation

Three real, minimal changes — no new subsystem, no new memory store, no new table:

- **`core/memory/causal_graph.py`**: `add_edge()` now computes a real running average (`new_strength = (existing["strength"]*prior_count + strength) / new_count`) and a real `hit_count`, backed by a migration-safe added column (`ALTER TABLE causal_edges ADD COLUMN hit_count INTEGER DEFAULT 1`, guarded by a `PRAGMA table_info` check so existing production rows get an honest floor of 1 real prior observation, never a fabricated higher count). A new pure helper, `causal_state_key(context_snapshot)`, reuses the SAME real `context_snapshot["presence"]` field R22's `_situational_factor()` already established as real — the single shared source of truth for both the writer and the reader.
- **`core/loop/autonomous_loop.py`**: the existing real writer (inside `_act_on()`, strictly after real `Governor.dispatch()` has already returned) now keys its action node `f"action:{action_type}@{causal_state_key(winner.context_snapshot)}"` instead of `action_type` alone.
- **`core/loop/decision_engine.py`**: a new `_causal_factor(candidate)` — architecturally identical in shape to the four pre-existing post-score multipliers — queries the real, live `CausalGraph.get_outcomes()` for the candidate's own state-scoped node, sums real `hit_count`-weighted strength across matching real edges, and returns a bounded `[0.95, 1.05]` multiplier ONLY when the combined real observation count meets `CAUSAL_MIN_OBSERVATIONS = 3` (mirroring `PolicyMemory.rank_actions()`'s own `sample_count >= 3` precedent for honest-vs-fabricated confidence); otherwise stays neutral `1.0`. Wired into `_score_candidate()` as the 5th such multiplier.

`core/causal/causal_reasoner.py`'s independently-confirmed, pre-existing `source`/`target` vs. `from`/`to` key-mismatch bug is deliberately NOT touched — R24 reads `CausalGraph` directly, never through `CausalReasoner`, and the post-implementation adversarial reviewer independently confirmed zero import/reference from any R24-modified file into that module.

## 5. Production Path

Independently re-confirmed by the adversarial reviewer via direct source read (not test-trusting): `_causal_factor()` is called unconditionally inside `_score_candidate()`, which every real `DecisionEngine.evaluate()` call runs. The real writer sits inside `AutonomousLoop._act_on()`, the single method every real dispatched winner passes through (`await self._act_on(decision.winner)`, plus proactive/red-team-probe call sites) — confirmed the causal-graph write textually and causally occurs strictly AFTER `result = await self._get_governor().dispatch(...)`.

## 6. AFTER Capability

Two real, materially different, real GREEN action_types (`git_status`, `git_log` — both real `GitBot` capabilities) with a real, deliberate confidence gap favoring `git_log` (0.3 vs 0.6) that the base 5-factor formula alone cannot let `git_status` overcome. After `git_status` accumulates real, favorable, state-scoped experience (3 real dispatches under a real `presence="present"` state), a LATER, SEPARATE real decision genuinely changes: `git_status` now wins. Under a DIFFERENT real state (`presence="absent"`, where `git_status` was never dispatched), the same accumulated graph does NOT leak the favorable history in — the winner reverts to `git_log`, the real baseline.

## 7. Behavioral Evidence

`tests/test_r24_causal_reasoning.py` — 23 tests, independently re-run by the adversarial reviewer (23/23 pass) via their OWN standalone harness script (not merely re-running this file) that traces the real `evaluate()→_act_on()→Governor.dispatch()→GitBot` pipeline and prints every intermediate score, independently reproducing every claimed number:

| Category | Test(s) |
|---|---|
| `causal_state_key()` mechanics | `TestCausalStateKey` (2) |
| `CausalGraph` real accumulation | `TestCausalGraphAccumulation` (4) |
| `_causal_factor()` mechanics (bounded, gated, fail-safe, state-scoped) | `TestCausalFactorMechanics` (7) |
| BEFORE — pre-R24 blindness | `TestBeforeMissingDistinction` (2) |
| AFTER / Flagship — real winner change + intervention control | `TestFlagshipCausalReasoning` (2) |
| Persistence | `TestPersistence` (1) |
| Safety | `TestSafety` (5) |

Exact reward/score arithmetic (real formula, real reward composite, real online-average PolicyMemory update — all independently hand- and script-re-derived by the adversarial reviewer, matching exactly): `GitBot.run()` never sets a `"status"` key for `git_status`/`git_log`, so `completed=0.0` always; with mocked feedback `uf=1.0`, real reward `= 1.0*0.40+0.5*0.25+1.0*0.15+1.0*0.15+0.0*0.05 = 0.825`; 3 identical real dispatches → real edge `strength=0.825, hit_count=3`; `causal_factor = 1.0+(0.825-0.5)*0.1 = 1.0325`. Baseline (causal factor explicitly ablated): `git_log(0.4250) > git_status(0.4150)`. Present (real factor active): `git_status(0.4285) > git_log(0.4250)` — genuine flip. Absent (scope control): `git_log(0.4463) > git_status(0.4358)` — reverts to baseline exactly.

## 8. Causal Controls

- **A. Correlation control**: the edge only ever forms between a real action VECTOR ITSELF dispatched and its real resulting outcome (via the real `_act_on()`→`Governor.dispatch()` path) — not passive co-occurrence of unrelated events.
- **B. Intervention control**: `test_intervention_control_winner_follows_the_dispatched_candidate_not_a_hardcoded_name` swaps which real action_type (`git_log` instead of `git_status`) accumulates the real favorable history, with the baseline confidence edge swapped accordingly — the winner follows the actual dispatched candidate, not a hardcoded `action_type=="git_status"` special case anywhere in `_causal_factor()`. Independently confirmed genuine (not rigged) by the adversarial reviewer.
- **C. Outcome control**: `TestCausalGraphAccumulation` directly proves changing/adding observations changes the real accumulated strength via the real running-average formula (not a fixed/ignored value).
- **D. Scope control**: the flagship's own "SCOPE CONTROL" phase — independently reproduced by the adversarial reviewer via a separate harness — proves `git_status`'s real history, learned only under `presence=present`, does not influence a real `presence=absent` decision; `TestCausalFactorMechanics::test_scope_control_state_key_selects_only_the_matching_edge` proves this at the unit level too.
- **E. Ablation control**: the flagship's own explicit ablation phase (`engine._causal_factor` forced to return neutral, same real accumulated PolicyMemory/CausalGraph data) proves `git_log` still wins — PolicyMemory's own real, favorable, 20%-weighted boost for `git_status` is NOT, by itself, sufficient to flip the race.
- **F. Competing-factor control**: the same ablation phase directly isolates PolicyMemory's real contribution from the causal factor's own additional contribution — both are real signals, but the flip requires the causal factor specifically. `capability_factor`/`workload_factor` are held neutral by construction (GitBot declares both real action_types; `PlanStore` mocked to zero active plans); `situational_factor` (R22) applies identically to both real GREEN candidates, canceling in the relative comparison (independently re-derived and confirmed by the adversarial reviewer's own arithmetic).
- **G. Safety control**: see §10.
- **H. Persistence control**: see §9.

## 9. Persistence

Real and proven: `TestPersistence::test_accumulated_edge_survives_a_real_restart` uses `CausalGraph`'s real production constructor (the shared, disk-backed episodic SQLite connection — not the isolated `json_path=` namespace every other test in the file uses for isolation), with a genuine `close_db_connection()` between write and read. Independently confirmed by the adversarial reviewer: `close_db_connection()` nulls the module-level singleton, forcing a fresh `sqlite3.connect(...)` on next access, and all prior writes went through auto-committing `with conn:` blocks — a genuine restart-survival proof, not an in-process cache artifact.

## 10. Safety Review

- Neither `_causal_factor()`'s nor `causal_state_key()`'s executable body (post-docstring) references `PermissionGateway`, `core.config`, or any GREEN/YELLOW/RED/FORBIDDEN mutation — confirmed both by this session's own source-level test (`TestSafety::test_causal_factor_never_calls_permission_gateway`, which strips the docstring specifically to avoid a prose false-positive) and independently by the adversarial reviewer's own direct read.
- `PermissionGateway._classify()` remains, independently re-confirmed, a pure static function of `action_type` against `core/config.py`'s static lists — zero dependency on `CausalGraph` or any causal signal.
- The real causal-graph write in `_act_on()` occurs strictly AFTER `Governor.dispatch()` has already returned — it cannot have influenced the very dispatch/veto decision that produced the outcome it is recording (`TestSafety::test_causal_write_path_never_touches_governor_or_permission_gateway` proves this via source-position assertion; independently re-confirmed by the adversarial reviewer).
- The factor is strictly bounded `[0.95, 1.05]` — confirmed by direct enumeration of every return path, and by `test_factor_is_strictly_bounded_both_directions` (1000 observations still caps at 1.05).
- Fails safe to neutral `1.0` on any registry/store error, insufficient observations, or absent history — never penalizes VECTOR merely for lacking data (`TestCausalFactorMechanics`'s error/insufficient/no-history tests).

## 11. Adversarial Review

A fresh, independent agent (no inherited context) reviewed all 9 required claims via direct source reads, its own independent hand- AND script-based arithmetic re-derivation (a separate harness reproducing the real pipeline, not merely re-running this milestone's own tests), and its own independently-executed test runs (23/23 R24 suite; 226/226 combined 14-file regression sweep; 37/37 pre-existing `CausalGraph`-adjacent tests unaffected by the schema change).

**Verdict: PASS WITH CONCERNS.** All 9 claims CONFIRMED except one explicitly marked DISPUTED (not a correctness defect):

- **DB-safety allowlist "not exact"**: the reviewer correctly noted the extended allowlist in `test_r18_eq_equation_capability.py` pre-declares `core/causal/causal_reasoner.py` and R25/R26's own future files, none of which exist in R24's actual diff. Explicitly assessed as NOT scope-hiding — it matches this repo's own established, repeated convention (the R19+R20 and R21-R23 blocks in the same allowlist were pre-declared as whole batches before later milestones landed) and is documented in the orchestrator ledger as an intentional 3-milestone batch declaration. Recorded here as a known, deliberate, non-defect deviation from a literal "exact" match.
- **Crux finding on the milestone's own scope** (see §12, Limitations, and §14, What This Does NOT Prove, below): the reviewer's own honest assessment — "closer to a state-scoped generalization of PolicyMemory than to differentiated multi-outcome causal inference" — is accepted here in full and is the basis for this report's own, deliberately narrower, capability classification in §13. This is a disclosure/framing matter, not a functional or safety defect: every other claim (real state-scoping, real accumulation, real production path, real ablation/scope/intervention proofs, real safety isolation) was independently CONFIRMED.

No repair cycle was needed for any correctness defect — both concerns are honestly incorporated into this report's own claims rather than fixed in code, per the mission's own "distinguish implemented/integrated/behaviorally proven/etc." discipline.

## 12. Regression

Full 14-file sweep (`test_decision_engine.py`, `test_r10_decision_provenance.py`, `test_task91_r6_candidate_diversity.py`, `test_task92_r7_decision_candidate_correlation.py`, `test_r15_...` through `test_r24_causal_reasoning.py`) — 226/226 pass, independently re-run by the adversarial reviewer, zero unresolved regression. Pre-existing `CausalGraph`-adjacent tests (`tests/integration/test_spec11_year2_gaps.py`, 37 tests covering the schema/behavior this milestone changed) — 37/37 pass, confirming the `hit_count` migration and accumulation-not-overwrite change did not break any pre-existing real caller.

## 13. Exact Capability Classification (mission's own L0-L5 scale)

- **L0 (causal information stored)**: PROVEN. Real, state-scoped, accumulated edges with real observation counts.
- **L1 (causal information retrieved)**: PROVEN. Real `get_outcomes()` query inside `_causal_factor()`.
- **L2 (causal information influences decisions)**: PROVEN. Real, bounded, gated post-score multiplier wired into every real `evaluate()` call.
- **L3 (causal relationships learned from real experience)**: PROVEN. Edges accumulate exclusively from real `_act_on()` outcomes of real dispatched actions — never hand-constructed in the flagship path.
- **L4 (learned causal relationship changes later behavior)**: PROVEN. The flagship's own later, separate `evaluate()` call genuinely changes winner, independently re-derived by the adversarial reviewer via a separate harness.
- **L5 (transfers to materially different situations)**: NOT CLAIMED, BY DESIGN. State-scoping is itself a Scope Control requirement (an edge learned under one state must not affect an unrelated state) — cross-situation transfer is R21's own, separate, already-proven capability axis, not an R24 goal.

**Important scope-precision note (per §11's adversarial finding, accepted in full)**: what is PROVEN at L0-L4 above is specifically a **state-conditioned, minimum-observation-gated, real-experience-derived REWARD EXPECTATION** — "how favorably has this action tended to go, under conditions like now, based on real repeated self-experience" — not a differentiated, multi-outcome "this specific action under this specific state predicts THIS specific distinct consequence rather than THAT one" causal model. In the real path this milestone's own flagship exercises, the outcome side of every edge is always `outcome:unknown` (`GitBot.run()` never sets a `"status"` key on its return value) — the *quality* of the outcome varies and is learned (via `strength`), but the outcome's own *identity/type* does not. `CausalGraph`'s own BFS/common-cause/chain-traversal machinery (`get_causal_chain`, `find_common_causes`, `get_influence_score`) is real and untouched by this bug, but is not exercised by the specific signal `_causal_factor()` reads.

## 14. What This Milestone Does NOT Prove

- Does NOT prove differentiated, multi-outcome consequence prediction (i.e., predicting WHICH of several distinct real outcomes will follow an action) — only a scalar, state-conditioned expected-reward signal, honestly scoped in §13.
- Does NOT prove generalization/transfer across materially different real states (L5) — explicitly out of scope by design (state-scoping is a safety/correctness requirement, not a gap).
- Does NOT prove causal reasoning in the formal statistical sense (no confounder adjustment, no do-calculus, no counterfactual "what would have happened under the untaken action") — this was never attempted; Phase 1's own adversarial investigator (R24-I) explicitly scoped the mission's own definition to "state-conditioned repeated-experience prediction," and this report does not claim more than that.
- Does NOT fix `core/causal/causal_reasoner.py`'s pre-existing, independently-confirmed `source`/`target` key-mismatch bug — deliberately deferred as out of R24's own required scope (R24 never depends on or calls into that module).
- Does NOT claim any change to `PermissionGateway`/`Governor`/safety-tier semantics — independently reconfirmed untouched.

## 15. Next Bottleneck

The state-conditioned reward-expectation signal built here is a real, minimal, honestly-scoped substrate — but the single real production writer (`GitBot.run()` for `git_status`/`git_log`) never differentiates real outcome identity, which caps how much richer this signal can honestly become without a deliberate, separately-justified change to real district-agent return shapes (out of R24's own scope). For R25 (Mental Simulation), the most direct, honest substrate to build on is this same real, accumulated, state-scoped expectation — NOT a claim of differentiated outcome prediction — consistent with the mission's own explicit R25 framing ("what is likely to happen next, and how does that affect my choice" can legitimately be answered with a real expected-value estimate; a claim of predicting a SPECIFIC distinct future state would require new evidence this milestone does not provide).

## 16. Files Changed

`core/memory/causal_graph.py` (+~60 lines: `causal_state_key()`, `hit_count` migration, `add_edge()` real accumulation), `core/loop/autonomous_loop.py` (+~10 lines: state-scoped node id in the real writer), `core/loop/decision_engine.py` (+~90 lines: `_get_causal_graph()`, `_causal_factor()`, `_causal_state_key()`, `CAUSAL_MIN_OBSERVATIONS`, wiring into `_score_candidate()`'s formula/reasoning_chain/reasoning_steps), `tests/test_r24_causal_reasoning.py` (new, 23 tests), `tests/test_r18_eq_equation_capability.py` (DB-safety allowlist extended for the R24-R26 batch, per established precedent).
