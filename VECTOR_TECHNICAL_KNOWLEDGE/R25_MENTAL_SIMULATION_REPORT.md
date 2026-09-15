# R25 — Mental Simulation + Consequence Evaluation Report

## 1. Authoritative Starting HEAD

`830eb27b5a8c1e8056774bda77230405394c5ff9` (R24's own committed HEAD), clean working tree at the start of this milestone. See `VECTOR_TECHNICAL_KNOWLEDGE/R24_R26_ORCHESTRATOR_LEDGER.md` for the full R25 discovery trace (3 investigators: substrate audit, decision-integration seam, and a fresh adversarial pre-implementation reviewer who independently queried the real production database).

## 2. Ending HEAD

`473fd22c57988879bf0ee8f310da1ef7eb3905eb` — committed, working tree clean (except pre-existing, unrelated untracked files from concurrent repo activity — see §12).

## 3. BEFORE Capability

No real, structured, pre-decision consequence prediction existed anywhere in the decision path. `districts/predictive_analytics/causal_simulator.py::CausalSimulator` is a genuine Monte Carlo engine (real RNG sampling, real convergence detection, real confidence intervals) — but Phase 1's discovery, independently confirmed by a fresh adversarial reviewer who read every real call site, found it has NEVER, anywhere in this codebase, been connected to a specific real `Candidate.action_type`; every real caller feeds it hand-specified, generic scenario parameters unrelated to any particular candidate. `core/causal/causal_reasoner.py::CausalReasoner.what_if()` was confirmed to be a live, disqualified shortcut: it ignores its own `action`/`hypothetical` arguments and returns generic aggregate `CounterfactualMemory.get_rejection_patterns()` corpus stats, identical regardless of which two candidates are compared — explicitly rejected as a substrate.

R24's own real, causal signal (`_causal_factor()`) has a disclosed, adversarially-confirmed limitation: it reads a single BLENDED scalar average across all of a state-scoped action's real outcome edges — it cannot distinguish "usually succeeds, occasionally fails a specific way" from "always mediocre." Two real candidates with identical formula inputs but materially different real risk profiles (one with a real, empirically-observed chance of hitting a genuine dispatch failure; one with no history at all) could not be distinguished on that basis before this milestone.

## 4. Implementation

One real, minimal addition, reusing R24's own already-proven substrate — no new subsystem, no new store, no new Monte Carlo apparatus:

- **`Candidate.simulated_consequence: dict`** — new field, populated pre-scoring.
- **`DecisionEngine.evaluate()`**: a THIRD pre-scoring enrichment step (after the existing RULE 1 context injection and RULE 8 reasoning-bank injection) calls `_simulate_consequence(c)` for every real candidate.
- **`_simulate_consequence(candidate)`**: queries the same real `CausalGraph.get_outcomes()` R24 established, for the candidate's own real, state-scoped action node — but reads the FULL edge list as a categorical distribution over DISTINCT real outcome-node labels, not R24's blended average. Returns `{"status": "error"}` / `{"status": "no_history"}` / `{"status": "insufficient_data", "n_observations": N}` (gated by `SIMULATION_MIN_OBSERVATIONS = 3`, same honesty threshold as R24) / `{"status": "predicted", "n_observations": N, "outcome_distribution": {...}, "bad_outcome_probability": p}`. "Bad outcome" is a real, generic label set (`SIMULATION_BAD_OUTCOME_LABELS`) matching `Governor.dispatch()`'s own real, honest dispatch-failure statuses (`"no_agents"`, `"no_capable_agent"`, `"timeout"`, `"error"`) — not a fabricated taxonomy.
- **`_simulation_factor(candidate)`**: reads (never re-derives) `candidate.simulated_consequence`, returns a bounded `[0.90, 1.0]`, PENALTY-ONLY 6th post-score multiplier — deliberately asymmetric (never a boost) since a real, observed chance of a known-bad outcome should only ever count against a candidate.

## 5. Production Path

Independently re-confirmed by the adversarial reviewer via direct source read: `evaluate()` unconditionally populates `c.simulated_consequence` for every real candidate scored, and `_score_candidate()` unconditionally calls and multiplies in `_simulation_factor()` for every real `evaluate()` call.

## 6. AFTER Capability

Two real, materially different action_types (`git_status`, `git_log` — real `GitBot` capabilities) with a real confidence edge chosen so the base formula plus R24's own real causal factor together still favor `git_status`. After `git_status` accumulates a real, MIXED, categorically-distinct outcome history under a real `presence="present"` state — 3 real successful dispatches (`outcome:unknown`) and 2 real, honest Governor `"no_agents"` refusals (the isolated registry's agent map genuinely cleared, not a fabricated failure) — a LATER, SEPARATE real decision changes: `git_log` now wins, specifically because of the real, observed 40% chance of a genuine known-bad outcome, a distinction R24's own blended-average signal alone does not provide (independently verified: with R24's causal factor real but R25's simulation factor ablated, `git_status` still wins — only R25's addition flips it).

## 7. Behavioral Evidence

`tests/test_r25_mental_simulation.py` — 18 tests, independently re-run by the adversarial reviewer (18/18 pass) plus their OWN standalone reproduction script (not the test file) reproducing every claimed number exactly:

| Category | Test(s) |
|---|---|
| `_simulate_consequence()` mechanics (real categorical distribution, honesty gates) | `TestSimulateConsequenceMechanics` (5) |
| `_simulation_factor()` mechanics (bounded, penalty-only, fail-safe) | `TestSimulationFactorMechanics` (4) |
| BEFORE — no field, R24 alone blind to outcome-type distribution | `TestBeforeMissingDistinction` (2) |
| AFTER / Flagship — real winner change via R25 specifically (not R24) | `TestFlagshipMentalSimulation` (1) |
| Safety | `TestSafety` (6) |

Exact reward/score arithmetic (independently re-derived by the adversarial reviewer via their own separate script): `GitBot.run()` never sets a `"status"` key for `git_status` → `completed=0.0` always; real dispatches with mocked feedback `uf=1.0` → real reward `0.825` (3x, real success); with the isolated registry's agent map genuinely cleared, `Governor.dispatch()` returns the real, honest `{"status": "no_agents", ...}` (confirmed distinct from `"no_capable_agent"`, which only fires when agents exist but lack the capability) → with mocked feedback `uf=0.0`, real reward `0.425` (2x). Real accumulated edges: `outcome:unknown` hit_count=3/strength≈0.825, `outcome:no_agents` hit_count=2/strength≈0.425 → R24's `causal_factor=1.0165` (mild boost, blended average 0.665 sits above the 0.5 midpoint) vs. R25's `bad_outcome_probability=0.40 → simulation_factor=0.94` (real penalty). Baseline (both factors ablated): `git_status(0.3830) > git_log(0.3750)`. Causal-only (R24 real, R25 ablated): `git_status(0.3893) > git_log(0.3750)` — R24 alone only reinforces, does not flip. Both real: `git_status(0.3660) < git_log(0.3750)` — genuine flip, attributable specifically to R25.

## 8. Simulation Controls (mission's own R25 control list)

- **A. No-simulation control**: the flagship's own "causal-only" phase (R25's `_simulation_factor` ablated, R24's `_causal_factor` real) proves removing R25's own signal returns the decision to a `git_status`-favoring baseline — R25's addition is what changes the outcome, not a byproduct of R24.
- **B. Candidate swap**: `_simulate_consequence()`/`_simulation_factor()` read `candidate.action_type`/`candidate.context_snapshot` directly — no hardcoded action-type branch anywhere in either method (confirmed by source read; no `if candidate.action_type == "git_status"` anywhere).
- **C. Situation swap**: `_simulate_consequence()` reuses R24's own `causal_state_key()` — a real edge learned under one state is architecturally invisible to a query under a different state (same real mechanism R24's own Scope Control already proved; not re-derived here to avoid duplicating R24's own test).
- **D. Causal ablation**: the flagship's explicit three-phase design (both ablated → causal-only → both real) directly proves R25's own signal is necessary for the flip; R24's causal factor alone does NOT secretly retain the same answer.
- **E. Policy isolation**: PolicyMemory's own real, favorable accumulated score for `git_status` (0.665, pulled up by the 3 real successes) is present and real in ALL THREE comparison phases — it is not what explains the flip, since it is identical across all three; only the simulation factor differs.
- **F. R6 isolation**: a real, genuine R6 staleness-diversity confound was discovered DURING implementation (the accumulation phase's own 5 consecutive single-candidate `evaluate([c])` calls genuinely triggered `_select_staleness_aware_winner()`'s real 5-consecutive-win suppression) — independently verified by the adversarial reviewer to be real (they reran the baseline WITHOUT the reset and confirmed R6 firing incorrectly attributes the winner change to R6 rather than the real formula, which is exactly why an explicit `engine._winner_streak_hash = None; engine._winner_streak_count = 0` reset was added, with a comment explaining it is a disclosed test-methodology artifact isolation, not a way to suppress an inconvenient result).
- **G. Epistemic isolation**: not separately ablated in this flagship (R24's own flagship already proved epistemic dampening requires explicit real time-backdating to activate, per R16's established pattern — none occurs here, so `_epistemic_penalty()` stays neutral throughout by construction, not by suppression).
- **H. Safety**: see §10.
- **I. Persistence**: not claimed as a new persistence axis — `simulated_consequence` is a stateless, per-`evaluate()`-call derived value (same category as R22's own `_situational_factor()`); the underlying `CausalGraph` persistence is R24's own, already proven.

## 9. Anti-Hallucination Compliance

Independently confirmed by the adversarial reviewer: zero LLM/inference calls anywhere in `_simulate_consequence()` or `_simulation_factor()`. `outcome_distribution` is a real, structured, inspectable `{outcome_node_id: float}` dict derived entirely from real `hit_count` data — never natural-language prose, never a single LLM completion presented as evidence a simulation occurred.

## 10. Safety Review

- Neither `_simulate_consequence()`'s nor `_simulation_factor()`'s executable body references `PermissionGateway`, `core.config`, `Governor.dispatch`, or any GREEN/YELLOW/RED/FORBIDDEN mutation — confirmed by this session's own source-level tests and independently by the adversarial reviewer's own grep.
- Independently confirmed: zero references to `simulated_consequence`/`simulation_factor`/`_simulate_consequence` anywhere in `core/loop/autonomous_loop.py::_act_on()`'s real veto chain (CounterfactualMemory/ThreatDetector/RedTeamAgent) or `core/city/governor.py::dispatch()` — a "predicted-safe" simulation result cannot skip or soften any real safety check, by construction (grep-verified zero coupling, not merely asserted).
- Strictly bounded `[0.90, 1.0]`, penalty-only — confirmed by direct enumeration of the clamp expression and by `test_factor_is_strictly_bounded_and_penalty_only` (1000 observations still floors at 0.90, never exceeds 1.0).
- Fails safe to neutral `1.0` on any graph error, missing history, or insufficient observations.
- `AgentRegistry.deregister()` (the "natural" way to remove an agent) was independently confirmed by the adversarial reviewer to trigger real Darwinian ghost-memory/successor-respawn side effects — the flagship deliberately avoids it, directly clearing the isolated registry's internal map instead, to produce a genuinely empty district and a real, honest `Governor`-level `"no_agents"` refusal without any unrelated side effect.

## 11. Adversarial Review

A fresh, independent agent (no inherited context) reviewed all 9 required claims via direct source reads and its own independent standalone reproduction script (not merely re-running this milestone's own tests).

**Verdict: PASS WITH CONCERNS.** All 9 claims CONFIRMED, including an explicit, independently-reproduced divergence case proving R25's signal is materially different from R24's (same edges, `causal_factor=1.0165` mild boost vs. `simulation_factor=0.94` real penalty). The reviewer specifically re-ran the flagship's baseline WITHOUT the R6 streak reset and confirmed R6 would otherwise fire and falsely attribute the result to staleness-suppression rather than the real formula — independently validating the reset as a legitimate, disclosed control rather than a way to dodge an inconvenient result. The sole non-blocking finding: this report and the ledger's own R25 phase entry did not exist at the time of review (paperwork gap, not a code/behavioral defect) — resolved by this document and the ledger update accompanying this commit.

No repair cycle was needed for any correctness or safety defect.

## 12. Regression

`tests/test_r25_mental_simulation.py`: 18/18 pass, independently re-run by the adversarial reviewer. Combined 15-file regression sweep (`test_decision_engine.py` through `test_r25_mental_simulation.py`, 244 tests): 243/244 pass. The single failure, `test_r18_eq_equation_capability.py::TestProductionDBSafety::test_git_worktree_confirms_only_expected_files_modified`, is independently confirmed (both by this session and by the adversarial reviewer) to be caused ENTIRELY by untracked files unrelated to this milestone (`docs/CODEX_VECTOR_V1_HANDOFF.md`, `docs/VECTOR_OS_LONG_TERM_VISION.md`, `docs/VECTOR_FORENSIC_AUDIT_REPORT_2026-09-15.md`, `.claude/settings.local.backup-2026-09-14.json`, `tools/vector_dev_orchestrator/`) — genuine concurrent, unrelated activity in this shared repository (per this session's own git discipline: one mutation owner per coupled subsystem; these files are neither read, written, nor referenced by any R24-R26 code or test, and this session's own commits stage only its own explicit file list, never `git add -A`). **Classified per the mission's own failure taxonomy: Type D (pre-existing, unrelated) / Type C (environment)** — not investigated further, not fixed, not touched, consistent with this session's scope discipline.

## 13. Exact Capability Classification (mission's own S0-S5 scale)

- **S0 (simulation representation)**: PROVEN. `simulated_consequence` is a real, structured, inspectable dict.
- **S1 (simulation generated)**: PROVEN, with an explicit, honest scope boundary — the "simulation" is a real, honest RETRIEVAL against VECTOR's own real accumulated experience (a categorical outcome-type distribution), not a generative forward rollout. `CausalSimulator`'s real Monte Carlo machinery was investigated and explicitly rejected as substrate (Phase 1 discovery, independently confirmed): using it honestly would require either fabricated per-action_type calibration parameters or deriving them from a single real scalar, adding manufactured precision with zero real added signal.
- **S2 (simulation influences decision)**: PROVEN. Real, bounded, gated post-score multiplier wired into every real `evaluate()` call.
- **S3 (simulation uses learned causal knowledge)**: PROVEN. Built directly on R24's own real, state-scoped `CausalGraph` edges — the exact same real data, read differently.
- **S4 (simulation changes real action selection)**: PROVEN. The flagship's three-phase design (ablated → causal-only → both real) isolates and proves this specifically, distinct from R24's own already-proven S-equivalent (L4).
- **S5 (simulation remains useful across materially different situations)**: NOT CLAIMED. Same scope boundary as R24's own L5 — state-scoping is a correctness requirement (an edge/distribution learned under one real state must not apply to a materially different one), not a gap to close here.

## 14. What This Milestone Does NOT Prove

- Does NOT prove generative/forward world-model simulation (no hypothetical trajectory rollout, no predicted FUTURE STATE beyond a real, empirically-observed outcome-type distribution from past real experience).
- Does NOT wire `CausalSimulator`'s real Monte Carlo engine into any real candidate — explicitly and deliberately rejected as substrate per Phase 1's own adversarial finding (would require fabrication to bridge).
- Does NOT prove S5 (cross-situation transfer) — an explicit, deliberate non-goal, matching R24's own scope boundary.
- Per the adversarially-confirmed empirical finding from R24's own Phase 1 discovery (every real production causal edge currently has `hit_count=1`): in a lightly-used real system, `_simulate_consequence()` will honestly return `"insufficient_data"`/`"no_history"` far more often than `"predicted"` — this is by design, not a defect, and this report does not claim otherwise.
- Does NOT reuse or fix `core/causal/causal_reasoner.py::CausalReasoner.what_if()` — independently reconfirmed as a live, disqualified shortcut (ignores its own arguments, returns generic corpus stats) and deliberately not touched or depended upon.

## 15. Next Bottleneck

R25's own real substrate is identical in kind to R24's (real, state-scoped `CausalGraph` edges) — richer in shape (categorical vs. blended) but bounded by the same real data-sparsity limitation Phase 1's adversarial investigator empirically confirmed in the live production database. For R26 (Cognitive Integration), the most direct, honest path is to trace the FULL real production chain (perception → R22 situation → R23 world/self → R24 causal → R25 simulation → decision → governance → action → outcome → learning) end-to-end in ONE real scenario, and to explicitly audit for disconnected stages, duplicated reasoning, or state lost between stages — per the mission's own explicit R26 architecture-audit requirement — rather than assuming the six real post-score factors already compose into a coherent loop merely because each was individually proven.

## 16. Files Changed

`core/loop/decision_engine.py` (+~100 lines: `Candidate.simulated_consequence` field, `SIMULATION_MIN_OBSERVATIONS`/`SIMULATION_BAD_OUTCOME_LABELS` constants, `_simulate_consequence()`, `_simulation_factor()`, pre-scoring enrichment wiring in `evaluate()`, post-score multiplier wiring in `_score_candidate()`, plus a stale-comment fix on `Candidate.context_snapshot` predating this milestone), `tests/test_r25_mental_simulation.py` (new, 18 tests).
