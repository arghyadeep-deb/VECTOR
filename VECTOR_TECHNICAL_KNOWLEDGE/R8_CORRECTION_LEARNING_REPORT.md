# R8 — Explicit Correction Learning

**Starting HEAD:** `43508df78189d50e1f1d5cb5cde07d6d1cce97aa` (the R6+R7 checkpoint committed at the
start of this overnight pipeline). `git status --short` / `git branch --show-current` /
`git rev-parse HEAD` were run first, per the pipeline's ABSOLUTE OPERATING RULES; the tree was
clean, on `production-hardening-complete`, no stale worktree, no conflicting uncommitted owner work.

## Objective

Establish the smallest honest causal path: **explicit owner correction → capture → validation →
persistence → retrieval → future decision influence** — and only that. Not reward learning, not
sentiment analysis, not automatic interpretation of arbitrary language.

## Audit methodology

Direct source read + repo-wide `Grep` for every real call site of `CorrectionLearner`'s public
methods, cross-checked against `DecisionEngine` (which the R1–R7 pipeline already established as the
one real autonomous decision path) to see whether correction lessons ever reach it. No subagents
were used for this audit — the codebase areas involved (one module, two call sites) were small
enough that direct inspection was faster and more reliable than dispatching parallel read-only
agents and reconciling their findings.

## Files inspected

`core/memory/correction_learner.py` (full file, 785 lines), `core/loop/context_engine.py`
(`_correction_lessons_line`, `session_hydration_prompt`), `core/loop/autonomous_loop.py`
(`_detect_and_store_correction`, `_act_on`, `__init__`, the 2AM `reflect_loop`'s
`expire_old_lessons()` call), `core/loop/decision_engine.py` (confirmed, before this task, zero
references to correction/lesson anywhere), `core/loop/permission_gateway.py`,
`core/city/governor.py` (confirmed no correction references, before and after), `core/config.py`
(confirmed no `correction_scoring`/`epistemic_scoring`-style declared setting existed —
`epistemic_scoring` itself is only a soft `CONFIG.get(..., True)` lookup, no formal Pydantic field —
matched for the new `correction_scoring` flag), `tests/unit/test_correction_learner.py`,
`tests/integration/test_correction_integration.py`, `core/benchmark/tasks/t08_owner_correction_learning.py`.

## Findings

### Capture → normalization → validation (detection-time) → persistence: solid and reachable

`CorrectionDetector.detect()` (regex-pattern-based, 14 explicit + 5 implicit patterns) cleanly
distinguishes explicit corrections ("no, X", "wrong, X", "actually, X" — confidence 0.85–0.95) from
preferences ("I prefer X"), temporary instructions ("just this once"), and normal conversation — all
explicitly rejected before any storage attempt. `LessonExtractor.extract()` refuses to build a lesson
below `MIN_STORE_CONFIDENCE = 0.7`, returning `None`. `CorrectionLearner.process_owner_message()`
dedups via `situation_hash` before storing (`_find_duplicate` → `_consolidate`, which boosts
confidence by +0.05 on repeat and re-stores under the same id unless the correction content itself
changed). Storage is `EpisodicMemory.store(event_type="correction_lesson", ...)` — no new table, an
existing table this repo already treats as append-only-per-event.

### Retrieval: solid and reachable

`retrieve_applicable_lessons()` queries via `EpisodicMemory.recall()` with an FTS-style query built
from `source:owner_correction` + optional `domain:`/situation keywords, filters out
`expired`/`contradicted` and confidence `< 0.5`, sorts by confidence. `build_injection_line()`
formats up to 3 lessons and calls `mark_applied()` on each (increments `times_applied`, updates
`last_applied`). This is the ONE production consumer wired at real call sites:
`core/loop/context_engine.py:284-285` (`_correction_lessons_line()`, itself called from
`session_hydration_prompt()`), which is called before real LLM calls across the codebase
(`governor.py`'s own `_llm_classify`, `chat.py`, `voice.py`, `commands.py`, etc. — 15+ call sites).

### THE GAP: DecisionEngine never consumed correction lessons at all

`core/loop/decision_engine.py` had **zero** references to `correction`/`lesson`/`CorrectionLearner`
anywhere, confirmed by direct grep before this task. Correction lessons could influence what an LLM
was TOLD (prompt text via `session_hydration_prompt()`), but never influenced the mathematical
5-factor candidate-scoring/selection path this entire R1–R10 pipeline is about. This is the single
largest, cleanest missing causal edge the audit found.

### THE ROOT CAUSE: `self._current_action_type` was read but never written

`autonomous_loop._detect_and_store_correction()` builds each lesson's context as:
```python
context = {
    "situation": getattr(self, '_current_action_type', 'conversation') or "conversation",
    "person_id": "owner",
}
```
Repo-wide grep for `_current_action_type` before this task found **exactly one occurrence — this
read**. Nothing anywhere ever assigned `self._current_action_type`. Every real production
correction therefore had `lesson.situation == "conversation"` unconditionally, no matter what
VECTOR had actually just done. Even if DecisionEngine HAD consumed lessons, this constant would have
made every correction indistinguishable from every other — structurally incapable of targeting a
specific action_type. This is the exact missing causal connection the pipeline's R8 phase asked the
audit to find.

### `validate_lesson()`: confirmed S1 (implemented, zero production callers)

Repo-wide grep for `validate_lesson(` found it defined once (`correction_learner.py:591`) and never
called anywhere else in `core/`, `districts/`, `vectorcode/`, or any test outside
`test_correction_learner.py`/`test_correction_integration.py`'s own direct unit tests of the method
itself. `mark_applied()` (also read-adjacent) IS called, but only internally from
`build_injection_line()` — not as an independent production entry point either.

### Edge classification (S0–S5)

| Edge | Classification | Evidence |
|---|---|---|
| capture (detect + extract) | **S4** | `process_owner_message()` real call site in `autonomous_loop._detect_and_store_correction()`, reached from `_handle_user_input()` for `person_id=="owner"`; test-verified pre-existing (`tests/integration/test_correction_integration.py`) |
| detection-time validation (MIN_STORE_CONFIDENCE gate) | **S4** | Same as above — reachable and tested |
| outcome-based validation (`validate_lesson`) | **S1** | Defined, zero production callers anywhere in the repo |
| persistence | **S4** | `EpisodicMemory.store()`, existing table, tested |
| retrieval | **S4** | `retrieve_applicable_lessons()` reached from `build_injection_line()` ← `context_engine._correction_lessons_line()` ← `session_hydration_prompt()`, called from 15+ real LLM call sites including `Governor._llm_classify` |
| decision influence on LLM prompts | **S3** (runtime reachable, not behaviorally proven in this task — out of scope, that's an LLM-output claim, not a deterministic one) | via `session_hydration_prompt()` |
| decision influence on DecisionEngine's 5-factor scoring | **S0 → S5 (this task)** | Was entirely absent before this task; now implemented, wired, and behaviorally verified (§ Tests) |
| `situation` field carrying the real action_type | **S0 → S4 (this task)** | `self._current_action_type` was read-only dead state; now assigned in `_act_on()` |

### Twelve audit questions, answered

1. **Does `validate_lesson()` have production callers?** No — S1, confirmed by repo-wide grep.
2. **What constitutes an explicit correction?** `CorrectionDetector`'s 14 explicit-pattern regex set
   ("no, X", "wrong, X", "actually, X", "I said/meant X", "correction: X", etc.), confidence
   0.85–0.95; implicit patterns (5 more, softer, 0.70–0.85) are also accepted if they clear
   `MIN_STORE_CONFIDENCE`. Preferences/temporary-instructions/plain conversation are explicitly
   excluded first, before any correction pattern is even checked.
3. **Is provenance retained?** Yes — `source="owner_correction"`, `correction_type`,
   `timestamp`, `wrong_behavior` (VECTOR's prior response), `correction` (owner's exact text),
   `confidence`, all persisted and round-tripped through JSON serialization.
4. **Can arbitrary text become a correction?** No — the preference/temporary/no-match branches all
   return `None` before extraction; `MIN_STORE_CONFIDENCE` additionally gates extraction.
5. **Can prompt injection become a correction?** Only if it happens to match one of the fixed regex
   patterns AND originates from `person_id == "owner"` (the ONLY gate at the call site — see
   Limitations, §16-equivalent, for the one real residual risk this does NOT close).
6. **Where is the lesson stored?** `episodic_memory`, `event_type="correction_lesson"` — an existing
   table, no new schema.
7. **Can it be retrieved?** Yes, via FTS-style `recall()` query, confirmed reachable and tested.
8. **Does retrieval affect decisions?** Before this task: only LLM-prompt text (not a mathematical
   decision). After this task: yes, also `DecisionEngine`'s 5-factor score, bounded (§ Implementation).
9. **Can low-confidence corrections become authoritative?** No — `MIN_STORE_CONFIDENCE` (0.7) gates
   storage entirely; the new decision-penalty mechanism additionally re-checks `>= MIN_STORE_CONFIDENCE`
   on every lesson it considers, independent of storage-time filtering.
10. **Can correction influence unrelated situations?** No — the new mechanism requires an EXACT
    string match between `lesson.situation` and the candidate's `action_type`; proven directly by
    `test_j_unrelated_decision_does_not_change`.
11. **Can correction bypass safety?** No — proven by source-text absence of any
    Governor/PermissionGateway reference in the new code paths (§ Tests, `TestGovernanceUnbypassed`).
12. **Is correction distinct from reward/outcome feedback?** Yes — the new mechanism never touches
    `PolicyMemory`, never reads or writes a reward value, and is deliberately independent of
    `validate_lesson()`'s outcome-linked reinforcement (proven by
    `test_unvalidated_lesson_still_influences_decision`).

## Implementation

Two changes, both minimal, both additive to existing structures — no new table, no new subsystem.

### 1. `core/loop/autonomous_loop.py` — root-cause fix

- `__init__`: added `self._current_action_type: str | None = None`.
- `_act_on()`: added `self._current_action_type = winner.action_type` as the very first line inside
  the method body (before any gating), so a correction made right after an action captures the real
  action_type, not the dead constant fallback.

### 2. `core/memory/correction_learner.py` — new bounded decision-influence query

`CorrectionLearner.get_correction_penalty(action_type: str) -> float`: retrieves applicable lessons
via the EXISTING `retrieve_applicable_lessons()`, filters for an EXACT `lesson.situation ==
action_type` match AND `confidence >= MIN_STORE_CONFIDENCE`, and — if one or more match — returns
`min(0.12, best_confidence * 0.15)` using the single highest-confidence match (never summed across
multiple matches, preventing unbounded stacking from repeated/duplicate corrections). No LLM call,
no semantic interpretation of the lesson's free text — pure exact identity matching, the same
philosophy `PolicyMemory.make_situation_hash()` already uses for its own identity, just applied to a
different field (`situation`, not a computed hash) because that's what `LessonExtractor` already
populates from context.

### 3. `core/loop/decision_engine.py` — wiring into the existing 5-factor formula

- `__init__`: added `self._correction_learner = None`.
- New `_get_correction_learner()` lazy getter, matching the existing `_get_epistemic`/
  `_get_metacognition` pattern exactly (sentinel `False` on failure, never retries, degrades to `None`).
- New `_correction_penalty(candidate) -> float`, matching `_bias_penalty`'s exact structure: gated by
  a soft `CONFIG.get("correction_scoring", True)` kill-switch (same undeclared-flag pattern as the
  pre-existing `epistemic_scoring`), delegates to `learner.get_correction_penalty(candidate.action_type)`.
- `_score_candidate()`: `correction_penalty = self._correction_penalty(candidate)` computed alongside
  `bias_penalty`; subtracted from `total` in the same line as `bias_penalty` (`- bias_penalty -
  correction_penalty`); appended to `reasoning_chain`/`reasoning_steps` when nonzero, exactly like
  the existing `meta_cognition`/`epistemic_confidence` entries.

### Safety properties (by construction, not just by test)

- **Bounded**: max 0.12 subtraction from a `[0.0, 1.0]` weighted total — cannot alone force an
  otherwise-terrible candidate to win, and the final score is still clamped to `[0.0, 1.0]`.
- **Cannot touch permission tier**: `gw.classify(action_type)` (RED/YELLOW/GREEN/FORBIDDEN) is a
  static `CONFIG["permission"]` lookup by `action_type` string — entirely independent of
  `total_score`. A correction can never turn a FORBIDDEN action GREEN or skip RED-tier review.
- **Cannot bypass Governor/PermissionGateway**: neither is referenced anywhere in
  `correction_learner.py` or in the new `_correction_penalty`/`get_correction_penalty` methods —
  proven directly by source-text inspection tests, not just by description.
- **Independent of reward semantics**: `PolicyMemory` is never imported, read, or written by any of
  the new code; `update_from_outcome`'s signature is asserted unchanged.

## Tests

`tests/test_r8_correction_learning.py` — **27 tests, all passing**, covering A–N:

- `TestExplicitOnly` (A, B, C, C2, C3) — explicit captured, ordinary/ambiguous/preference/temporary
  all correctly rejected before storage.
- `TestCaptureValidatePersistRetrieve` (D, E, F, G, M, N) — detection-time validation gate proven
  directly on `LessonExtractor.extract()`; provenance round-trips through real JSON
  serialize/deserialize; invalid text rejected; valid lesson retrievable; 10 repeated identical
  corrections still cap the resulting penalty at ≤ 0.12 (no runaway amplification); a genuine
  "restart" simulation (two independent `CorrectionLearner` instances sharing one durable store)
  proves the lesson and its resulting penalty both survive.
- `TestSituationWiringRootCauseFix` — 3 tests directly proving the root-cause fix: the attribute is
  unset before any action; `_act_on()` sets it; and a full, real `_detect_and_store_correction()`
  call after a real `_act_on()` call captures the exact real action_type as `lesson.situation`
  (not `"conversation"`).
- `TestDecisionPathInfluence` (H, I, J) — **the required WITHOUT/WITH causal demonstration**:
  two fully independent `DecisionEngine` instances score the identical candidate pair
  (`send_email` confidence 0.62 vs `check_calendar` confidence 0.60); WITHOUT any correction,
  `send_email` wins (sanity check); WITH an explicit correction targeting `send_email` specifically,
  `check_calendar` wins — the correction is the only variable that changed between the two runs.
  Also: an unrelated action_type's score is provably untouched (`== 0.0`, not just "smaller"); the
  penalty is bounded; and a still-`unvalidated` lesson (never touched by `validate_lesson()`) already
  influences the decision, directly demonstrating the design is independent of the dead
  validation-reinforcement path.
- `TestGovernanceUnbypassed` (K, L) — source-text absence proof, both for `correction_learner.py`
  as a whole and for the two new methods specifically.
- `TestNoRewardConflation` — source-text absence of any `PolicyMemory`/`update_from_outcome`/
  `record_suppression` reference in the new code; `PolicyMemory.update_from_outcome`'s signature
  unchanged; the bound holds even at the maximum possible lesson confidence (0.95).

At least one test crosses real, unmocked components end-to-end:
`test_correction_after_action_captures_real_action_type` runs a REAL `AutonomousLoop._act_on()`
followed by a REAL `AutonomousLoop._detect_and_store_correction()` (only `Governor`/`PolicyMemory`/
`EpisodicMemory` stubbed, matching the established `tests/test_task89c_goal_progress.py` pattern) and
inspects the actual stored JSON row.

## Behavioral evidence

```
WITHOUT CORRECTION:
    candidates: send_email(conf=0.62) vs check_calendar(conf=0.60)
    winner: send_email

WITH EXPLICIT CORRECTION ("no, don't send that email, wait for approval",
                          situation="send_email"):
    candidates: send_email(conf=0.62) vs check_calendar(conf=0.60)   [identical inputs]
    winner: check_calendar
    causal difference: correction_penalty=0.1425→clamped 0.12 applied to send_email
                        (0.12 subtracted from send_email's weighted total is enough
                        to drop it below check_calendar's unpenalized total, given
                        their near-equal starting scores)
```

This satisfies the task's required causal demonstration directly, not by inference from row counts
or confidence values alone.

## Regression comparison

Targeted correction/decision/policy/governance suite (`tests/test_r8_correction_learning.py` +
`tests/test_task92_r7_decision_candidate_correlation.py` + `tests/test_task91_r6_candidate_diversity.py`
+ `tests/unit/test_decision_engine.py` + `tests/test_decision_engine.py` +
`tests/unit/test_correction_learner.py` + `tests/integration/test_correction_integration.py` +
`tests/test_policy_reward_identity.py` + `tests/test_counterfactual_block_penalizes_policy.py` +
`tests/test_task89c_goal_progress.py` + `tests/unit/test_governor_dispatch_thread_hop.py` +
`tests/unit/test_permission_gateway_extra.py`): **4 failures**, all confirmed, via a direct
`git stash` before/after comparison, to be **byte-identical to the pre-existing baseline** —
`test_correction_learner.py::test_extract_from_explicit_correction`,
`test_correction_learner.py::test_tags_include_domain_and_source`,
`test_correction_integration.py::test_full_loop_stores_and_retrieves`,
`test_correction_integration.py::test_lifecycle_unvalidated_to_validated` — all 4 are the SAME
`LessonExtractor._detect_domain()` domain-detection defect and the SAME dead-`validate_lesson()`-path
test already present in the Task 90/91/92 baseline, unrelated to and unmodified by R8's own changes
(R8 never touches `_detect_domain()`).

Full non-Ollama suite comparison: see the FINAL VERDICT block below (captured after the background
run this report was written alongside completed).

## Limitations

- **`validate_lesson()` remains S1 (dead)** — deliberately not wired to any real caller in this task.
  The one plausible real caller (an owner-facing "was that correction right?" confirmation surface)
  does not exist in production today, and building it would mean adding new interaction surface
  (API route or voice/chat prompt) beyond `DecisionEngine`/`autonomous_loop` correlation — judged too
  large for "minimum viable" tonight and reported here rather than invented.
- **`LessonExtractor._detect_domain()`'s pre-existing keyword-matching bug** (the 4 baseline
  failures above) was found but NOT fixed — out of scope for R8, which must not "fix unrelated
  defects." It does not affect the new `get_correction_penalty()` mechanism, which matches on
  `situation` (the real action_type), never on `domain`.
- **Prompt-injection risk is only partially mitigated**: `_detect_and_store_correction()` is gated on
  `person_id == "owner"`, but this repo's own person-identification mechanism (voice/face/session)
  is a SEPARATE system this task did not audit — if that identification were ever spoofed, an
  attacker-controlled utterance matching one of the fixed regex patterns could still produce a
  low-magnitude (≤0.12), single-action-type-scoped score penalty. This is bounded and cannot bypass
  RED/YELLOW/FORBIDDEN gating, but is worth flagging precisely rather than silently assuming solved.
- **The decision-influence mechanism only ever produces a PENALTY, never a boost.** This was a
  deliberate, conservative design choice (mirrors R6's "never fabricate/never promote past the real
  scored alternatives" philosophy) — a correction can make VECTOR less likely to repeat a specific
  mistake, but cannot make an otherwise-unlikely alternative artificially more attractive beyond its
  own real score.
- **LLM-prompt-level influence (`session_hydration_prompt()`) was traced (S3) but not behaviorally
  re-verified in this task** — that would require a real LLM call and inspecting its output, which is
  an LLM-behavior claim, not a deterministic decision-engine claim, and was judged out of scope for
  R8's specific "decision path" framing (R1–R10's own definition of "decision" throughout this
  pipeline has consistently meant `DecisionEngine.evaluate()`).

## Maturity classification

Per the pipeline's own S0–S5 scale, for the specific edge "explicit correction → DecisionEngine
decision influence":

**S5 — behaviorally verified.** Not S4 (test-verified only) — the WITHOUT/WITH causal demonstration
(§ Behavioral evidence) is a real behavioral proof, not a unit-level assertion about internal state,
using the actual production `DecisionEngine.evaluate()` method with no candidate injection, no
hardcoded winner, no scorer alteration for the experiment.

For "outcome-based validation → decision influence" specifically: **S1 (dead)**, honestly reported,
not silently left ambiguous.

## Final verdict

```
STARTING HEAD: 43508df78189d50e1f1d5cb5cde07d6d1cce97aa
ROOT CAUSE FOUND: self._current_action_type read but never assigned (autonomous_loop.py)
                  + DecisionEngine never consumed correction lessons at all
IMPLEMENTATION: minimal, additive, 3 files (autonomous_loop.py, correction_learner.py, decision_engine.py)
NEW TABLE: none
NEW SUBSYSTEM: none
REWARD SEMANTICS CHANGED: none (proven by signature + source-text tests)
GOVERNANCE BYPASSED: none (proven by source-text tests)
CAUSAL DEMONSTRATION: PROVEN (WITHOUT correction: send_email wins / WITH correction: check_calendar wins)
NEW TESTS: 27/27 PASS
FULL NON-OLLAMA SUITE: 5,143 collected / 5,093 passed / 13 failed (all pre-existing, byte-identical
                        to Task 90/91/92 baseline, 0 new) / 37 skipped / 0 errors
NEW REGRESSIONS: 0
MATURITY: S5 (behaviorally verified) for correction→DecisionEngine influence;
          S1 (dead, honestly reported) for validate_lesson()/outcome-based reinforcement
VERDICT: R8 COMPLETE
```

**FINAL HEAD:** `ff6922f6b2f5aeda33053605a27e877758ad2cc5`
