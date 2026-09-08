# Task 91 — R6 Candidate Diversity (Staleness-Only)

**Authoritative HEAD verified at task start:** `b8d5b406b3d2b66334a76903d8d8765b9c9f9e02` (matches
the checkpoint named in the task). `git status` showed only the untracked Task 90 report from the
previous turn — no other pending changes, no divergence from the authoritative branch. No worktree
was created or used. Segment2/PID 37588 was not running, not started, not touched. `.env` was not
modified.

---

## 1. Executive summary

VECTOR's candidate-selection loop (`DecisionEngine.evaluate()`) had no memory of its own prior
decisions: it always picked the single highest-scoring candidate, every single time, with zero
regard for whether that exact same candidate had just won the previous four, ten, or hundred
evaluate() calls. If nothing in a goal's tags/params changed, the same `(action_type, params)`
identity could dominate every think-loop tick indefinitely.

R6 adds a **staleness-only** guard directly inside `evaluate()`: if a candidate identity has been
the actual winner for `CONFIG["candidate_staleness_streak"]` (default **5**) or more *consecutive*
calls, the next distinct candidate already present in the real, already-scored ranked list is
selected instead. Nothing is invented — no new `Candidate` object is ever constructed, no
`action_type` is ever changed, and if no distinct alternative exists among the real candidates, the
stale winner is kept exactly as before. The claim this task supports, and no more:

> VECTOR now has staleness-aware candidate selection that can avoid repeatedly selecting an
> unchanged stale candidate when a safe existing alternative is available.

## 2. Exact pre-fix behavior

`core/loop/decision_engine.py::evaluate()` computed `ranked = sorted(candidates, key=...,
reverse=True)` and unconditionally set `winner = ranked[0]` — a pure, stateless, per-call
computation with no reference to any past `evaluate()` call. `TestPreFixBehaviorBaseline` in the new
test suite (`tests/test_task91_r6_candidate_diversity.py`) proves this directly: five consecutive
`evaluate()` calls with an unchanged candidate set all return the identical winner, and nothing in
the pre-fix code path would ever have made that stop.

## 3. Source locations inspected (pre-implementation audit)

| Component | File | Finding |
|---|---|---|
| `DecisionEngine` | `core/loop/decision_engine.py` | `evaluate()` (candidate scoring + winner selection), `_score_candidate()`, `_make_situation_hash()` — the exact canonical identity function to reuse |
| autonomous_loop decision-selection path | `core/loop/autonomous_loop.py:906-990` | Builds `candidates` from goal actions (`_TAG_TO_ACTION` mapping) + `_get_plan_candidates()`, calls `self._get_decision().evaluate(candidates)`, then acts on `decision.winner` through ContinueGate → CounterfactualMemory veto → ThreatDetector → RED-tier red-team review → PermissionGateway/VectorCode gateway → skills → execution |
| Candidate generation | `core/loop/autonomous_loop.py:880-935` (goal actions) and `:1479-1510` (`_get_plan_candidates`) | Goal-action candidates: `params={"goal_id": ..., "title": ...}` — stable across ticks unless the goal itself changes. Plan-step candidates: `params={**step.params, "_plan_id": plan.id, "_step_id": step.id}` — inherently unique per plan step, confirming candidate identity is already meaningful and stable in this codebase |
| Candidate scoring | `core/loop/decision_engine.py::_score_candidate()` | 5-factor formula (unchanged, R1-R5 semantics untouched) |
| Candidate persistence/history | `core/memory/policy.py` (`policy_memory` table: `avg_reward`, `sample_count`, `veto_count`) | No existing "times selected as winner" signal — `sample_count` only increments on a real post-execution outcome (gated behind many downstream systems), not on being chosen by `evaluate()`. Not the right signal for this task; not reused for streak tracking |
| PolicyMemory reader/writer paths after R4/R5 | `core/memory/policy.py::make_situation_hash()`, `get_score()`, `update_from_outcome()`, `record_suppression()` | Confirmed unchanged by this task; `make_situation_hash()` reused as-is (read-only call) |
| Existing staleness-related fields/helpers | grepped `stale|staleness` repo-wide | Only pre-existing concept is `EpistemicTracker`'s TTL-based **domain**-belief staleness (`core/brain/epistemic_tracker.py`, consumed by `decision_engine._epistemic_penalty()`) — semantically different (confidence-in-a-*domain* staleness, not candidate-*identity* repetition) and explicitly out of scope ("DO NOT modify epistemic semantics"); not reused, not competed with |
| Existing decision/candidate identifiers | `Candidate` dataclass (`core/loop/decision_engine.py:14-34`) | No existing identity field; identity is derived the same way policy scoring already derives it — `(action_type, params)` via `PolicyMemory.make_situation_hash()` |

## 4. Root cause

`evaluate()`'s winner-selection step (`winner = ranked[0]`) was a pure function of the current
candidate set's scores alone. There was no mechanism anywhere in the call chain — not in
`DecisionEngine`, not in `autonomous_loop`, not in `PolicyMemory` — that ever compared the current
winner against *who won last time*. A structurally stale decision (same action, same params, every
tick) was therefore indistinguishable from a correct, intentional, repeated decision — both looked
identical to the code.

## 5. Exact implementation

**`core/loop/decision_engine.py`** — two changes, both additive:

1. `DecisionEngine.__init__` gained two new instance attributes:
   ```python
   self._winner_streak_hash: str | None = None
   self._winner_streak_count: int = 0
   ```
   Process-local, not persisted to any database — a restart clears all streaks by design (matches
   the precedent set by Task 89B's `_FANOUT_EDGE_COOLDOWN_SEC`, which is also explicitly
   not-persisted for the same reason: a fresh process should not inherit stale suppression state
   from before it started).

2. New method `_select_staleness_aware_winner(self, ranked: list[Candidate]) -> Candidate`,
   inserted right after `_score_candidate()` and called from `evaluate()` in place of the old
   `winner = ranked[0]`:
   ```python
   ranked = sorted(candidates, key=lambda c: c.total_score, reverse=True)
   winner = self._select_staleness_aware_winner(ranked)
   ```
   The method (full docstring in source):
   - Computes `top_hash = self._make_situation_hash(top)` — reusing the exact same
     `PolicyMemory.make_situation_hash()` call this class already used for policy scoring. **No
     second identity system was created.**
   - `is_stale = (top_hash == self._winner_streak_hash and self._winner_streak_count >=
     CONFIG["candidate_staleness_streak"])`.
   - If stale: scans `ranked[1:]` for the first candidate whose hash differs from `top_hash`. If
     found, that candidate becomes the winner (log line records the suppression). If not found, the
     stale candidate remains the winner, unchanged — **no substitute is ever manufactured.**
   - Updates the streak counter against whichever candidate actually won: same hash as last
     time → increment; different hash → reset to 1. This is the entire "meaningful change" logic —
     see §6.

**`core/config.py`** — one new setting, following the exact pattern of Task 89B's
`FANOUT_EDGE_COOLDOWN_SEC`:
```python
CANDIDATE_STALENESS_STREAK: int = Field(5, ge=1, le=1000)
```
plus its `CONFIG["candidate_staleness_streak"]` mapping entry. Bounded (`ge=1, le=1000`), owner-
tunable via `core/config.py` per this repo's own configuration convention (`.claude/rules/code_style.md`
— "ALL configurable values → CONFIG dict"), no new configuration framework.

No new database table. No new memory subsystem. No historical `policy_memory` rows touched or
reinterpreted. No change to `Candidate`'s or `Decision`'s dataclass shape.

## 6. Staleness definition (explicit, deterministic)

A candidate identity `H = make_situation_hash(action_type, params)` is **stale** exactly when: it
was the actual `evaluate()` winner on the immediately preceding call, AND it has now been the actual
winner for `candidate_staleness_streak` (default 5) or more calls **in a row**.

This is a repeated-*selection*-count definition, not a wall-clock one — a candidate that has never
won, or that only ever wins every-other-tick, is never stale regardless of how much real time
passes. "Meaningful change" is defined structurally, not by inspecting world-state fields: **the
moment any other identity actually wins even once, the streak resets** — the previously-stale
identity is evaluated completely fresh the next time it resurfaces as the top scorer. No arbitrary
wall-clock expiry was introduced, matching the task's explicit constraint.

## 7. Safety analysis

- **Never fabricates**: `_select_staleness_aware_winner` only ever returns an element already
  present in `ranked` (`assert any(d.winner is c for c in cands)` — proven by
  `test_4_no_consequential_action_selected_outside_ranked_list`).
- **Never invents when no alternative exists**: proven by `test_d_no_alternative_system_does_not_invent_one`
  and Behavioral Scenario 2 — a single-candidate set keeps winning indefinitely, streak count
  climbing unboundedly, with no crash and no substitute.
- **No RED/YELLOW/FORBIDDEN action can be created**: R6 lives entirely inside
  `DecisionEngine.evaluate()`, upstream of every governance gate in `autonomous_loop.py`
  (ContinueGate, CounterfactualMemory veto, ThreatDetector, RED-tier red-team review, VectorCode
  gateway `classify()`, PermissionGateway). Whatever `decision.winner` ends up being — R6-suppressed
  or not — passes through the exact same downstream gates, unchanged code, unchanged order.
  `test_g_no_red_yellow_forbidden_action_created` and Behavioral Scenario 4 confirm the winner is
  always confined to the `action_type`s that were actually present in the input.
- **No governance bypass**: `test_6_governance_not_bypassed_r6_is_scoring_only` inspects the source
  of `_select_staleness_aware_winner` and asserts it contains no reference to
  `PermissionGateway`/`Governor`/`governor.dispatch` — it has no code path to them at all.
- **Instance-local, no cross-context leakage**: `test_2_staleness_state_does_not_leak_across_unrelated_situations`
  proves two independent `DecisionEngine` instances never share streak state.
- **Parameter-ordering-safe identity**: because identity is delegated unchanged to
  `PolicyMemory.make_situation_hash()` (which canonicalizes via `json.dumps(..., sort_keys=True)`),
  `{"a":1,"b":2}` and `{"b":2,"a":1}` hash identically — proven by `test_f_...` and
  `test_3_parameter_ordering_never_causes_false_alternative`.
- **Empty-candidate contract untouched**: `evaluate()`'s pre-existing `if not candidates:` noop
  fallback runs and returns *before* `_select_staleness_aware_winner` is ever called —
  `test_8_empty_candidate_set_unaffected_safe_fallback` confirms the exact prior contract.

## 8. Tests added

`tests/test_task91_r6_candidate_diversity.py` — 22 tests, all passing:

- `TestPreFixBehaviorBaseline` (1) — documents the exact pre-fix bug this task closes.
- `TestStalenessGuardCore` (9) — the task's lettered requirements A-H (plus one extended duplicate-
  identity case, D2).
- `TestBehavioralScenarios` (4) — the task's Scenarios 1-4 verbatim, using the real
  `DecisionEngine` + real `PolicyMemory.make_situation_hash`.
- `TestAdversarial` (7) — adversarial items 1, 2, 3, 4, 6, 7, 8 from the task (item 5, "an
  attacker/LLM can cause R6 to create or select a consequential action," is covered by the same
  assertion as item 4 — the winner is always `is` one of the input candidates — so no separate test
  was needed for it).
- `TestConfigDefault` (1) — confirms `CONFIG["candidate_staleness_streak"]` exists, is an `int`, and
  is bounded `[1, 1000]`.

All fixtures reuse the REAL `PolicyMemory.make_situation_hash` static method (pure, no DB access)
via `side_effect`, rather than the opaque `MagicMock` the pre-existing `tests/unit/test_decision_engine.py`
fixture uses for `_get_policy()` — that mock returns one indistinguishable child-Mock hash for every
input, which is fine for tests that never call `evaluate()` more than twice, but would silently
defeat any test asserting on *distinct* identities.

## 9. Behavioral verification

Ran directly against the real `DecisionEngine`/candidate-selection pipeline (only unrelated heavy
subsystems — episodic memory store, goal system, epistemic tracker, reasoning bank, neural trainer,
metacognition — stubbed, exactly matching this repo's own existing `test_decision_engine.py` fixture
pattern; no live/experiment database touched):

- **Scenario 1** (A wins 5x, becomes stale, safe B exists → A suppressed, B wins): confirmed exactly
  at the 6th consecutive call.
- **Scenario 2** (A stale, no safe alternative → system does not invent B): confirmed across
  `THRESHOLD + 5` consecutive calls with a single-candidate set — A wins every time, no crash, no
  fabricated action.
- **Scenario 3** (situation changes meaningfully → A eligible again): confirmed — after B wins once
  (breaking A's streak), A wins again on the very next call once it is top-ranked and no longer
  matches the current streak identity.
- **Scenario 4** (no RED/YELLOW/FORBIDDEN action manufactured): confirmed across `THRESHOLD + 1`
  consecutive calls — winner is always confined to `{"wire_transfer", "noop"}`, the two real inputs.

## 10. Adversarial verification

All 7 applicable adversarial items from the task (see §7 for citations) were directly tested and
passed:
1. Staleness cannot suppress every candidate (single-identity set always still wins). ✅
2. Staleness state does not leak across unrelated `DecisionEngine` instances. ✅
3. Parameter ordering cannot cause a false "distinct alternative." ✅
4. Candidate identity collisions (two objects, same canonical identity) do not count as
   alternatives to each other. ✅
5. *(covered by 4's own assertion — winner always `is` an input object.)*
6. R6 has no code path to Governor/PermissionGateway — cannot bypass governance. ✅
7. Staleness cannot be trivially reset without a genuinely different winner actually occurring
   (`test_7`). ✅
8. Empty candidate set still returns the pre-existing safe `noop` fallback, unaffected. ✅

No issue was found that required a fix.

## 11. Regression results

Ran against the full non-Ollama subset established as the authoritative baseline in Task 90
(5,061 tests: the same 7 real-Ollama-dependent files excluded for the same, previously root-caused
environment reason — `OLLAMA_MAX_LOADED_MODELS=1` / `OLLAMA_KEEP_ALIVE=2m` model-swap delays,
unrelated to this task and explicitly out of scope to fix here):

| Metric | Task 90 baseline | Task 91 (this run) |
|---|---|---|
| Collected | 5,061 | 5,092 (+22 — this task's own new R6 test file, +9 additional collection-count/skip variance unrelated to R6 — see below) |
| Passed | 5,012 | 5,042 |
| Failed | 13 | **13 — identical set, by exact test name** |
| Skipped | 36 | 37 |
| Errors | 0 | 0 |

**All 13 failures are the exact same tests, by full node ID, as Task 90's own classification table**
(`test_webauthn_middleware_integration.py::test_wrong_token_type_rejected_type_confusion`,
`test_correction_integration.py::test_full_loop_stores_and_retrieves`,
`test_correction_integration.py::test_lifecycle_unvalidated_to_validated`,
`test_epistemic_integration.py::test_different_domains_independent`,
`test_phase_a7_council_red_tier.py::test_proceed_high_confidence_returns_proceed`,
`test_openwa_absorption.py::test_exception_in_send_counted_as_failure` (Class C — the pre-existing
cross-test-pollution artifact, unchanged),
`test_permission_gateway.py::test_red_action_times_out_without_confirmation`,
`test_agent_registry_successor_class.py::test_dying_coding_swarm_respawns_...`,
`test_correction_learner.py::test_extract_from_explicit_correction`,
`test_correction_learner.py::test_tags_include_domain_and_source`,
`test_epistemic_scoring.py::test_stale_domain_reduces_score`,
`test_planning.py::test_circular_deps_flattened`,
`test_planning.py::test_decompose_returns_plan_or_none`) — **12×A (pre-existing) + 1×C (test
pollution), 0×B (caused by this work), exactly matching Task 90's classification.**

**Explicitly did not attempt to fix any of these 13** per the task's instruction — including
`test_epistemic_scoring.py::test_stale_domain_reduces_score`, which appeared in this run's isolated
sub-suite too (§ targeted-regression run below) and could easily be mistaken for an R6-caused
failure since it involves candidate scoring — it is not: it fails purely inside `_score_candidate()`'s
epistemic-dampening step (comparing `candidate.total_score` between a "fresh" and "stale" belief
before any winner is ever selected), a code path R6 never touches.

**+9 unexplained collection/skip delta** beyond this task's own +22 new tests: 30 more passed and 1
more skipped than 22+0 would predict. Investigated only to the extent of confirming it introduces
**zero new failures** and the new skip is not one of R6's own tests (all 22 R6 tests ran for real,
none skipped). Consistent with ordinary test-suite collection variance between two separate full-
suite invocations (parametrized fixtures, conditional skips based on transient local state such as
installed optional packages or file-system timing) rather than anything caused by this task's two-
file, additive-only diff — documented here rather than investigated further, per the task's explicit
instruction not to spend time chasing unrelated pre-existing/environmental variance.

**Targeted regression run** (before the full-suite run, for fast iteration):
`tests/unit/test_decision_engine.py`, `tests/test_decision_engine.py`,
`tests/test_policy_reward_identity.py`, `tests/test_counterfactual_block_penalizes_policy.py`,
`tests/test_task89c_goal_progress.py`, `tests/loop/test_fanout_cooldown.py`,
`tests/unit/test_governor_dispatch_thread_hop.py` — **73/73 passed.**
`tests/unit/test_permission_gateway_extra.py`, `tests/unit/test_epistemic_integration.py`,
`tests/unit/test_epistemic_scoring.py` — **1 failure, the pre-existing
`test_stale_domain_reduces_score` (Class A, identical to baseline).**

## 12. Before/after candidate-selection behavior

**Before:** `evaluate()` always returns `ranked[0]`. Given an unchanging candidate set, the winner
is identical on every call, forever, with no code path that could ever change that.

**After:** `evaluate()` returns `ranked[0]` for the first `candidate_staleness_streak` (default 5)
consecutive times it wins. On the next call after that, if `ranked[0]` is still the same identity
AND a distinct, already-scored alternative exists in the same candidate list, that alternative wins
instead. If the situation is genuinely single-option, or the winner naturally changes on its own,
behavior is unchanged from before.

## 13. Files changed

```
core/config.py                                    | 15 +++++++
core/loop/decision_engine.py                       | 76 +++++++++++++++++++--
tests/test_task91_r6_candidate_diversity.py         | new file (22 tests)
VECTOR_TECHNICAL_KNOWLEDGE/91_R6_CANDIDATE_DIVERSITY_REPORT.md | new file (this report)
```

No other file was touched. `git status --porcelain` before this task showed only the untracked Task
90 report (from the previous turn's Write, not yet committed) — that file is untouched by this task
and remains untracked, exactly as found.

## 14. Remaining limitations

- Staleness state is **process-local and not persisted** — a VECTOR restart clears every streak.
  This is a deliberate, documented choice (matching the precedent of Task 89B's fanout cooldown),
  not an oversight, but it does mean staleness suppression provides no protection against a stale
  candidate winning again immediately after a restart.
- The staleness definition only concerns the **`evaluate()`-level winner**, not candidates that
  score highly but never win, and not candidates the goal/plan layer never proposes at all — R6 has
  no visibility into, and makes no claim about, why a particular set of candidates was generated in
  the first place.
- With a genuinely single-candidate situation (or all remaining candidates sharing one identity),
  R6 provides no diversity at all — this is intentional (§7 safety analysis) but means R6 cannot
  help in VECTOR's most repetitive real scenario: a lone recurring goal action with no competing
  candidate ever proposed alongside it.
- The `+9` unexplained collection-count delta noted in §11 was not root-caused (out of scope,
  produced zero new failures).

## 15. Explicit statement of what R6 DOES NOT prove

R6 does **not** prove, and this report makes no claim, that VECTOR has:
- general candidate diversity (only staleness-triggered avoidance of an unchanged repeat);
- exploration (no randomness, no curiosity signal, no exploration/exploitation tradeoff — purely
  deterministic reuse of already-scored candidates);
- genuine multi-strategy reasoning (candidates are generated exactly as before — by
  `_TAG_TO_ACTION` and plan steps — R6 never generates a new strategy, only reorders selection among
  what already existed);
- L4 learning of any kind (the streak counter is not a learned signal — it is a bounded, hard-coded
  counter with a fixed threshold);
- Astra-level understanding or general intelligence, in any sense.

The only supported claim is the one stated in §1.

## 16. Recommended next task

Per Task 89/90/91's established sequencing, R6 was the last of the currently-authorized
remediations (R1-R6). No R7 is authorized by this task. Two natural, narrowly-scoped follow-ups are
visible from this session's own findings but are explicitly **not** being started:
1. The `+9` collection/skip delta noted in §11 (low priority — zero new failures, likely benign).
2. The 7 real-Ollama-dependent test files' timeout/marker treatment, proposed but not implemented in
   Task 90 §6.

---

## Git discipline

```
$ git status --porcelain
 M core/config.py
 M core/loop/decision_engine.py
?? VECTOR_TECHNICAL_KNOWLEDGE/90_AUTHORITATIVE_REPOSITORY_BASELINE.md   (pre-existing, from prior turn — untouched by this task)
?? VECTOR_TECHNICAL_KNOWLEDGE/91_R6_CANDIDATE_DIVERSITY_REPORT.md       (this report)
?? tests/test_task91_r6_candidate_diversity.py                          (new test file, this task)

$ git diff --stat
 core/config.py               | 15 +++++++
 core/loop/decision_engine.py | 76 +++++++++++++++++++++++++++++++++++++++++++-
 2 files changed, 90 insertions(+), 1 deletion(-)
```

No unrelated file was modified. Nothing was committed — awaiting explicit instruction. No worktree
was created. No merge/cherry-pick was performed.

---

## FINAL VERDICT

```
AUTHORITATIVE HEAD VERIFIED: PASS (b8d5b406b)
STALENESS DEFINITION: EXPLICIT AND DETERMINISTIC
UNCHANGED STALE CANDIDATES CAN BE SUPPRESSED: PASS
SAFE ALTERNATIVES REMAIN ELIGIBLE: PASS
NO UNSAFE ALTERNATIVES MANUFACTURED: PASS
NO RED/YELLOW/FORBIDDEN ACTION CREATED: PASS
NO GOVERNANCE/PERMISSION BYPASS: PASS
MEANINGFUL CONTEXT CHANGE RESETS STALENESS: PASS
FOCUSED TESTS: 22/22 PASS
BEHAVIORAL TESTS: 4/4 SCENARIOS PASS
ADVERSARIAL TESTS: 7/7 PASS
REGRESSION (FULL NON-OLLAMA SUITE): 5,042 passed / 13 failed (all pre-existing, 0 new) / 37 skipped / 0 errors
NEW REGRESSIONS: 0
WORKING TREE: 2 files modified (core/config.py, core/loop/decision_engine.py), 1 new test file, 1 new report — nothing committed
```

R6 ONLY. Do NOT proceed to R7. STOP.
