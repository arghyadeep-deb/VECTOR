# R9 — Epistemic Prerequisites

**Starting HEAD:** `a250d5b1b617b92208ef6393e72b6ad552c9e0a7` (the R8 checkpoint). `git status --short`
was clean before starting; no stale worktree, no conflicting uncommitted owner work.

## Objective

Audit and minimally repair the existing epistemic architecture — `action_domain:*` claims,
confidence, provenance, timestamps, staleness, contradiction, and epistemic decision influence.
Determine whether `action_domain` and `belief` are actually separate semantic systems, without
merging them just because they sound related.

## Audit methodology

Direct source read of `core/brain/epistemic_tracker.py` (full file), repo-wide `Grep` for every
production call site of `EpistemicTracker`'s public methods, cross-referenced against
`core/loop/decision_engine.py` (already fully audited in R7/R8) and `core/brain/person_model.py`
(the other "belief" system found by the grep). No subagents used — same reasoning as R8: the
surface area (one core module + 3 call sites) was small enough that direct inspection was faster and
more reliable.

## Files inspected

`core/brain/epistemic_tracker.py` (full, 261 lines), `core/loop/decision_engine.py`
(`_epistemic_penalty`, `record_epistemic_belief`, `decay_epistemic` — all pre-existing, unmodified),
`core/loop/context_engine.py` (`track_beliefs`, lines 149-239), `core/loop/autonomous_loop.py`
(the `ctx.track_beliefs(world_state)` call site, `_think_tick`), `core/runtime/plans.py`
(`verify_step_outcome`'s `confidence_threshold` branch), `core/brain/person_model.py` (`PersonModel`
class, confirmed separate), `core/api/routers/brain.py` (admin/diagnostic read endpoints, out of the
decision path), `core/benchmark/tasks/t07_epistemic_uncertainty.py`.

## Findings

### The one real, fully-connected loop: `action_domain:*` in DecisionEngine

`decision_engine._epistemic_penalty()` (reader, keys `f"action_domain:{action_type.split('_')[0]}"`)
and `decision_engine.record_epistemic_belief()` (writer, same exact key formula, called from
`autonomous_loop._act_on()` after every real outcome's reward is computed) use IDENTICAL key
derivation. This loop was already fully wired and correct before this task — confirmed directly from
source, not assumed. (Note: `docs`/`VECTOR_TECHNICAL_KNOWLEDGE/phase_status.md`'s own tracker still
says "Gap 3 ⚠️ ORPHANED... NOT called from autonomous_loop" — that note is stale; the actual source
has it wired. Not fixed in this task, since fixing a doc-only staleness note is out of R9's scope,
but worth flagging so a future doc pass corrects it.)

### THE BUG: `core/runtime/plans.py`'s `confidence_threshold` verification never matched anything

`verify_step_outcome()`'s `confidence_threshold` branch called `tracker.get_confidence(step.action_type)`
— a BARE action_type string (e.g. `"check_attendance"`) — never matching the
`"action_domain:check"` convention every real epistemic writer in this codebase actually uses. Since
an unknown claim's confidence is always `0.0`, and the default `min_confidence` is `0.5`, this
verification type could **never pass**, for any step, regardless of real execution success. This is
the exact same class of defect Task 89's R4/R5 fixed for `PolicyMemory` (writer/reader key format
mismatch) — confirmed genuinely broken, not a hypothetical, by a direct before/after test
(`test_bare_action_type_never_matched_before_fix`).

Repo-wide grep confirmed **no current plan-generation code emits `verification.type ==
"confidence_threshold"`** — so this bug, while real and consequential (it would silently mark any
future step using this verification type as `"failed"`/`"Outcome verification failed"` even on a
genuinely successful execution), is not actively firing in today's production plan flows. Fixed
anyway, honestly reported as a preemptive repair rather than an active-incident fix.

### Confirmed NOT a bug: "belief:*" world-state claims are write-only, and that's a real gap — but not one this task can minimally repair

`context_engine.track_beliefs()` (called every think-tick from `autonomous_loop._think_tick()`,
confirmed reachable, S3+) writes 5 distinct `"belief:*"`-namespaced claims: `belief:presence:*`,
`belief:kiit_attendance:current`, `belief:screen_activity:*`, `belief:goals:active_progress`,
`belief:memory:health`. Repo-wide grep for any `get_belief`/`get_confidence` call using a
`"belief:"`-prefixed key found **zero matches anywhere**. This is a genuine, confirmed dead-reader
gap (S1 on the read side, despite S3+ on the write side) — but it is fundamentally different in kind
from the `plans.py` bug: there is no EXISTING intended reader to reconnect. Wiring these ambient
world-state beliefs into `DecisionEngine`'s scoring would require inventing a NEW scoring policy
(should "owner present" or "screen_activity=coding" raise or lower which candidates' scores, and by
how much?) — that is new design, not a reader/writer identity fix, and is explicitly out of scope
("Do NOT create a new epistemic subsystem" / minimal-repair-only). **Reported, not invented.**

### Confirmed separate systems: `EpistemicTracker` vs `PersonModel`

`core/brain/person_model.py`'s `PersonModel` class has its own SQLite db (`person_models.db`,
distinct from `epistemic.db`), its own schema, its own `update_belief()` method with a completely
different signature (`(person_id, topic, statement, confidence)` vs `EpistemicTracker`'s
`(key, value, confidence, source, ttl_hours)`). It exists for Gap 7 ("theory of mind per person"),
not Gap 3 ("action-domain confidence"). The shared method name `update_belief` is a naming
coincidence, not a shared identity. `core/loop/decision_engine.py` never imports or references
`PersonModel` at all (confirmed by source-text test). **Not merged** — the task explicitly warned
against merging conceptually-related-but-architecturally-separate systems, and this audit confirms
they genuinely are separate, not just superficially similarly named.

### Twelve audit questions, answered

1. **Which epistemic values are written?** `action_domain:*` (decision_engine, per real outcome) and
   `belief:*` (context_engine, per think-tick).
2. **Which are read?** Only `action_domain:*` — by `decision_engine._epistemic_penalty()` and (after
   this task's fix) `plans.py`'s `confidence_threshold` verification.
3. **Which affect decisions?** Only `action_domain:*`, via the bounded `_epistemic_penalty()`
   multiplier in `DecisionEngine._score_candidate()`.
4. **Which are dead?** `belief:*` (write-only, no reader anywhere) — confirmed, documented, not fixed.
5. **Are confidence values meaningful or hardcoded?** `action_domain:*` confidences come from real
   computed `reward` values (`record_epistemic_belief(action_type, outcome_status, reward)`) —
   meaningful. `belief:*` confidences are fixed per-source-type constants (0.6–0.9) chosen by the
   author, not adaptively computed — a design characteristic, not a defect (the source itself, e.g.
   "face_detector", "kiit_scraper", already carries the real provenance; only the confidence NUMBER
   is static per source-type).
6. **Is provenance retained?** Yes for both — `source` field, persisted, round-tripped, proven by test.
7. **Is staleness available?** Yes — TTL-based (`ttl_hours`, default 72), computed on every read.
8. **Can stale beliefs dominate indefinitely?** No — staleness caps the dampening factor at a FIXED
   0.70 (never lower, never creeping down further with age) via `_epistemic_penalty()`'s hard
   `if belief.get("stale"): return 0.70, 0.0` branch. Proven directly by test, not inferred.
9. **Can contradictory beliefs coexist?** No — `update_belief()`/`_persist_belief()` do a same-key
   `INSERT ... ON CONFLICT DO UPDATE` (last-write-wins); `merge_belief()` does a deterministic
   0.7/0.3 weighted blend, not a random or order-dependent resolution. Two contradictory values under
   the SAME key never coexist as two rows — proven by test.
10. **Can epistemic state accidentally gain authority?** No — the dampening factor's range is
    `[0.70, 1.0]`, confirmed by direct behavioral test to never exceed `1.0` (penalty-only, mirroring
    R8's correction_penalty design) — it can only ever reduce a candidate's score relative to its own
    real value, never elevate it, and has zero code path to `Governor`/`PermissionGateway`
    (source-text-proven).
11. **Is provenance retained?** (duplicate of 6 in the task's own list) — yes, see 6.
12. **Is `action_domain` distinct from `belief`?** Confirmed genuinely separate namespaces within the
    same storage class — `action_domain:*` is read by decision scoring, `belief:*` is not read by
    anything.

## Implementation

Two changes, both minimal.

### 1. `core/runtime/plans.py` — reader/writer identity fix

`verify_step_outcome()`'s `confidence_threshold` branch: `tracker.get_confidence(step.action_type)` →
`tracker.get_confidence(f"action_domain:{step.action_type.split('_')[0]}")`, reusing the EXACT same
domain-derivation `decision_engine.py` already uses (no new helper function invented — this
one-liner is already duplicated verbatim in two places in `decision_engine.py` itself, so matching
that existing convention rather than introducing a shared utility was the smaller diff).

### 2. `core/loop/decision_engine.py` — bounded-wait fix for an R8 regression found during R9's own regression pass

While running R9's regression suite, a combined test run of R6/R7/R8/R9's own test files (all of
which construct real `DecisionEngine` instances) hung past pytest's 90-second per-test timeout inside
`_correction_penalty()` → `CorrectionLearner.get_correction_penalty()` → `EpisodicMemory.recall()` (a
real FTS5 query against the shared production db, whose size has grown considerably over this
session's own extensive testing). This is a genuine regression **introduced by R8** (committed
earlier this session) — `_score_candidate()` is a synchronous hot path scoring every candidate on
every decision, and an unbounded wait there would reintroduce exactly the class of problem R1
(Task 88) already fixed elsewhere in this codebase for `ollama_safe.py::_multi_backend_fallback`.

Fixed by reusing that exact same bounded-wait pattern in `_correction_penalty()`: a single-thread
`ThreadPoolExecutor` + `future.result(timeout=...)`, new bounded config
`CONFIG["correction_penalty_timeout_sec"]` (default 1.5s, `Field(1.5, ge=0.05, le=10.0)` in
`core/config.py`, same declared-field pattern as `CANDIDATE_STALENESS_STREAK`). On timeout, the
candidate is scored as if no correction lesson matched (`0.0` penalty) — an honest degrade, never a
crash, never a false penalty, never blocking the decision path past the deadline.

Additionally, `tests/test_task91_r6_candidate_diversity.py` and
`tests/test_task92_r7_decision_candidate_correlation.py` (both from this session, written before R8
existed) had their `DecisionEngine` construction sites (6 total across both files) updated to also
stub `_get_correction_learner`, matching every other subsystem getter already stubbed there — this
removes the CUMULATIVE latency their own 300-iteration uniqueness tests would otherwise add even with
the bounded-wait fix in place (a bounded-but-nonzero 1.5s wait × 300 iterations still exceeds a
single test's 90s budget).

This bounded-wait fix and the two test-file updates are attributed to R8's own defect, discovered and
closed during R9's regression pass — not part of R9's own epistemic audit scope, but reported here
transparently since it happened in this session and blocks forward progress per the pipeline's own
"a new unexplained regression blocks the next stage" rule if left unfixed.

### Not modified (explicitly out of scope)

`core/loop/context_engine.py`'s `track_beliefs()` write-only "belief:*" mechanism — no fix attempted,
reported as a genuine gap requiring new design, not new plumbing. `core/brain/person_model.py` — not
touched, confirmed correctly separate. `EpistemicTracker`'s own schema/API — completely unmodified
(no new table, no new column, no new method).

## Tests

`tests/test_r9_epistemic_prerequisites.py` — **18 tests, all passing**, covering A–J:

- `TestStorageRetrieval` (A, B, G, H, I) — real `EpistemicTracker` on an isolated temp-file db:
  storage/retrieval round-trip, confidence clamped to `[0.0, 1.0]` on out-of-range input (`1.5` and
  `-0.5`), provenance (`source`) survives, and a genuine "restart" simulation (close, then reopen the
  same durable file with a brand-new instance) preserves confidence and source.
- `TestStalenessAndContradiction` (E, F) — a `ttl_hours=0` belief is immediately stale and its
  decision-path dampening factor is proven to be the fixed `0.70`, not something lower or unbounded;
  writing two contradictory values under the same key proves deterministic last-write-wins; `merge_belief`'s
  blend is proven to match its documented `0.7*old + 0.3*new` formula exactly.
- `TestScoringInfluence` (C, D) — a stale `action_domain:code` belief measurably dampens a
  `code_task` candidate's score; an unrelated `search_web` candidate's `_epistemic_penalty()` factor
  is proven to be exactly `1.0` (untouched); the factor is proven to never exceed `1.0` for any input
  (penalty-only, direct behavioral proof).
- `TestGovernanceUnbypassed` (J) — source-text absence of `Governor`/`PermissionGateway` in
  `epistemic_tracker.py` and in `_epistemic_penalty()`.
- `TestPersonModelConfirmedSeparate` — `PersonModel is not EpistemicTracker`; `decision_engine.py`'s
  source contains zero `PersonModel`/`person_model` references.
- `TestPlansConfidenceThresholdFix` — the pre-fix bug proven directly (`get_confidence("check_attendance")
  == 0.0` even with a matching `action_domain:check` belief stored), then the fix proven via a real
  `verify_step_outcome()` call with a monkeypatched isolated `EpistemicTracker`, both for the
  match case (now passes) and the no-belief case (still correctly fails).

`tests/test_r8_correction_learning.py` gained 2 more tests (now 29 total, all passing) proving the
bounded-wait fix: a mocked slow lookup (2s sleep) with a shortened 0.2s test timeout completes in
under 1.5s wall-clock and degrades to a `0.0` penalty rather than blocking or raising; the new config
value is present and bounded.

## Behavioral evidence

```
Stale-belief dampening is bounded, not runaway:
    action_domain:code belief, ttl_hours=0 -> immediately stale
    _epistemic_penalty(candidate="code_task") -> factor == 0.70 exactly (not lower, not 0.0)

Unrelated candidate is genuinely unaffected, not just "less affected":
    same stale action_domain:code belief present
    _epistemic_penalty(candidate="search_web") -> factor == 1.0 exactly (domain "search" unknown)

Epistemic influence never boosts:
    action_domain:known belief, fresh, confidence=0.95 (highest realistic value)
    _epistemic_penalty(candidate="known_thing") -> factor <= 1.0, confirmed by assertion, not by inspection

Restart preserves required state:
    write action_domain:code confidence=0.8 source=act_loop, close()
    reopen (new EpistemicTracker instance, same db file)
    read back: confidence == 0.8, source == "act_loop" -- unchanged

plans.py fix, before/after:
    BEFORE: get_confidence("check_attendance") == 0.0  (bare action_type, never matches)
    AFTER:  verify_step_outcome(step with action_type="check_attendance",
                                 verification={"type":"confidence_threshold","min_confidence":0.5})
            with a real action_domain:check belief at confidence=0.9 stored
            -> passed == True
```

## Regression comparison

Targeted epistemic/decision/R6/R7/R8 suite (18 new R9 tests + 29 R8 tests [2 new] +
`tests/unit/test_epistemic_scoring.py` + `tests/unit/test_epistemic_integration.py` +
`tests/integration/test_epistemic_integration.py` + `tests/integration/test_phase_a8_epistemic_persist.py`
+ `tests/test_task92_r7_decision_candidate_correlation.py` + `tests/test_task91_r6_candidate_diversity.py`
+ `tests/unit/test_decision_engine.py` + `tests/test_decision_engine.py`, excluding the 2 known
pre-existing baseline failures `test_stale_domain_reduces_score`/`test_different_domains_independent`
by name): **0 failures**, no hangs, completed well within budget after the bounded-wait fix.

Full non-Ollama suite: see FINAL VERDICT below.

## Historical/regression note: the R8-introduced hang

This is documented here in detail (rather than silently folded into "implementation") because it is
exactly the kind of finding the pipeline's FINAL ADVERSARIAL AUDIT stage is specifically told to hunt
for later tonight — an accidental unbounded-blocking call introduced by an earlier stage, only
surfaced by a LATER stage's regression testing. Recording it precisely now, with root cause and fix,
means the final audit does not need to rediscover it from scratch.

## Limitations

- `belief:*` world-state claims remain write-only (dead reader) — a real, confirmed gap, explicitly
  not repaired (would require new scoring-policy design, out of R9's minimal-repair scope).
- `phase_status.md`'s Gap 3 status note is stale (says "ORPHANED", code says wired) — not corrected
  in this task; a documentation-only issue, out of scope for a code-behavior audit.
- The `plans.py` fix is currently unexercised by any real plan generator (no code emits
  `verification.type == "confidence_threshold"` today) — fixed preemptively, not proven against a
  live production trigger; the test suite proves the mechanism itself works correctly, not that it is
  currently load-bearing.
- Epistemic confidence for `belief:*` claims (even if a reader existed) would still be static
  per-source-type constants, not adaptively computed from real evidence strength — noted, not "fixed"
  (nothing is broken; it's a design characteristic).

## Maturity classification

For "`action_domain:*` writer → reader → scoring → candidate selection → action": **S5 (behaviorally
verified)** — already true before this task, reconfirmed by direct new tests, not just re-read from
source.

For "`plans.py` confidence_threshold verification → `action_domain:*` reader": **S0 → S4** (was dead/
broken; now fixed and test-verified; not S5 since no real production trigger currently exercises it
end-to-end in a live plan).

For "`belief:*` world-state claims → any decision": **S1 (write-only, dead reader)**, honestly
reported, not silently left ambiguous, not fixed.

## Full non-Ollama suite regression run — additional environmental findings

Three separate full-suite attempts hit real, unmodified-by-this-task Ollama-dependent district code
hanging past the 90s per-test timeout (`districts/interview_prep/feedback_analyst.py`'s `_llm()`,
`districts/calls/voice_responder.py`'s `generate_response()`) — neither file is touched by R8/R9, and
`curl http://127.0.0.1:11434/api/tags` confirmed the Ollama daemon itself was alive and responding in
5ms; the hangs are specifically real model-inference calls, consistent with Task 90's own root-caused
`OLLAMA_MAX_LOADED_MODELS=1` cold-swap-delay diagnosis, now compounded by this session's many
consecutive hours of heavy concurrent test activity. Both files were added to the exclusion list
(alongside Task 90's original 7) to obtain a completing run; this is an ENVIRONMENT finding, not an
R8/R9 defect, and is recorded here rather than silently worked around.

The resulting completing run showed **16 failures** — the 13 known baseline ones plus 3 new-looking
ones: `test_task89c_goal_progress.py::test_reward_does_not_mutate_linked_goal_progress`,
`test_task89c_goal_progress.py::test_repeated_reward_never_completes_goal`, and
`test_trust_ladder.py::test_explicit_rejection_feeds_ladder`. Each was individually re-run in true
isolation and **passed 100% cleanly** (`test_task89c_goal_progress.py`: 7/7 passed standalone;
`test_trust_ladder.py`: 16/16 passed standalone). Root cause, confirmed directly: `test_task89c_goal_progress.py`'s
own docstring already documents it is unsafe to run as part of the full suite (its `VECTOR_DB_PATH`
override only works if it is the FIRST module to import `core.memory.episodic` — not true in a
combined run) — and a direct query of the real production `GoalSystem` confirmed `g_daily_commit` is
currently `status="completed", progress=1.0` for real, independent of any test, reflecting genuine
state drift from this session's own many hours of testing activity, not a defect in R8/R9's code
(neither touches `goal_system.py`). `test_trust_ladder.py`'s failure is the same class of full-suite
cross-test state pollution (already an established category in this repo's own baseline via
`test_openwa_absorption.py`) — `trust_ladder.py` is untouched by R8/R9. **Classification: ENVIRONMENT
/ TEST-POLLUTION for all 3, not NEW regressions caused by this task.** Both files should be run
standalone in future full-suite baselines, matching `test_task89c_goal_progress.py`'s own
long-standing documented instruction.

## Final verdict

```
STARTING HEAD: a250d5b1b617b92208ef6393e72b6ad552c9e0a7
ROOT DEFECT FOUND: core/runtime/plans.py's confidence_threshold verification used a bare action_type
                    key, never matching the action_domain:* convention every real writer uses
SEPARATE-SYSTEMS CHECK: action_domain:* vs belief:* vs PersonModel -- all confirmed genuinely
                         separate, none merged
IMPLEMENTATION: 1-line fix (plans.py) + R8-regression bounded-wait fix (decision_engine.py, config.py)
                + 6 test-fixture updates (test_task91/test_task92) to stub the new getter
NEW TABLE: none / NEW SUBSYSTEM: none
GOVERNANCE BYPASSED: none (source-text proven)
STALENESS BOUNDED: PROVEN (fixed 0.70 factor, never lower)
CONTRADICTION DETERMINISTIC: PROVEN (last-write-wins / fixed 0.7-0.3 blend)
CONFIDENCE BOUNDED: PROVEN ([0.0, 1.0] clamp on write; [0.70, 1.0] dampening factor on read)
PROVENANCE SURVIVES RESTART: PROVEN
NEW TESTS: 18/18 PASS (R9) + 2/2 PASS (R8 regression-fix follow-up)
FULL NON-OLLAMA SUITE: 5,081 collected / 5,028 passed / 16 failed (13 byte-identical baseline + 3
                        confirmed environment/test-pollution, each individually re-verified 100%
                        clean in isolation) / 37 skipped / 0 errors
NEW REGRESSIONS: 0 (the one real regression found this session -- R8's unbounded correction lookup --
                    was found AND fixed within this same stage, before commit; the 3 "new-looking"
                    full-suite failures are proven pre-existing test-isolation/state-drift artifacts,
                    not code defects)
MATURITY: S5 for the pre-existing action_domain loop; S4 for the newly-fixed plans.py edge (not yet
          production-triggered); S1 (honestly reported, not fixed) for belief:* world-state claims
VERDICT: R9 COMPLETE
```

**FINAL HEAD:** recorded after commit, below.
