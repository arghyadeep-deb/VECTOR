# 54 — Pre-Experiment Readiness Verification

**Date**: 2026-09-02
**Type**: VERIFICATION ONLY. No production code was modified by this task. No behavior was
changed, fixed, refactored, or redesigned. Where a diagnostic script or test was written, it
performs no production-behavior change and is clearly marked below.
**Question this document answers, and only this question**: *Is VECTOR sufficiently verified to
begin the 7-day autonomous experiment?*

---

## 1. Executive Summary

No new BLOCKER was discovered this task. All blockers confirmed in prior tasks (`51`'s two
MUST-FIX items, `53`'s two confirmed permission bypasses) were re-confirmed fixed, and their fixes
were re-run and still pass. However, this verification pass — going beyond what any prior task's
narrower scope required — surfaced several **real, currently-open WARNINGS** that were previously
either unverified assumptions or not investigated at all:

- **RULE 1 (session hydration)** is genuinely, broadly integrated across ~65 real district-agent
  call sites, but is confirmed **not** called by `autonomous_loop.py`'s own two direct LLM call
  sites (`hypothesis_loop()` via `HypothesisEngine._call()`, and `_coding_companion_nudge()`) —
  a real violation of a project rule (`.claude/rules/memory.md`: *"Without hydration, VECTOR has
  amnesia. Rule 1."*), assessed as low safety impact (both are passive/advisory, no side effects)
  but not fixed, per this task's explicit instruction not to fix anything.
- **Owner-correction learning's outcome-feedback loop is confirmed still never wired** —
  `CorrectionLearner.validate_lesson()` has zero production callers (re-confirmed this task, same
  finding as `51`, unchanged). Lessons are detected, stored, and injected into prompts, but their
  confidence is never adjusted by whether applying them actually helped.
- **A previously-undiscovered pre-existing test failure was root-caused this task** (not merely
  bucketed as "unrelated" the way it was implicitly excluded from prior tasks' narrower scopes):
  `test_epistemic_scoring.py::test_stale_domain_reduces_score` fails because the test's own mock
  doesn't match the real `domain = action_type.split("_")[0]` extraction — a test bug, not a
  production bug, but it surfaces a genuine design characteristic worth flagging: epistemic
  dampening operates at first-underscore-token granularity ("action_domain:git", not
  "action_domain:git_status"), which is coarser than it might appear from the code alone.
- **Two more previously-undiscovered pre-existing test failures** surfaced from a broader sweep
  (`test_regression_governor_capability_routing.py`, 2 tests) — root-caused to a regex/embedding
  pre-classify layer added after that test file was written, unrelated to any of this session's
  changes.
- **Residual limitations documented in `53` remain genuinely unverified**, and this task closed
  one of them (plan execution → executor → gateway, now confirmed by direct code trace) but did
  **not** close the others (event fan-out's per-district handler coverage beyond the security
  district; `pc_controller.py`/`phone_controller.py`'s token-minting call sites; the ~70-80
  `subprocess`/`os.system` files never individually read).

Given the explicit instruction *"If there is ANY uncertainty about whether a consequential
autonomous path is safely gated, recoverable, observable, or behaviorally verified, do NOT
classify VECTOR as A — READY"* — and given real, confirmed uncertainty remains in the areas above
— this document does not classify VECTOR as A. See §17 for the exact gate and next steps.

---

## 2. Historical Blocker Status

| Item | Source | Original status | Re-verified this task | S-level | Class |
|---|---|---|---|---|---|
| `hypothesis_loop()` missing `await` | 51 §16.A | MUST-FIX blocker | Fixed in 52, re-run this task (203/203 targeted tests pass) | S5 | Resolved |
| Plan-step crash recovery | 51 §16.B | MUST-FIX blocker | Fixed in 52, re-run this task (part of the 203) | S5 | Resolved |
| Hypothesis key mismatch (`"hypothesis"` vs `"text"`) | 55 | Confirmed defect | Fixed in 55, re-run this task | S5 | Resolved |
| Hypothesis confidence hardcoded 0.7 | 55 | Confirmed defect | Fixed in 55, re-run this task | S5 | Resolved |
| Hypothesis observation dict/str mismatch | 56 | Confirmed defect (classification B) | Fixed in 56, re-run this task, live-verified in 56 | S5 | Resolved |
| Governor.dispatch() → PermissionGateway | 51 §9 / 53 | Assumed-bypass; reclassified in 53 as routing-layer-by-design | Re-confirmed this task via fresh read of `dispatch()` | S5 | Not a bug (A/D) |
| EmailAgent reply/forward real-send bypass | 53 Finding 1 | Confirmed live RED-tier bypass | Fixed in 53, re-run this task (16/16) | S5 | Resolved |
| `_act_on()` YELLOW-skip in VC/skill gates | 53 Finding 2 | Confirmed live contract gap | Fixed in 53, re-run this task (part of the 16) | S5 | Resolved |
| `pc_controller.py`/`phone_controller.py` device control | 53 §15 | Documented unverified | Mechanism confirmed fail-closed by design (this task); call-site coverage still not exhaustively traced | S3 | **WARNING — open** |
| Event fan-out per-district handler coverage | 53 §15 | Documented unverified beyond security district | Not extended this task | S2 | **WARNING — open** |
| ~90 subprocess/os.system files | 53 §15 | Documented unverified (highest-risk subset checked) | Not extended this task | S2 | **WARNING — open** |
| Plan execution → executor → gateway wiring | 53 §4 (carried as assumption) | Assumed, not re-verified | **Confirmed this task** via direct read of `PlanRunner.execute_step()` → `AutonomousExecutor.execute()` → `PermissionGateway.execute()` | S4 | Resolved (upgraded from assumption) |
| `belief:*` epistemic formation loop | 51 §7 | S3 — writes real data, nothing consults it for scoring | Not re-verified this task (out of the narrow scope any prior task touched) | S3 | ACCEPTABLE RESIDUAL (unchanged, documented) |
| `action_domain:*` epistemic outcome loop | 51 §7 | S5 — closed, test-proven | **Re-confirmed this task**: same `f"action_domain:{domain}"` key used by both the read side (`_epistemic_penalty`) and write side (`record_epistemic_belief`); `_epistemic_penalty()` confirmed called from `_score_candidate()` | S5 | Resolved (re-confirmed) |
| Owner-correction outcome-feedback loop | 51 §8 | S2 — never called in production | **Re-confirmed this task**: `validate_lesson()` still has zero callers anywhere in production code | S2 | **WARNING — open, unchanged** |
| Retry-rate metric coverage (50 §6b) | 50 | PARTIAL — real but not codebase-wide | Not re-verified this task (observability-completeness, not a safety question) | S3 | ACCEPTABLE RESIDUAL |
| Vendored/dormant LLM clients uninstrumented (50 §6a) | 50 | Documented, dormant | Not re-verified this task | N/A | NOT APPLICABLE (dormant) |
| RULE 1 not called by `hypothesis_loop()`/`_coding_companion_nudge()` | 56 §9 (flagged, unresolved) | Flagged, not investigated | **Investigated this task — see §5** | S3 | **WARNING — open** |
| Hypothesis confidence marker compliance | 55/56 | Documented — LLM doesn't always emit the marker | Unchanged; falls back safely to 0.5 (below the 0.85 gate) | S5 (fallback path) | ACCEPTABLE RESIDUAL |

---

## 3. Readiness Criteria (Phase 1, 27 categories)

Legend: I=Implemented, N=Integrated, R=Runtime reachable, T=Test verified, B=Behaviorally verified
(this task or a prior task, both cited).

| # | Category | I | N | R | T | B | Evidence | Remaining gap |
|---|---|---|---|---|---|---|---|---|
| 1 | Autonomous loop | Y | Y | Y | Y | Y | `run_forever()` gathers 21 `_supervised()`-wrapped coroutines (read directly, §7); `test_absorbed_autonomy.py::test_scheduler_fires_hands` — real scheduler fires a Hand with zero test-body trigger | None found |
| 2 | Cognitive cycle | Y | Y | Y | Y | Y | `_think_tick()` → `generate_immediate_actions()` → `_score_candidate()` → `_act_on()`, traced end to end this task (§6, §9) | Belief-formation sub-loop not scored (see #11) |
| 3 | Context/world-state acquisition | Y | Y | Y | Y | Y | `ContextEngine.get_world_state()` — 16-key dict, read directly; used by `_think_tick`, `hypothesis_loop`, `decision_engine`, `planner` | None found |
| 4 | Memory retrieval | Y | Y | Y | Y | Y | `EpisodicMemory.recall()`/`search_semantic()` feed `get_world_state()`'s `recent_episodes` | None found |
| 5 | Memory writing/learning | Y | Y | Y | Y | Y | `EpisodicMemory.store()` called from `_act_on()`, `hypothesis_loop()`, `governor.dispatch()` — confirmed via direct reads across 4 prior tasks | None found |
| 6 | Goals/objectives | Y | Y | Y | Y | P | `GoalSystem` — real, seeded, `generate_immediate_actions()` feeds candidates; goal-progress updates confirmed in `_act_on()`. Not independently re-run this task | None found |
| 7 | Reasoning | Y | Y | Y | Y | P | `ReasoningBank.inject_past_reasoning()` (RULE 8) — confirmed called in `decision_engine.py`; not independently re-run this task | None found |
| 8 | Hypothesis generation | Y | Y | Y | Y | Y | `HypothesisEngine.generate_hypotheses()` — live-verified in 56 (real network call reached, real fallback engaged) | Marker compliance not guaranteed (accepted, §2) |
| 9 | Hypothesis persistence/suppression | Y | Y | Y | Y | Y | `SuggestionQueue` + `EpisodicMemory.store()` on qualify; 0.85 gate confirmed unchanged, tested (55/56, re-run this task) | None found |
| 10 | Decision engine | Y | Y | Y | Y | P | 5-factor formula + epistemic/policy/counterfactual injection, confirmed via direct read this task (§7 below); not independently re-executed this task beyond what 203 targeted tests cover | None found |
| 11 | Epistemic state/confidence | Y | Y | Y | T(partial) | P | `action_domain:*` loop: S5, re-confirmed this task (keyspace match + call-site trace). `belief:*` loop: S3, unchanged, not re-verified this task | `belief:*` formation loop still doesn't reach scoring (unchanged since 51) |
| 12 | Policy/governance | Y | Y | Y | Y | Y | `PolicyMemory.get_score()`/`update_from_outcome()` — SQLite-backed (`policy_memory` table), confirmed via `core/memory/policy.py` read this task | None found |
| 13 | Permission boundary | Y | Y | Y | Y | Y | 53's two findings fixed and re-run this task (16/16); `execute()`'s classify→approve→execute flow confirmed the sole path to `_execute_action()` | Device-control/event-fan-out/subprocess coverage not exhaustive (§2) |
| 14 | Planning | Y | Y | Y | Y | P | `plans.py`'s DAG/replan machinery — extensively tested in 52 (19/19, re-run this task); not independently re-executed beyond that suite this task | None found |
| 15 | Plan execution | Y | Y | Y | Y | P | `_act_on_plan_step()` → `PlanRunner.execute_step()` → `AutonomousExecutor.execute()` → `PermissionGateway.execute()` — traced end to end **this task** (§9); behaviorally covered by 52's crash-recovery tests, not independently re-executed as a fresh end-to-end run this task | None found |
| 16 | Tool execution | Y | Y | Y | Y | P | Skill-matching gate (53 Finding 2, fixed, re-run this task); VectorCode bridge gate confirmed via direct read | None found |
| 17 | External side effects | Y | Y | Y | Y | Y | Email (53, fixed+tested), git push, Solana swap, social upload — each individually traced in 53, re-confirmed via git-status-unchanged this task | Device control / subprocess sweep incomplete (§2) |
| 18 | Recovery/restart behavior | Y | Y | Y | Y | Y | Plan crash recovery — 11 behavioral tests, re-run this task; `_supervised()` coroutine restart — confirmed via direct read this task (§7) | None found for what was checked |
| 19 | Fallback behavior | Y | Y | Y | Y | Y | Provider fallback chain — confirmed live during 56's real network call (groq→deepseek→mistral); 50's 184/184 regression suite | None found |
| 20 | Inference routing/observability | Y | Y | Y | Y | Y | 50 — 20/22 requirements COMPLETE, 1 PARTIAL (documented, not a safety gap), re-run this task (16/16 `test_inference_observability_gaps.py`) | Retry-rate metric doesn't cover 100% of call paths (accepted, observability-only) |
| 21 | Persistence | Y | Y | Y | Y | P | Surveyed this task (§12) — 5 canonical SQLite tables + `PlanStore` JSON + 3 dedicated SQLite DBs (epistemic, suggestion_queue, telemetry) | None found for what was surveyed |
| 22 | Proactivity/background execution | Y | Y | Y | Y | Y | `anticipation_loop` (S5 per 51, unchanged) + `hypothesis_loop` (S5, fixed in 52/55/56) + Hands scheduler proof (`test_absorbed_autonomy.py`) | RULE 1 gap on 2 call sites (§2, §5) |
| 23 | No-user-input operation | Y | Y | Y | Y | Y | `test_scheduler_fires_hands` — a real `AsyncIOScheduler` fires a Hand with zero test-body-initiated call; hypothesis-pipeline tests drive `hypothesis_loop()` with only `asyncio.sleep` fast-forwarded, no user message | None found |
| 24 | Error containment | Y | Y | Y | Y | P | `_supervised()` wrapper confirmed this task (§7) — structural, applies to all 21 coroutines; individual failure-mode tests exist for hypothesis generation (55/56), gateway denial (53), plan crash (52) — not every one of Phase 11's 11 failure types was freshly injected this task | See §13 |
| 25 | Safety boundaries | Y | Y | Y | Y | Y | Same as #13 | Same as #13 |
| 26 | Auditability/observability | Y | Y | Y | Y | Y | Merkle audit chain (`_write_audit()` in `permission_gateway.py`, called on every `execute()` branch); inference_calls table (50) | None found |
| 27 | Experiment instrumentation | Y | Y | Y | Y | P | `scripts/inference_report.py` verified end-to-end in 50 against seeded data | Not re-run against live data this task (no live 7-day data exists yet — expected) |

---

## 4. End-to-End Autonomous Cycle (Phase 2)

Traced via direct code read (not assumed from any prior document), this task:

```
run_forever()
  → 21 coroutines, each wrapped by _supervised() (exponential-backoff restart on exception)
  → think_loop() → _think_tick() [confirmed exists, called on a real interval — not user-triggered]
      → self._get_goals().generate_immediate_actions()          [goal candidates]
      → decision_engine._score_candidate() for each candidate    [5-factor + epistemic + policy]
          → self._epistemic_penalty(candidate)                   [reads action_domain:* belief]
          → ReasoningBank.inject_past_reasoning()                 [RULE 8]
      → winner = highest-scoring candidate
      → _act_on(winner)
          → proactive_* → gw.execute() directly, returns (no district routing)
          → plan: source → _act_on_plan_step() → PlanRunner.execute_step()
              → AutonomousExecutor.execute() → PermissionGateway.execute()   [traced this task]
          → _VC_ACTION_TYPES → gw.classify()/gw.execute() [FORBIDDEN/RED/YELLOW gated — 53 fix]
          → skill match (confidence > 0.6) → gw.classify()/gw.execute() [FORBIDDEN/RED/YELLOW gated — 53 fix]
          → fallthrough → governor.dispatch() → agent.run(task)   [district-specific; agent
                                                                      self-gates real side effects,
                                                                      per 53's per-agent findings]
      → policy.update_from_outcome() + decision.record_epistemic_belief() + goal progress + CausalGraph edge
  → hypothesis_loop() → engine.generate_hypotheses(str(get_world_state())[:500])   [55/56 fixes]
      → confidence >= 0.85 → EpisodicMemory.store()
  → (18 other supervised coroutines: observe, reflect, sync, scheduler, ambient_scheduler, ...)
```

**Verified this task**: the cycle does not require a user message anywhere in this chain —
`think_loop`/`hypothesis_loop`/`reflect_loop`/`scheduler_loop`/etc. are all time-interval-driven
coroutines under `run_forever()`, none gated on chat input. **Verified this task**: an exception at
any single stage (e.g., a district agent's `run()` raising) is caught by `_act_on()`'s own
try/except around that specific sub-step (confirmed by direct read — every major block in
`_act_on()` has its own `try/except`, degrading gracefully rather than propagating), and even an
exception that escapes `_act_on()` entirely would only kill the `think` coroutine specifically —
`_supervised()` restarts it with backoff, the other 20 coroutines are unaffected (`asyncio.gather(
..., return_exceptions=True)` plus each coroutine's own internal catch).

**Not independently re-executed this task as one live, continuous run**: a full multi-tick,
real-time execution of this entire chain end-to-end in a single observed session. The chain was
verified by reading the real call sites (not documentation) and by re-running the behavioral tests
that exercise its individual segments (hypothesis generation end-to-end in 56; plan-step
execution in 52; the Hand-scheduler proof unconditionally). This is S4 (test-verified per-segment)
rather than S5 (one continuous live proof of the whole chain) for the chain *as a whole* — each
segment is S5 individually.

---

## 5. RULE 1 / Session Hydration (Phase 3)

**What RULE 1 is**: `.claude/rules/memory.md` states it explicitly: *"Every LLM call must be
preceded by [`session_hydration_prompt()`]... Without hydration, VECTOR has amnesia. Rule 1."*
`CLAUDE.md`'s "Key Rules" restates it as rule #1: *"`context_engine.session_hydration_prompt()`
before EVERY LLM call — no exceptions."*

**Where implemented**: `ContextEngine.session_hydration_prompt(extra_context=None) -> str`
(`core/loop/context_engine.py:293`) — builds a text block from `get_world_state()` plus: the
owner's Blueprint doctrine line, a knowledge-graph line (if a `query` is given), person context
(if `person_id` given), and correction lessons (if `domain` given).

**Which autonomous paths call it**: re-grepped this task — **~65 real production call sites**
across the district-agent layer (`districts/health/*`, `districts/languages/*`,
`districts/learning/*`, `districts/marketing/*`, `districts/memory_curator/*`,
`districts/news_trends/*`, `districts/pattern_detective/*`, `districts/personal_growth/*`,
`districts/privacy/*`, `districts/projects/*`, `districts/qa/*`, `districts/reflection/*`,
`districts/relationships/*`, `districts/research/*`, `districts/skills/*`, `districts/startups/*`,
`districts/time_calendar/*`, `districts/chief_of_staff/*`, `districts/governance/llm_council.py`,
`hands/runner.py`, all the API routers, `core/voice/ambient_listener.py`). Spot-checked two
non-obvious ones directly (`hindi_coach.py`, `sleep_tracker.py`) and confirmed genuine usage
(hydration result threaded into the actual LLM message, not just imported). **Five files in the
grep are false positives** — `districts/coding/{code_reviewer,architect_bot,fastapi_reviewer,
python_reviewer,security_reviewer}.py` reference the *string* `"session_hydration_prompt"` only as
part of their own review-heuristic checklist (checking *other* code for RULE 1 compliance), not as
a call they themselves make.

**Does `hypothesis_loop()` call it?** No — confirmed by direct read of both
`AutonomousLoop.hypothesis_loop()` and `HypothesisEngine._call()`; the latter builds its message
list directly (`[{"role": "system", "content": self._SYSTEM}, {"role": "user", "content":
user_prompt}]`) with no hydration call anywhere in the chain.

**Does the normal autonomous cognitive cycle call it?** For the part that actually makes LLM calls
— district agents executing via `agent.run(task)` — yes, genuinely, for the ~65 confirmed sites.
`autonomous_loop.py` itself makes exactly one other direct LLM call
(`_coding_companion_nudge()`, a screen-stuck-error advisory nudge) and it also does not hydrate.

**Is session hydration actually required for autonomous correctness?** No — the autonomous loop's
control flow (which coroutine runs, which candidate wins, whether an action executes) does not
depend on hydration content. Hydration affects the *quality/relevance* of what an LLM-driven agent
*produces*, not whether the loop runs or what path a decision takes.

**Blocker or limitation?** **WARNING, not BLOCKER.** Reasoning: (1) both non-compliant call sites
produce purely advisory/passive output — a stored hypothesis (never auto-acted-on, per 55/56) and
a spoken/HUD nudge — neither has any side-effect capability; (2) for `hypothesis_loop()`
specifically, the `observation` it *does* use (`str(get_world_state())[:500]`) already contains
`goal_summary`, `recent_episodes`, `presence`, `screen_summary` — most of what
`session_hydration_prompt()` would add; the material gap is narrower than "zero context" — it's
specifically the owner's doctrine line, knowledge-graph line, and correction lessons. This is a
real, confirmed rule violation that should be tracked and eventually fixed, but it does not meet
the bar of "could cause unauthorized consequential side effects, destructive behavior, or silent
failure of core autonomy" that this document's BLOCKER definition requires.

**No equivalent hydration path was found** that makes this gap fully harmless — `get_world_state()`
is a genuine but partial substitute for `hypothesis_loop()`, and `_coding_companion_nudge()` has no
substitute at all beyond the screen-OCR text embedded directly in its own prompt.

---

## 6. Hypothesis Pipeline Verification (Phase 4)

Re-run this task, not re-derived from scratch: `tests/integration/test_phase_a5_hypothesis_consumer.py`
— **30/30 pass**, including the `TestHypothesisPipelineTextAndConfidenceContract` (55),
`TestHypothesisObservationContract` (56), and `TestHypothesisLoopActuallyExecutes` (52) classes.

Per-item status, all previously behaviorally verified in 55/56 and re-confirmed passing this task:
- **Real generation occurs**: `test_real_world_state_reaches_real_engine_as_string_and_is_stored` —
  real `ContextEngine`, real `HypothesisEngine`, only the network leg mocked.
- **Observation contract is correct**: `str(context)[:500]` conversion, fixed in 56, re-tested.
- **Text propagates correctly**: `h.get("text", ...)`, fixed in 55, re-tested.
- **Confidence is meaningful**: parsed from a real `"CONFIDENCE: <n>"` marker, fixed in 55,
  re-tested; **known limitation unchanged**: the marker is a prompt request, not an enforced
  schema — a live LLM call during 56 omitted it and correctly fell back to 0.5.
- **Qualifying hypotheses persist / non-qualifying suppressed**: 0.85 gate unchanged, both paths
  tested.
- **Malformed LLM output handled safely**: `_extract_confidence()`'s no-match branch, tested.
- **Errors don't kill the loop**: two independent tests — the engine's own internal catch
  (`{"error": ...}` return) and `hypothesis_loop()`'s own except block.
- **Cadence remains correct**: `sleep_calls[0] == 4 * 3600` asserted in multiple tests, still true.
- **No-user-input execution works**: every test in this class drives `hypothesis_loop()` directly
  with no user-facing trigger; the 4h `asyncio.sleep` is fast-forwarded, not skipped-around.

**Not re-verified this task**: a fresh live network call (56 already did one; not repeated here to
avoid unnecessary real API usage for a verification-only pass).

---

## 7. Permission / Safety Boundary Verification (Phase 5)

Re-run this task: `tests/unit/test_permission_gateway.py` + `tests/unit/test_permission_gateway_extra.py`
+ `tests/test_email_agent_permission_gate.py` + `tests/loop/test_skill_gateway.py` — **203/203 pass**
combined with the hypothesis/planning suites (§6, §9).

- **GREEN executes without unnecessary friction**: confirmed by `test_read_only_list_task_
  unaffected_by_gate` (53) and `test_green_skill_action_does_not_require_gateway_execute` (53) —
  both assert the gateway's `execute()` is never even called for GREEN, not just that it approves.
- **YELLOW receives the existing confirmation/trust mechanism**: confirmed for the two paths 53
  fixed (skill-matching, VC-routing) — both now route through `gw.execute()`'s real YELLOW logic
  (trust ladder / owner-command fast path / real wait-for-confirmation).
- **RED receives required approval**: `push_github`, `solana_swap_execute`, `send_email` (post-53
  fix) all confirmed gated before their real side effect, re-traced this task via git-status
  (files unchanged since 53, confirming the fix is still in place) plus the 9 email-gate tests.
- **FORBIDDEN cannot execute**: `test_forbidden_skill_action_still_blocked` (53) — confirmed
  neither `gw.execute()` nor `sm.execute()` is reached.
- **Both user-triggered and autonomous execution obey the boundary**: `proposed_by` differentiates
  them inside `PermissionGateway.execute()` (owner-trust markers `"api_command"`/`"voice"` vs.
  anything else) — this mechanism itself was not modified by any task this session; re-confirmed
  present via `core/loop/permission_gateway.py:480` read this task.

**Residual areas from 53, status this task**:
- `pc_controller.py`/`phone_controller.py`: the *mechanism* (`_verify_control_token()`) is
  confirmed **fail-closed** by direct read this task (`except: return False` on gateway
  unavailability; requires a token minted by `PermissionGateway.grant_control()`). **Not
  confirmed**: that every production caller of `grant_control("run_shell_command", ...)` is
  preceded by a real `execute()` RED-tier approval rather than minting a token directly (the
  module's own `__main__` self-test mints directly, which is fine for a self-test but doesn't
  answer the production-caller question). **Status: WARNING, open.**
- Event fan-out → every relevant district handler: only the security district's two agents
  (`node_guard.py`, `threat_scout.py`) were checked directly, in 53 and again referenced this
  task — both ignore `task_type` and perform a fixed, safe operation regardless. **Not extended**
  to the other ~10 districts `EVENT_TRIGGER_MAP` can route to (coding, content, qa, documentation,
  intelligence, investment, governance, health, predictive_analytics, marketing, data_analytics,
  security). **Status: WARNING, open.**
- ~70-80 of the ~90 `subprocess`/`os.system`-using files: not individually read (53's own
  admission, unchanged). The highest-plausible-risk subset (git, email, Solana, social upload,
  Hands, node/security monitoring, marketing ads) was checked and found safe. **Status: WARNING,
  open, for the unchecked remainder** — predominantly video/audio encoding and Claude-Code-facing
  dev tooling by file-path inspection, but not individually confirmed.

No dangerous real action was performed to verify any of this — all checks were direct code reads,
existing/new mocked tests, or the pre-existing fail-closed-by-design confirmation.

---

## 8. Planning / Recovery Verification (Phase 6)

Re-run this task: `tests/integration/test_planning_integration.py::TestCrashRecovery` — **19/19
pass** (11 crash-recovery tests + 8 pre-existing lifecycle tests in the same file).

1. **Process crash during a running step does not permanently strand the plan**: confirmed —
   `_recover_stale_running_steps()` runs on `PlanStore._ensure_loaded()`'s first load, tested via
   simulated-crash-state-on-disk + fresh-store-load (the documented equivalence to a real restart).
2. **GREEN stale-running steps recover/re-execute**: `test_green_step_detected_and_reset_to_planned`
   + `test_recovered_green_step_executes_and_unblocks_dependents`.
3. **Non-GREEN stale-running steps do NOT blindly replay**: `test_yellow_tier_step_not_auto_resumed`,
   `test_red_tier_step_not_auto_resumed`.
4. **Fallback/review_required behavior preserved**: `test_non_green_step_with_fallback_routes_
   around_crash_safely`.
5. **Recovery is idempotent**: `test_recovery_is_idempotent_across_repeated_loads` (3 simulated
   fresh loads).
6. **Persistence survives restart**: `test_recovery_decision_persisted_to_disk_not_just_memory`.
7. **Autonomous plan execution reaches the intended executor**: **confirmed this task** by direct
   read (not previously traced end-to-end) — `AutonomousLoop._act_on_plan_step()` →
   `PlanRunner.execute_step()` (`core/runtime/plans.py:859`) → `self._get_executor()` →
   `AutonomousExecutor()` (`core/runtime/executor.py:51`).
8. **The executor still respects the permission boundary**: **confirmed this task** —
   `AutonomousExecutor.execute()` calls `await self.permission_gateway.execute(action)`
   (`core/runtime/executor.py:132`), the same `PermissionGateway.execute()` verified throughout
   §7. This closes the "not re-verified" caveat `53` carried forward as an assumption.

---

## 9. Epistemic / Learning Loop Verification (Phase 7)

- **EpistemicTracker influences decisions**: **re-confirmed this task** via direct code read —
  `DecisionEngine._epistemic_penalty()` (line 271) is called from `_score_candidate()` (line 404,
  confirmed by grep), reads `claim_id = f"action_domain:{domain}"`; `record_epistemic_belief()`
  (called from `_act_on()` after every outcome) writes the identical key format. **Keyspaces are
  compatible** — confirmed, not assumed.
- **PolicyMemory influences decisions where intended**: `get_score()`/`update_from_outcome()` —
  SQLite-backed (`policy_memory`, one of the 5 canonical tables), confirmed via
  `core/memory/policy.py` read this task; call sites in `_act_on()` confirmed across all 4 prior
  tasks this session.
- **CounterfactualMemory influences decisions where intended**: confirmed via direct read of
  `_act_on()`'s counterfactual block (unchanged across all 4 prior tasks' reads this session) —
  blocks proposals above a similarity threshold to past rejections, applies a policy penalty so
  the same rejected action doesn't get proposed forever.
- **Action-domain epistemic confidence changes behavior where intended**: yes — see first bullet;
  this is `51`'s S5 finding, re-confirmed.
- **Owner-correction learning reaching the mechanism intended to learn from it**: **partially**.
  Detection (`CorrectionLearner.detect()`), storage (`_store_lesson()`), retrieval
  (`retrieve_applicable_lessons()`), and prompt injection (`build_injection_line()`, called from
  `session_hydration_prompt()`) are all real and wired. The outcome-feedback half
  (`validate_lesson(lesson_id, outcome_good)` — adjusts a lesson's confidence based on whether
  applying it actually helped) has **zero production callers**, re-confirmed this task via grep
  (unchanged from `51`). Correction lessons are injected into future prompts and can influence LLM
  output, but nothing ever tells the system whether that influence was good or bad, so lesson
  confidence never reflects real-world validation.
- **No critical learning mechanism is "implemented but never called"**: **one exception exists**
  and is unchanged from `51` — `validate_lesson()`. This is not "critical" in the sense of a safety
  BLOCKER (it degrades learning quality, not safety), but it is exactly the kind of
  "implemented-but-not-integrated" gap Phase 7 asks to be distinguished from working code, so it is
  called out explicitly rather than silently inherited from the prior document.
- **Keyspace compatibility**: confirmed for `action_domain:*` (above). Not independently
  re-verified for `belief:*` this task (unchanged S3 status from `51` — writes real data via
  `ContextEngine.track_beliefs()`, but no consumer was found reading it for scoring in `51`'s
  original 6-pass audit, and this task did not re-run that search).

---

## 10. Proactivity / No-User-Input Verification (Phase 8)

**Scheduler → cognition → decision → action → observation → learning, traced and behaviorally
confirmed this task** (by re-running the existing proof, not re-deriving it):
`tests/integration/test_absorbed_autonomy.py::test_scheduler_fires_hands` — a real
`apscheduler.schedulers.asyncio.AsyncIOScheduler` is started, a job is registered with a `date`
trigger ~1.5s in the future, and the test only calls `asyncio.sleep(3.0)` and waits — it never
calls `run_hand()` itself. Result, confirmed via a fresh run this task: the scheduler fires the
job, a real (unstubbed) episodic-memory row is persisted, a real HP delta is applied to a real
agent, and a real `policy_memory` row is written from `update_from_outcome()`. Only the
LLM/governor leaf itself is stubbed (for speed/Ollama-independence) — every other link in the
chain is the real, production code path.

This directly demonstrates: no new chat message, no manual invocation, no manual approval (the
Hand used, `vault_sync`, is GREEN-tier), no developer intervention, and — critically — the test
harness's only role is to *wait*, not to trigger. This is the strongest available evidence for
"VECTOR can perform meaningful autonomous cognition without user input" without literally running
the system unattended for an extended period (explicitly out of scope for this task).

Combined with `run_forever()`'s 21 always-on, `_supervised()`-wrapped coroutines (§4) and
`hypothesis_loop()`'s confirmed real-network-call reachability with zero user input (§6, citing
56's live verification), this category is assessed **S5 — behaviorally verified**, not merely
assumed from the coroutine list's existence.

---

## 11. Inference / Provider / Fallback Verification (Phase 9)

Re-run this task: `tests/unit/test_inference_observability_gaps.py` — **16/16 pass**.

- All production-relevant inference paths are observable: per `50` §2, three instrumentation
  points (`ProviderClient.chat()`, the legacy fallback chain, `ollama_safe.chat()`'s direct-bypass
  callers) cover the full call graph; unchanged this task (no file in the inference stack was
  touched by any of the 4 prior tasks this session — confirmed via `git status`, §14).
- Provider/model identity recorded: `inference_calls.provider`/`.model` columns, unchanged.
- Autonomous vs. user-triggered distinguishable: `is_autonomous_caller()`, unchanged.
- Token accounting available: `input_tokens`/`output_tokens`, real where the provider reports them,
  flagged `token_exact=False` where estimated — unchanged.
- Failures recorded: `status="error"` + `error_kind`, unchanged.
- Fallback events observable: `providers_tried > 1` → `fallback_calls`, unchanged; directly
  witnessed live during `56`'s hypothesis-generation test (groq 404 → deepseek 402 → mistral
  success, all logged).
- Provider failures do not silently terminate autonomous cognition: confirmed structurally via
  `_supervised()` (§4) plus `hypothesis_loop()`'s own except block (§6) plus `_act_on()`'s
  per-branch try/except pattern, consistently observed across every file this session touched.
- No unsafe routing bypass introduced by any of this session's fixes: `git diff` review across all
  4 prior tasks confirmed zero changes to `route_policy.decide_route()`, `TIER_ROUTING`,
  `model_pool`, or any provider-selection code — re-confirmed via `git status` this task (§14),
  none of the inference-stack files show as touched by this session's work.

---

## 12. Persistence / Restart Verification (Phase 10)

Surveyed this task (direct code reads, not assumed):

| State | Backend | Survives process/app restart? |
|---|---|---|
| Episodic memory | SQLite (`episodic_memory`, one of the 5 canonical tables, `core/memory/episodic.py`) | Yes |
| Semantic memory | SQLite (`semantic_memory`) | Yes |
| Policy memory | SQLite (`policy_memory`) — confirmed via `core/memory/policy.py` read this task | Yes |
| Reasoning chains | SQLite (`reasoning_chains`) | Yes |
| Agent history / HP | SQLite (`agent_history`) + `loop_state.py`'s `restore_agent_hp()` on `run_forever()` startup (confirmed via direct read this task, §4) | Yes |
| Goals | Loaded via `GoalSystem._load_or_seed()` from memory (confirmed via log line observed repeatedly this session: `"loaded N goals from memory"`) | Yes |
| Plans | `PlanStore` — JSON file (`plans.py`), with the crash-recovery fix from `52` for stale `"running"` steps on reload | Yes |
| Hypothesis state (SuggestionQueue) | SQLite (`data/suggestion_queue.db`) | Yes |
| Epistemic state | SQLite (`data/epistemic.db`, confirmed via log line observed this session: `"EpistemicTracker initialized (db=data\epistemic.db)"`) | Yes |
| Correction lessons | Stored via `EpisodicMemory.store(event_type="correction_lesson")` — SQLite | Yes |
| Inference observability | SQLite (`data/telemetry.db`, per `50`) | Yes |
| Audit log | `MerkleAuditChain` (`core/audit/merkle_chain.py`) — persisted hash chain, called from `permission_gateway._write_audit()` on every `execute()` branch | Yes (not independently re-verified this task beyond confirming the call site exists) |

**No state was identified that would unexpectedly reset during a 7-day run** among the categories
surveyed. This survey did not exhaustively check every one of VECTOR's 130+ agent files for
agent-local in-memory-only state that might not persist — that would be a much larger undertaking
than this task's remaining scope allows, and is noted as a survey-depth limitation rather than a
confirmed gap.

---

## 13. Error Containment Verification (Phase 11)

**Structural guarantee, confirmed this task by direct read**: `_supervised()`
(`core/loop/autonomous_loop.py:2509`) wraps all 21 `run_forever()` coroutines individually — an
exception escaping any one coroutine's own internal guards is caught, logged, and the coroutine is
restarted with exponential backoff (5s → capped at 300s); the other 20 coroutines are structurally
unaffected (each is an independent `_supervised()` call inside `asyncio.gather(...,
return_exceptions=True)`). This is a **C = "the entire autonomous loop dies"** outcome ruled out
by construction for coroutine-level failures — the correct classification is **D = retries/falls
back** at the coroutine level.

Below that level, every major sub-step inside the busiest coroutines (`_act_on()`, `hypothesis_
loop()`, `_fanout_handler()`, `reflect_loop()`) was observed, across all 4 prior tasks' direct
reads plus this task's fresh reads, to have its own `try/except` with debug/warning logging and
graceful continuation — not a single unguarded step was found in any of the code paths this
session actually read start-to-finish.

Specific failure types with actual behavioral test evidence (re-run this task, not just cited):
| Failure injected | Stage | Result | Classification | Evidence |
|---|---|---|---|---|
| LLM/provider raises inside `generate_hypotheses()` | Hypothesis generation | Caught internally, returns `{"error": ...}`, loop continues | A (action fails safely) + E (observable via logger) | `test_real_engine_llm_failure_does_not_kill_loop` (55), `test_generation_exception_does_not_kill_loop` (52) |
| `HypothesisEngine._call()` raises directly (not caught internally) | Hypothesis generation | Caught by `hypothesis_loop()`'s own except, 300s backoff sleep, loop continues | B (cycle fails safely) + E | `test_generation_exception_does_not_kill_loop` (52) |
| `PermissionGateway.execute()` raises | Permission check (email reply/forward) | Fails closed — action blocked, not silently allowed | A + E | `test_gateway_unreachable_fails_closed_for_reply`/`_forward` (53) |
| `PermissionGateway.execute()` denies | Permission check (email, skills) | Action correctly not executed | A + E | Multiple tests, 53 |
| Process crash mid plan-step | Planning/execution | Recovered on next load per GREEN/non-GREEN rules, not silently stranded | A/D + E | `TestCrashRecovery`, 52 |

**Failure types from Phase 11's list not freshly, individually injected this task**: memory
failure, planning failure (beyond the crash-recovery case above), tool-executor failure (beyond
the gateway-denial case), persistence failure, observation failure. For these, the assessment
relies on the structural guarantee above (every `_act_on()`/coroutine sub-step is
try/except-wrapped) rather than a dedicated new injection test per failure type — a real,
acknowledged scope limitation of this pass, not a claim that each was individually verified to the
same S5 standard as the five rows in the table.

---

## 14. Test Results (Phase 12)

**Full suite** (`tests/unit` + `tests/integration`, identical scope/exclusions to tasks 52/55/56/53):

```
2212 collected, 2175 passed, 8 failed, 0 errors, 29 skipped
```

Compared to the stated baseline (2212 collected / 2175 passed / 8 failed / 0 errors / 29 skipped):
identical — same 8 failing test names (`agent_registry` successor reconstruction,
`correction_learner` domain classification ×4, `decision_engine` epistemic scoring ×2, council
red-tier verdict logic), individually re-confirmed unrelated to any of this session's changes
across 4 prior tasks. **Zero new failures from this task** (no production code was modified).

**Focused behavioral suites** (Phase 12's named list), run fresh this task:

```
tests/integration/test_planning_integration.py           19/19  (recovery — 52)
tests/integration/test_phase_a5_hypothesis_consumer.py   30/30  (hypothesis pipeline — 55/56)
tests/unit/test_permission_gateway.py                    34/34
tests/unit/test_permission_gateway_extra.py               88/88  (permission gateway)
tests/test_email_agent_permission_gate.py                  9/9  (53)
tests/loop/test_skill_gateway.py                            7/7  (53)
tests/unit/test_inference_observability_gaps.py            16/16 (50)
```
**203/203 pass** combined (single run, verbatim, this task).

**New failures found this task, root-caused, confirmed pre-existing and unrelated**:
- `tests/unit/test_epistemic_scoring.py::test_stale_domain_reduces_score` — was already in the
  established 8-failure baseline; root-caused fully this task (§9's note; test's mock substring
  check `"stale_domain" in claim_id` never matches the real `claim_id = "action_domain:stale"`
  produced by `domain = action_type.split("_")[0]` — a test-fixture bug, not a production bug).
- `tests/test_regression_governor_capability_routing.py::test_languages_routes_correctly_
  despite_wrong_llm_guess` and `::test_news_trends_routes_correctly_despite_wrong_llm_guess` —
  newly surfaced this task (this file lives outside the tracked tests/unit+integration baseline
  scope, so was never run against the established baseline in any prior task this session).
  Root-caused via isolated re-run with full traceback: `classify_chat_intent()`'s mocked LLM call
  is never reached for these two inputs — a `REGEX_PRECLASSIFY`/`EMBEDDING_MATCH` pre-classify
  layer (confirmed via debug logs showing `raw=''`) intercepts first and returns a different
  `task_type` than the test expects. Confirmed unrelated to any file this session touched
  (`governor.py`, `intent_matcher.py` are pre-existing dirty/untracked state, untouched by any of
  the 4 prior tasks or this one).

**Git diff review this task**: `git status` shows the identical set of pre-existing
modified/untracked files present throughout this entire session (reviewed and confirmed unrelated
in every prior task), plus the 4 files this session's 4 prior tasks actually changed
(`core/loop/autonomous_loop.py`, `core/brain/hypothesis_engine.py`,
`districts/communications/email_agent.py`, plus new test files). **This task added zero new
changes to any production file** — confirmed via `git status` immediately before writing this
document (§ below).

---

## 15. Risk Register (Phase 13)

| Risk | Evidence | Severity | Likelihood | Autonomous reachability | Blocker? |
|---|---|---|---|---|---|
| Device-control (`pc_controller`/`phone_controller`) token-minting call sites not exhaustively traced | §7 | S2 | Low — mechanism fails closed by design | Only if a production caller mints a control token without prior real approval (not found, not ruled out) | No — mechanism is fail-closed; unverified ≠ unsafe, but genuinely unverified |
| Event fan-out task_types for districts beyond security not checked | §7 | S1 | Low — task_types are fixed/internal, not LLM-invented or user-controllable | Yes, event-triggered, fully autonomous | No — structurally low-risk vocabulary, but coverage genuinely incomplete |
| ~70-80 unread subprocess/os.system files | §7 | S1-S2 (unknown per-file) | Unknown | Unknown | No confirmed blocker; genuinely unverified surface |
| RULE 1 not honored by `hypothesis_loop()`/`_coding_companion_nudge()` | §5 | S1 | Certain (always true for these 2 call sites) | Yes, both autonomous | No — advisory-only output, no side effects, but a real rule violation |
| Owner-correction outcome-feedback loop never wired | §9 | S1 | Certain | N/A (learning-quality gap, not an action-safety gap) | No |
| Epistemic dampening operates at coarse (first-token) domain granularity | §9 | S0-S1 | Certain (by design, not a bug) | N/A | No |
| `belief:*` epistemic formation loop still not consulted by scoring | §9 (carried from 51, not re-verified this task) | S1 | Certain per 51's original finding | N/A | No |
| Full end-to-end autonomous cycle not observed as one continuous live run this task | §4 | S1 | N/A | N/A | No — every segment individually S5-verified; only the "all in one observed run" framing is S4 |

**No item in this register meets this document's BLOCKER bar** (unauthorized consequential side
effects, destructive behavior, persistent corruption/stalling, uncontrolled escalation, inability
to recover, silent failure of core autonomy, loss of required observability, runaway resource
consumption, repeated unsafe execution, inability to terminate/contain). Every BLOCKER-class issue
found across this session's 4 prior tasks was fixed and re-verified. What remains is **unverified
surface area and quality-affecting (not safety-affecting) gaps**, not a confirmed active danger.

---

## 16. Remaining Limitations

Carried forward, unchanged, from prior documents (not re-litigated here): `55`/`56`'s marker
compliance and 500-char truncation notes; `53`'s device-control/event-fan-out/subprocess coverage
gaps (§7, §15); `51`'s `belief:*` epistemic and correction-outcome-feedback gaps (§9, §15); `50`'s
partial retry-rate coverage and dormant vendored-client instrumentation gap.

New this task: RULE 1's 2 non-compliant call sites (§5); the precise root cause of 3 pre-existing
test failures not previously root-caused to this depth (§14); the "one continuous observed run"
framing gap noted in §4.

---

## 17. Explicit Experiment Gate (Phase 14)

**B — CONDITIONALLY READY.**

No BLOCKER-class issue is currently open — every one identified across this session's four prior
tasks (`52`'s two MUST-FIX items, `53`'s two confirmed permission bypasses) was fixed and
re-verified this task via fresh test runs (203/203 targeted, full suite unchanged from baseline).

But this verification pass surfaced genuine, currently-unresolved **uncertainty** about whether
several corners of the permission/safety boundary are fully covered — device-control token-minting
call sites, event-fan-out handlers outside the security district, and the majority of
subprocess-using files were not exhaustively traced. Per this task's own explicit final rule
("If there is ANY uncertainty about whether a consequential autonomous path is safely gated... do
NOT classify VECTOR as A — READY"), these open items are sufficient, on their own, to withhold an
A classification — independent of the (lower-severity) RULE 1 and correction-learning findings.

**Required before an A classification, or before accepting these as bounded/constrained risks for
a B-conditional start**:

1. **Exhaustively verify `pc_controller.py`/`phone_controller.py`'s production call sites** —
   confirm every real (non-self-test) caller of `PermissionGateway.grant_control("run_shell_
   command"/"launch_app", ...)` is preceded by a genuine `execute()` RED-tier approval, not a
   direct mint. Verification-only; no fix expected unless a real gap is found, in which case a
   separate remediation task should be opened.
2. **Extend the event-fan-out district-handler check** from `53`/this task's 2-agent (security)
   sample to every district `EVENT_TRIGGER_MAP` can route to — confirm each either ignores
   `task_type` safely (like `node_guard.py`/`threat_scout.py`) or gates real side effects properly.
3. **Sweep the remaining ~70-80 unread subprocess/os.system files** and classify each — most are
   expected to be video/audio encoding or Claude-Code-facing dev tooling (low autonomous-decision
   reachability), but this should be confirmed rather than assumed.

None of these three items requires a code change by default — they are verification tasks. If any
of them surfaces a real gap (analogous to `53`'s Finding 1/2), that specific gap should be fixed
and re-verified in its own narrowly-scoped task before the 7-day experiment begins.

**If the owner chooses to accept the current state of items 1-3 as a bounded, explicitly-understood
risk** (e.g., because the 7-day experiment's actual scenario space doesn't exercise device control,
non-security event-fan-out districts, or the unread subprocess files) rather than commissioning
further verification, that is a legitimate basis for a **constrained B-conditional start** — but
that decision belongs to the owner, not to this document, and should be made explicitly rather than
by default.

---

## 18. Next Steps If Not Ready

Exact next task(s), in priority order:

1. **Task (verification-only)**: trace every production caller of
   `PermissionGateway.grant_control()` for `run_shell_command` and `launch_app`; confirm each is
   downstream of a real RED-tier `execute()` approval. Report findings; do not fix unless
   explicitly authorized in a follow-up task.
2. **Task (verification-only)**: for every district `core/event_bus/wiring.py`'s
   `EVENT_TRIGGER_MAP` can route a downstream task to, read that district's `run()`
   implementation(s) and confirm the fixed/internal `task_type` strings either have no dedicated
   handler (safe by the same pattern already confirmed for security) or are properly gated.
3. **Task (verification-only)**: sweep the remaining subprocess/os.system-using files not yet
   individually read (listed in `53`'s Phase-4 grep output minus the ones already checked across
   `53` and this task) and classify each by autonomous-decision reachability and gating status.
4. **Optional, non-blocking**: decide whether to wire `CorrectionLearner.validate_lesson()` into a
   real outcome-feedback call site, or to explicitly document that correction "learning" is
   detection+injection only (not reinforcement) as an accepted, permanent design choice.
5. **Optional, non-blocking**: decide whether `hypothesis_loop()` and `_coding_companion_nudge()`
   should call `session_hydration_prompt()` for full RULE 1 compliance, or whether their current
   partial-context substitutes (`get_world_state()`, screen OCR) are an accepted, documented
   exception to the stated rule.

---

==================================================
VECTOR PRE-EXPERIMENT GATE
==================================================

Overall:
B — CONDITIONALLY READY

Safety:
Fixed + re-verified for all confirmed findings (53); device-control/event-fan-out/subprocess coverage incomplete — WARNING

Autonomous cognition:
Behaviorally verified (no-user-input reachability confirmed; 21-coroutine crash isolation confirmed)

Memory/learning:
action_domain epistemic loop verified closed; belief:* loop and correction outcome-feedback loop confirmed still open (unchanged, non-blocking)

Hypothesis pipeline:
Fixed + behaviorally verified (55/56, re-confirmed this task, 30/30)

Planning/recovery:
Fixed + behaviorally verified (52, re-confirmed this task, 19/19); executor->gateway chain newly confirmed this task

Permission boundary:
Fixed + behaviorally verified for confirmed findings (53, re-confirmed this task, 16/16); residual unverified surface remains

Tools/actions:
Verified for traced paths; untraced subprocess surface remains

Inference/fallback:
Verified, unchanged (50, re-confirmed this task, 16/16)

Persistence:
Verified — all surveyed state SQLite/JSON-backed, survives restart

Error containment:
Structurally verified (_supervised() wrapper) + 5 specific failure-mode behavioral tests; not every Phase-11 failure type individually injected this task

Observability:
Verified, unchanged (50)

Remaining blockers:
0

Remaining warnings:
7 (device-control call-site coverage; event-fan-out district coverage; subprocess sweep coverage; RULE 1 non-compliance x2 call sites; correction outcome-feedback unwired; belief:* epistemic loop unscored; 2 newly-found unrelated pre-existing test failures)

Required next task(s):
1. Verify pc_controller/phone_controller grant_control() call sites
2. Verify event fan-out handlers for all non-security districts
3. Sweep remaining unread subprocess/os.system files
4. (Optional) Wire or formally accept correction-learning outcome-feedback gap
5. (Optional) Resolve or formally accept RULE 1 gap in hypothesis_loop/_coding_companion_nudge

7-DAY EXPERIMENT:
CONDITIONALLY START — only after items 1-3 above are completed, or explicitly, knowingly accepted as bounded risk by the owner

==================================================
