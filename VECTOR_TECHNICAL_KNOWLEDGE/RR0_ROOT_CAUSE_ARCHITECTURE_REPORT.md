# RR-0 ROOT-CAUSE ARCHITECTURE REPORT

## 1. Executive Diagnosis

1. **`result["goal_progress"]` is never written by any action handler in the entire codebase** (exhaustive grep, zero hits) — it permanently defaults to 0.5 inside the main reward formula, making the formula's 25%-weighted "goal-aware" term structurally unreachable. This is the single deepest root cause of FACT 2 and FACT 5.
2. **Two structurally separate dispatch paths exist**: Path A (`AutonomousLoop._act_on()`, DecisionEngine-selected actions) writes to PolicyMemory/CausalGraph/EpistemicTracker; Path B (direct `governor.dispatch()` calls, e.g. the VectorIntel/document_feature background sweep) writes to **none of them** — only HP. This fully explains FACT 3.
3. **`update_goal_progress()` unconditionally sets `status="completed"` at `progress>=1.0` with no one-shot/recurring distinction** — a real, already-acknowledged, still-open gap from a prior fix (Task 89C, 2026-09-08). This is why `g_daily_commit`-tagged candidates (like `read_code`) permanently score `goal_alignment=0.00`.
4. **`goals_v1` shows a state its own single owning method cannot produce**: real production data (captured directly during RG-D) shows `g_daily_commit` at `progress=1.0, status="active"` — but `update_goal_progress()`'s own unconditional rule means reaching `progress=1.0` through that method would force `status="completed"`. Since it's still `"active"`, this value was written through some OTHER path to the `goals_v1` semantic_memory key, bypassing the one function meant to own completion semantics. This is a genuine, previously-undocumented finding.
5. **`/command`'s successful-classification action branch bypasses `Candidate`/`DecisionEngine.evaluate()`/`PermissionGateway.execute()` entirely**, calling `GovernorCouncil().dispatch()` directly — a second, parallel, gateway-adjacent-but-not-gateway path sitting ~90 lines above the "real" Candidate-based path in the same file. Root cause of FACT 1.
6. **The intent classifier is deliberately biased toward "just respond"** on ANY ambiguity (timeout, parse error, low confidence, unrecognized district) — by explicit design ("errs toward talking, not doing, whenever it isn't sure"). This is a defensible safety default, not a bug, but it means most open-ended owner instructions never reach real cognition.
7. **R24's causal factor and PolicyMemory both consume the exact same blended, largely status-driven reward value** — not an independent "execution utility" signal. CausalGraph's `strength` is set to `reward` verbatim (identity clamp). There is no separate "goal utility" signal anywhere for R24 to have consumed instead — the ambiguity is resolved: it's neither a `R24` bug nor an "ambiguous blended reward" mystery, it's a single, traceable, shared reward with a structurally-neutralized goal term.
8. **A prior fix (Task 89C) correctly removed a real bug** (blind reward-scaled goal-progress accumulation was silently auto-completing recurring goals) **but left no replacement** — this was explicit, documented, and intentional at the time ("a future task should design a proper recurring-goal type"). RR-0's findings are the direct continuation of that acknowledged gap, not a new problem.
9. **At least 4 numerically-incompatible "reward" formulas coexist** (main 5-factor ≈0.755, VectorCode binary {0.3,0.8}, plan-step binary {0.3,0.7}, HP economy — fully independent), all feeding into the same PolicyMemory/CausalGraph stores under one shared `action_type`+`situation_hash` key.
10. **Existing machinery is sufficient for a minimal repair** — `RetryQueue`, `CounterfactualMemory.should_avoid()`, `EpistemicTracker`, and the `Candidate`/`DecisionEngine`/`PermissionGateway` pipeline all already exist and are production-reachable; none of the five audits found a case requiring new architecture.

## 2. Owner Command Trace

```
POST /command
 → scan_text() [prompt-injection check]                          commands.py:86
 → ctx_engine.session_hydration_prompt()                          commands.py:117
 → _detect_intent_action(text)  [Stage 0: deterministic keywords] commands.py:126, 509-605
     ├─ MATCH (9 fixed keyword categories + widget/app-launch)
     │    → build real Candidate → decision_engine.evaluate() → perm_gateway.execute()   commands.py:258-330
     │       (PolicyMemory + CausalGraph ARE written here — RULE 7 intact)
     └─ NO MATCH → action_type="respond" → FAST-PATH
          → governor.classify_chat_intent(text)  [Stage 1: regex → embedding → 12s-timeout LLM]  commands.py:152, governor.py:1316
              ├─ TIMEOUT (12s) / parse error / low confidence / unrecognized district
              │    → fallback = {"type": "answer_question"}                    governor.py:1342,1351,1358,1368,1374,1493-1515
              │    → _llm_answer()  [pure text, self-disclosed no tool-calling]  commands.py:222
              │       (NOTHING written to PolicyMemory/CausalGraph — only a
              │        reasoning_chains "respond" row + episodic turn)
              └─ classified action (type != "answer_question")
                   → builds bespoke gov_task dict
                   → GovernorCouncil().dispatch(gov_task)  DIRECTLY               commands.py:154-220
                      (bypasses DecisionEngine.evaluate() AND PermissionGateway.execute()
                       entirely; writes only a reasoning_chains row with reward
                       HARDCODED to 0.8/0.4 by request status, plus episodic log —
                       zero PolicyMemory/CausalGraph write)
```

**The exact bypass point**: `core/api/routers/commands.py:154-220` — the classify_chat_intent-routed action branch. This is a fully separate execution path from the Candidate/DecisionEngine/PermissionGateway pipeline that exists ~90 lines below it in the SAME file.

**Answers to Audit A's 10 questions** (in short): (1) only the 9-category keyword map reaches DecisionEngine; (2) everything else bypasses it; (3) timeout → `answer_question` fallback, no action; (4) same fallback on error; (5) same fallback on ambiguity; (6) **yes**, by explicit design; (7) no, for the classify_chat_intent path — yes, for the stage-0 keyword path; (8) no evidence of command-path goal/plan creation; (9) only the stage-0 path writes PolicyMemory/CausalGraph; (10) **yes** — the stage-0 Candidate-construction block at L258-330 is the reusable seam.

## 3. Reward Map

| WRITER | INPUTS | FORMULA | RANGE | STORE | ACTION KEY | SITUATION KEY | GOAL-AWARE? | FAILURE-AWARE? |
|---|---|---|---|---|---|---|---|---|
| Main `_act_on()` reward (`autonomous_loop.py:1319-1336`) | `status`, `goal_progress` (defaults 0.5, never set), `overridden`, `corrected`, optional user_feedback | `uf·.40+goal_progress·.25+not_overridden·.15+not_corrected·.15+completed·.05` | 0–1 (≈0.755 typical) | PolicyMemory, CausalGraph, EpistemicTracker | `action_type` | `situation_hash` | Nominally yes, structurally unreachable | Partial |
| VectorCode reward (`autonomous_loop.py:1097`) | `status` | `0.8` ok / `0.3` else | {0.3,0.8} | PolicyMemory, CausalGraph | `action_type` | `situation_hash` | No | Binary |
| Plan-step reward (`autonomous_loop.py:1587-1588`) | `status=="completed"` | `0.7`/`0.3` | {0.3,0.7} | PolicyMemory, CausalGraph | `action_type` | `situation_hash` | No | Binary |
| `/command` GovernorCouncil path (`commands.py:199`) | request status | hardcoded `0.8`/`0.4` | {0.4,0.8} | `reasoning_chains` only | — | — | No | Binary, **never reaches PolicyMemory/CausalGraph** |
| CausalGraph strength (`autonomous_loop.py:1402`) | the `reward` variable from whichever formula ran | `clamp(reward,0,1)` identity | 0–1 | `causal_edges` | `action:{type}@{state}` | `causal_state_key(context_snapshot)` | Same as source | Same as source |
| Goal progress update | (historically reward-scaled; removed Task 89C 2026-09-08) | **no automatic writer exists** | — | `goals_v1` | goal_id | — | N/A — disconnected | N/A |
| HP/reputation (`agent_base.award_points`/`deduct_points`) | caller-supplied fixed points + reason string, `repeat#N` diminishing multiplier | direct add/sub | 0–1000 | `agent.health_points` | agent name | — | No | Partial (reason string only) |
| CounterfactualMemory rejection | proposal similarity, `should_avoid()`≥0.7 | pre-execution veto | boolean | `rejections` | `decision_id` | — | No | Only for never-executed candidates |
| EpistemicTracker belief | `status`→outcome string | bucketed confidence nudge | 0–1 | `claims` | `action_domain:{type}` | — | No | Partial, **Path A only** |

**Why `read_code` with `goal_alignment=0.00` gets ~0.755**: `goal_alignment` (candidate-selection term, 30% weight) and `goal_progress` (reward term, 25% weight) are two different, never-connected fields. `goal_progress` defaults to 0.5 (never written by any handler — confirmed exhaustive grep). Plugging real values (`status="ok"`→`completed=1.0`, no user feedback→`uf=0.7`, `goal_progress=0.5` default, not overridden/corrected→`1.0,1.0`): `0.7×.40+0.5×.25+1.0×.15+1.0×.15+1.0×.05 = 0.755` — exact match to every observed value across RG-A through RG-D.

**Verdict**: reward meanings are **fragmented, not unified** — at least 4 numerically incompatible formulas feed the same stores under the same keys.

## 4. Goal Progress Trace

```
GoalSystem.generate_immediate_actions()          goal_system.py:369-418
  SHORT goals: unconditional, no progress gate     L389-401  ← g_daily_commit (SHORT) regenerated EVERY tick
  MID/LONG goals: gated by progress==0.0 only       L403-416
        ↓
Candidate.goal_ids tagged                          (via _tag_derived_action_types)
        ↓
_score_goal_alignment()                            decision_engine.py:419-433
  no goal_ids → 0.3 default
  else → max(priority/10 × (1.0 − progress)) over tagged goals
        g_daily_commit: priority=7, progress=1.0 → 7/10×(1−1.0) = 0.00   ← EXACT source of goal_alignment=0.00
        ↓
[action executes] → result
        ↓
Progress write-back:  NONE — reward-scaled auto-update removed 2026-09-08 (Task 89C),
                       replaced with a debug-only log line, no mutation.
                       (analyze_progress's own handler was not found to independently
                       write goal progress either.)
        ↓
loop:current_goal = save_goal(winner.goal_ids[0])   autonomous_loop.py:981-983
                     — a pure checkpoint of whatever the WINNING candidate carried,
                       not an independent prioritization/staleness check.
```

**Broken/missing couplings**:
- **Missing**: any automatic action-outcome→progress writer (intentionally removed, never replaced).
- **Missing**: a SHORT-goal "already done" cutoff analogous to MID/LONG's `progress==0.0` gate — so `g_daily_commit` (progress=1.0) is still unconditionally regenerated as a candidate source every tick.
- **Missing**: one-shot vs. recurring/habitual goal semantics inside `update_goal_progress()` itself — an explicitly acknowledged, still-open gap from Task 89C.
- **Broken/inconsistent** (new finding, cross-referenced against real RG-D data): `g_daily_commit`'s real persisted state is `progress=1.0, status="active"` — a combination `update_goal_progress()`'s own unconditional rule should make unreachable through that method. Some other write path to the `goals_v1` key produced this state.
- `get_active_goals()` filters only on `status=="active"` — progress is never consulted, so a completed-in-substance-but-not-in-status goal remains fully "active" indefinitely.
- Goal progress does **not** feed reward, PolicyMemory, or CausalGraph in either direction — `goal_alignment` (selection-time) is the only place goals touch scoring at all.

## 5. Failure Learning Trace

**VectorIntel case**: `_check_availability()` never raises; sets `available=False`, logs WARNING only; `run()`'s failure branch returns a dict with **no `"status"` key at all** (`districts/intelligence/vectorintel_agent.py:101-121, 222-228`). In `governor.dispatch()`, `result.get("status")` is therefore `None` — matches neither `"ok"` nor `"error"`, so not even the HP penalty fires here. Only a generic untagged episodic log is written. This is **Path B** — no wiring to PolicyMemory/CausalGraph/CounterfactualMemory/EpistemicTracker exists for Path B at all.

**TechnicalWriter/document_feature case**: also Path B; status resolves to `"error"`/`"failed"`, so `deduct_points` fires (HP consequence, confirmed) — but `governor.dispatch()` (`core/city/governor.py:2010-2463`) contains **zero** calls to PolicyMemory/CausalGraph/CounterfactualMemory/EpistemicTracker anywhere in its body. No retry, no reroute, no consultation of prior failures before the next identical dispatch.

**DecisionEngine failure path (Path A, for comparison)**: `AutonomousLoop._act_on()` (Path A, DecisionEngine-selected actions only) DOES write PolicyMemory, CausalGraph, and EpistemicTracker (`autonomous_loop.py:1343,1349,1402`). This is why `action_domain:read_code` has a live epistemic claim but `action_domain:vectorintel`/`document_feature` do not.

**Where the signal is lost**: at the very first hop — `governor.dispatch()` itself, for any task NOT originating from a DecisionEngine-selected Candidate, has no call sites into any learning store. The signal isn't "collapsed" or "misclassified" downstream — it simply **never enters** the learning pipeline in the first place for Path B.

`CounterfactualMemory.record_rejection` is confirmed **pre-execution-only** (blocks/vetoes candidates before they run) — architecturally incapable of representing "an action was selected, ran, and failed," regardless of which path it came from.

## 6. Existing Mechanism Inventory

| Item | Classification | Note |
|---|---|---|
| Goal progress delta calculator | ABSENT | `update_goal_progress` takes an absolute float, not a delta |
| Task/action utility scoring | ABSENT | — |
| Outcome/result quality assessment | ABSENT | — |
| Novelty detection | ABSENT | — |
| Artifact tracking | ABSENT | — |
| Failure/loss-streak counter (DecisionEngine-level) | ABSENT | R6 only tracks win-streaks |
| Failure/loss-streak counter (elsewhere) | IMPLEMENTED BUT DISCONNECTED | `districts/coding/vector_mlops/.../doom_loop.py` — isolated to one coding-agent tool loop |
| Capability/agent health → candidate scoring | IMPLEMENTED BUT DISCONNECTED | `core/resilience/circuit_breaker.py` exists; zero references from `decision_engine.py` |
| Retry/backoff on failed dispatches | IMPLEMENTED + PRODUCTION-REACHABLE (narrow) | `core/queue/retry_queue.py`, only fires on unhandled exceptions, not soft `status≠"ok"` |
| `CounterfactualMemory.should_avoid()` (read-side) | IMPLEMENTED + PRODUCTION-REACHABLE | Called as pre-execution veto only, never from DecisionEngine's own scoring |
| EpistemicTracker failure/non-novelty penalty | ABSENT | No such method exists on the tracker |
| Reflection loop write-back | PARTIAL | Exists (2AM cycle); write-back to scoring not confirmed |
| Critic/self-evaluation | ABSENT | — |
| `meta_cognition.py` bias detection | IMPLEMENTED + PRODUCTION-REACHABLE, wrong signal | Detects overconfidence/recency/confirmation bias, not "repeated zero-goal-progress action" |
| Plan outcome/completion criteria | IMPLEMENTED BUT DISCONNECTED | Real `expected_outcome`/`actual_outcome` machinery in `plans.py`, but `data/plans/` is empty in production — unused |
| `synthesis_bridge.py`/`hypothesis_engine.py` as anomaly detectors | ABSENT for this purpose | Different tool (cross-domain text merging, not numeric-pattern detection) |

**Highest-leverage reusable assets**: the Task-89C removal itself (restoring correctly, not re-adding the old bug), and `RetryQueue`+`should_avoid()` (already production-reachable, just need soft-failure routing).

## 7. Root Causes

**P0** (structural, explains multiple facts):
- P0-1: `result["goal_progress"]` never written anywhere → reward's goal-aware term structurally unreachable (FACT 2, FACT 5).
- P0-2: Path A / Path B dispatch split → Path B (district-dispatch failures) has zero connection to any learning store (FACT 3).
- P0-3: No one-shot/recurring distinction in `update_goal_progress()` → recurring goals like `g_daily_commit` permanently zero out `goal_alignment` for any action tagged to them (contributes to FACT 2's specific read_code case).

**P1** (significant, narrower or downstream):
- P1-1: `/command`'s classify_chat_intent action branch bypasses Candidate/DecisionEngine/PermissionGateway/PolicyMemory/CausalGraph via a parallel `GovernorCouncil().dispatch()` call (FACT 1).
- P1-2: `goals_v1` contains a state (`g_daily_commit` progress=1.0/status=active) that `update_goal_progress()`'s own unconditional rule cannot produce — evidence of an undocumented alternate write path to goal state.

**P2** (real, consequence-level):
- P2-1: `RetryQueue` only triggers on unhandled exceptions, not the soft `status≠"ok"` failures actually observed in RG-D.
- P2-2: `CounterfactualMemory` is architecturally pre-execution-only, cannot represent "selected-then-failed" — not necessarily a defect requiring a fix if EpistemicTracker is used instead for that role.

**P3** (symptom-level, not root causes — explicitly not to be remediated as if they were):
- P3-1: R6 mechanical diversity is working correctly as designed; it is not "masking" a problem so much as being the *only* mechanism currently doing any diversity work — a consequence of P0-1/P0-2, not a defect itself.
- P3-2: The historical 29,164-sample low-reward `analyze_progress` accumulation is a frozen consequence of P0-1/P0-3 that predates this benchmark; no separate remediation needed beyond fixing the root causes going forward.

## 8. Minimal Repair Wave

**RR-1 — Owner command → cognition/action integration**
- **Root cause**: P1-1.
- **Files**: `core/api/routers/commands.py` only.
- **Reuse**: the existing Candidate-construction + `decision_engine.evaluate()` + `perm_gateway.execute()` block already at L258-330 in the same file.
- **Minimal change**: reroute the classify_chat_intent action branch (L154-220) to build a `Candidate` from the classified action_type/district and feed it through the existing L258-330 block instead of calling `GovernorCouncil().dispatch()` directly.
- **Tests**: integration test asserting `candidates_evaluated≥1` and a PolicyMemory/CausalGraph write for a classify_chat_intent-routed owner command.
- **Production-path validation**: re-deliver an RG-C-shaped C1 mission and confirm non-zero `candidates_evaluated` when the classifier succeeds.
- **Regression risk**: MEDIUM — must not break the timeout→respond fallback, and must preserve the TaintTracker/council-review checks currently only present in the bypassed path (Audit A's explicit safety note).
- **Safety risk**: MEDIUM if done carelessly — could accidentally create a PermissionGateway bypass in the other direction if the existing taint/council checks are dropped rather than preserved or subsumed.
- **Rollback boundary**: one file, one function.

**RR-2 — Reward → measurable goal/task utility coupling**
- **Root cause**: P0-1, P0-3, P1-2.
- **Files**: `core/brain/goal_system.py` (add a `recurring`/`goal_type` distinction so `update_goal_progress()` stops unconditionally completing habitual goals — the exact gap Task 89C left open); `core/loop/autonomous_loop.py` (reintroduce a goal-progress write in `_act_on()`, this time gated by the new recurring flag, not blind reward-scaling).
- **Reuse**: `update_goal_progress()` itself; the existing "habit" tag already present on `g_daily_commit` (currently unread by any code) as a starting signal for the recurring flag.
- **Minimal change**: do NOT resurrect the old `0.10×reward` blanket auto-increment (that was the actual 89C bug). Instead, gate any reintroduced auto-completion on `not goal.get("recurring", False)`, and prefer having goal-progress-relevant action handlers (e.g. `analyze_progress`) report a real delta explicitly, rather than inferring one from a blended reward.
- **Tests**: re-run all 7 existing `tests/test_task89c_goal_progress.py` tests (must still pass unchanged); new tests for recurring-goal non-completion and one-shot-goal correct completion.
- **Regression risk**: MEDIUM-HIGH — touches the exact code Task 89C fixed; must not reintroduce that bug.
- **Rollback boundary**: `goal_system.py` + the `_act_on()` goal-feedback block.

**RR-3 — Failure → epistemic/counterfactual adaptation**
- **Root cause**: P0-2, P2-1.
- **Files**: `core/city/governor.py` — the `dispatch()` failure branch where `deduct_points` already fires (L2413-2431).
- **Reuse**: `EpistemicTracker.record_epistemic_belief`/`update_belief` (already exists, called from `_act_on()` — same pattern, new call site); optionally `RetryQueue` for soft-failure routing.
- **Minimal change**: add one call recording an `action_domain:{task_type}` epistemic belief on Path-B dispatch failure, using the same keying convention Path A already uses.
- **Tests**: unit test that a simulated Path-B dispatch failure produces an EpistemicTracker claim; test that repeated identical failures degrade confidence.
- **Regression risk**: LOW — additive only, no control-flow change.
- **Rollback boundary**: one failure branch in `governor.py`.

**RR-4 — Integrated purpose-driven validation**
- **Root cause**: none (validation stage).
- **Files**: new test files only (`tests/test_rr1_command_integration.py`, `tests/test_rr2_goal_progress_recurring.py`, `tests/test_rr3_failure_epistemic.py`); a scripted real-production-path validation pass reusing the RG-B/RG-C/RG-D observation methodology already proven in this session.
- **Regression risk**: none.

None of the four stages require a new subsystem — RR-3 is the clearest case of "reconnect existing code," RR-1 is "reuse the block 90 lines below," RR-2 is the most involved but still extends existing `GoalSystem`/`autonomous_loop.py` machinery rather than replacing it.

## 9. Files Proposed for Modification

| File | Why |
|---|---|
| `core/api/routers/commands.py` | RR-1: unify classify_chat_intent's action branch with the existing Candidate/DecisionEngine/PermissionGateway path |
| `core/brain/goal_system.py` | RR-2: add one-shot/recurring distinction to `update_goal_progress()`, closing the acknowledged Task-89C gap |
| `core/loop/autonomous_loop.py` | RR-2: reintroduce a correctly-gated goal-progress write in `_act_on()` |
| `core/city/governor.py` | RR-3: add an EpistemicTracker write on Path-B (district-dispatch) failure |

## 10. Tests Proposed

- **Unit**: recurring-goal non-completion / one-shot-goal correct completion (`goal_system.py`); Candidate construction from `classify_chat_intent` output (`commands.py`); epistemic write on Path-B failure (`governor.py`).
- **Integration**: full `/command`→DecisionEngine→PermissionGateway→PolicyMemory round-trip; full `governor.dispatch()` failure→EpistemicTracker round-trip.
- **Real production-path**: re-deliver an RG-C-shaped C1 mission (confirm `candidates_evaluated≥1`); re-run an RG-D-shaped observation window (confirm a repeated Path-B failure now shows an epistemic claim).
- **Restart/persistence**: confirm RR-2's recurring flag and RR-3's new epistemic claims survive a full process restart, reusing RG-B's exact watermark methodology.
- **Safety**: full re-run of the existing PermissionGateway test suite; a manual RED-tier `/command` test confirming no weakened gating after RR-1; full re-run of the existing 7 Task-89C tests after RR-2.

## 11. What NOT To Change

- PermissionGateway's tier classification logic itself.
- The TaintTracker/council-review checks currently present in the classify_chat_intent path — must be preserved or subsumed, never simply deleted.
- Do not reintroduce blind reward-scaled goal-progress mutation (the exact original Task-89C bug).
- No new Experience table, cognitive bus, reward database, or LLM judge — reuse PolicyMemory/CausalGraph/EpistemicTracker/GoalSystem as-is.
- `CounterfactualMemory`'s pre-execution veto semantics — leave architecture as-is; RR-3 uses EpistemicTracker for the post-execution-failure role instead.
- R6 staleness logic — working as designed, not a defect.
- The known plan-step permission-tier safety asymmetry — separately tracked per the mission's own instruction; not naturally touched by this repair wave.
- Already-persisted goal data (`g_daily_commit`'s frozen historical state) — no retroactive migration/rewrite, matching Task 89C's own precedent.

## 12. Expected Post-Repair Capability

Narrowly: owner commands whose intent classifier succeeds in recognizing an action will route through the same Candidate/DecisionEngine/PermissionGateway/PolicyMemory pipeline as autonomous actions, instead of a parallel bypass. Recurring/habitual goals will no longer structurally block positive `goal_alignment` for any action tagged to them, while one-shot goals retain correct completion semantics. District-dispatched (Path B) repeated failures will leave a visible EpistemicTracker trace, enabling — not guaranteeing — future confidence-based deprioritization. This does **not** constitute general self-correction, does not close the loop for every action type, and is explicitly not a claim of AGI/JARVIS-level autonomy — it is a targeted repair of three specific, evidenced architectural gaps.

## 13. Remaining Known Gaps (explicitly out of scope)

- The known plan-step permission-tier safety asymmetry (separately tracked).
- `CounterfactualMemory`'s inability to represent "selected action that then failed" (P2-2).
- No novelty/artifact-comparison mechanism — repeated `read_code` calls remain indistinguishable by content.
- No general critic/self-evaluation subsystem — `meta_cognition.py` does not cover "repeated zero-goal-progress action" as a bias signal.
- `RetryQueue` still won't catch soft (non-exception) failures unless RR-3 is explicitly extended to route them there — scoped out of RR-3's minimal version above; flagged as an optional follow-on.
- `doom_loop.py`'s repeat-detection remains isolated to the `vector_mlops` coding-agent tool loop, not generalized to `DecisionEngine`.

## 14. Verdict

# READY FOR RR-1 IMPLEMENTATION

All root causes trace to specific, small, well-evidenced code locations; no architectural blocker was found; existing components (`PolicyMemory`, `CausalGraph`, `EpistemicTracker`, `GoalSystem`, the `Candidate`/`DecisionEngine`/`PermissionGateway` pipeline, `RetryQueue`) are sufficient to implement all four repair stages without new subsystems.

**Hard Stop.** No implementation performed. No files modified. No commits made.
