# R11 — Native Goal Strategy Candidate Generation

**Mission:** close the exact bottleneck E6 identified ("NATIVE CANDIDATE COMPETITION IS THE CURRENT
LEARNING BOTTLENECK") and prove, honestly, whether VECTOR's existing learning machinery can actually
use genuine native alternatives once they exist.

## 1. Executive summary

Production candidate generation was structurally capped at 2 content-blind, horizon-derived
`action_type`s (`GOAL_ACTION_MAP`), and the one piece of code that looked like it should provide
real content-driven diversity (`autonomous_loop.py`'s `_TAG_TO_ACTION` dict) was confirmed dead —
`generate_immediate_actions()` never propagated a goal's own `tags` field into its returned action
dicts, so the remap loop consuming it could never fire.

**Fix:** `GoalSystem.generate_immediate_actions()` now resolves each goal's own `tags` into one or
more known, already-permission-classified, already-Governor-routed `action_type` strategies. A goal
whose tags map to ≥2 distinct action_types now proposes that many distinct real candidates for the
same decision (e.g. `g_daily_commit`, tags `["git","habit","coding"]`, now proposes **both**
`git_status` GREEN and `code_task` RED). A goal whose tags map to nothing known falls back to the
original `GOAL_ACTION_MAP` horizon default, unchanged — a strict superset of the prior behavior,
never narrower.

**Result:** Level 3 (real candidates reach DecisionEngine and compete) and Level 4 (existing
PolicyMemory learning changes the winner, using **natively generated** candidates, across a genuine
restart) are both behaviorally proven — not merely at LAB scope with hand-built candidates, but with
candidates the real production `generate_immediate_actions()` path actually produces. No safety
boundary was touched. No new subsystem, database, or LLM call was introduced.

## 2. Starting HEAD

`ca682c79ed1eb5570f8dc1bf3bea16797c16ef48` (verified via `git status --short` / `git branch
--show-current` / `git rev-parse HEAD` before any edit — clean tree, correct branch, single
worktree matching HEAD).

## 3. Files inspected (Phase 0 audit, read-only)

`core/loop/decision_engine.py`, `core/loop/autonomous_loop.py` (`_think_tick`, `_act_on`,
`_get_plan_candidates`), `core/brain/goal_system.py`, `core/config.py`'s `PermissionConfig`,
`core/city/governor.py` (`DISTRICT_TASK_MAP`, `route_task`/`route_task_async`), `core/event_bus/wiring.py`,
`core/loop/permission_gateway.py`, all of this session's R6–E6 reports and test files, and — found
during the audit, not anticipated beforehand — `VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/` in full
(`twin.py`, `scenario.py`, `isolation.py`, `trace.py`, `level4_experiment.py`, `78_DIGITAL_TWIN_LAB.md`),
a pre-existing (Task 78, predates R6–E6), real, isolated Digital Twin Lab wiring genuine production
classes (`DecisionEngine`, `PolicyMemory`, `GoalSystem`, `EpistemicTracker`, `CounterfactualMemory`)
against isolated SQLite storage.

## 4. Existing architecture discovered

- `GOAL_ACTION_MAP` (`goal_system.py`): `{"SHORT": "research_topic", "MID": "analyze_progress",
  "LONG": "analyze_progress"}` — keyed only by horizon.
- `_TAG_TO_ACTION` (`autonomous_loop.py::_think_tick()`, pre-R11): 22 tag→action_type mappings,
  reading `a.get("tags", [])` from `generate_immediate_actions()`'s output — always `[]`, confirmed
  dead by direct source read (the returned dict literals list only `goal_id/title/action/action_type/
  urgency/source`, never `tags`).
- **All 22 `_TAG_TO_ACTION` target values were confirmed, before any change, to already be**: (a)
  classified in `CONFIG["permission"]`'s green/yellow/red lists (`check_attendance`, `git_status`,
  `daily_digest`, `search_arxiv`, `check_fatigue`, `consolidate`, `daily_review`, `code_review_vc`,
  `search_web` all GREEN; `monthly_report` YELLOW; `code_task` RED), and (b) exact-match-routed in
  `core/city/governor.py`'s `DISTRICT_TASK_MAP` to a real district (`coding`, `time_calendar`,
  `research`, `memory_curator`, `health`, `finance`, `reflection`). Moving this table does not invent
  a single new action type, permission tier, or execution path.
- **Notable, unanticipated finding**: `GOAL_ACTION_MAP`'s own default values (`research_topic`,
  `analyze_progress`) — TODAY's status-quo action types — are **not** exact-match keys in
  `DISTRICT_TASK_MAP` at all (confirmed by direct grep), meaning today's single-candidate baseline
  already silently falls through to `Governor._llm_classify()`'s LLM-based routing fallback on every
  real decision. By contrast, R11's tag-derived candidates all resolve via the fast, free, exact-match
  path — R11 **reduces** incidental LLM-call reliance relative to the status quo, not increases it
  (directly relevant to Principle E, "no unbounded LLM expansion").
- **`VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/`**: a real, pre-existing Digital Twin Lab (Task 78).
  Its `twin.py::auto_candidates_from_goals()` deliberately, faithfully reproduced the OLD dead
  `_TAG_TO_ACTION` lookup — reused for Phase 3/4 evidence, and updated to match the fix (§10).

## 5. Candidate-generation bottleneck (confirmed live, before any change)

Querying the real, live `GoalSystem` at the start of this task returned exactly **1** candidate,
`action_type="analyze_progress"` — nothing to compete against. Confirmed structurally: at most 2
distinct, content-blind action_types were ever possible from `GOAL_ACTION_MAP` alone.

## 6. Existing goal semantics

Every goal dict (`PRESEEDED_GOALS` and `GoalSystem.add_goal()`) already carries a `tags: list[str]`
field — free-text, uncontrolled, no schema validation. `g_daily_commit`'s real tags
(`["git","habit","coding"]`) are today's richest real case.

## 7. Existing action capabilities

Confirmed via `Governor.DISTRICT_TASK_MAP` + `CONFIG["permission"]` that all 22
`_TAG_TO_ACTION_TYPE` values are real, already-classified, already-routed action types spanning
GREEN (`git_status`, `check_attendance`, `search_web`, `search_arxiv`, `daily_digest`,
`check_fatigue`, `consolidate`, `daily_review`, `code_review_vc`), YELLOW (`monthly_report`), and RED
(`code_task`) tiers — genuine cross-tier diversity was already latent in this table, just unreachable.

## 8. Candidate-generation design decision

`generate_immediate_actions()` (in `goal_system.py`) now computes, per goal, the **distinct** set of
known action_types its tags map to (via a new `_tag_derived_action_types()` helper + relocated
`_TAG_TO_ACTION_TYPE` table), bounded to `_MAX_STRATEGIES_PER_GOAL = 3`, and emits one action dict
per distinct strategy. A goal with no known tags falls back to the original `GOAL_ACTION_MAP`
horizon default — unchanged.

## 9. Why this design was chosen (over the mission's own hypothesized alternative)

The mission's own Phase 1 hypothesis was "wire tags into the action dict, let `_think_tick`'s
existing remap loop consume them." This was explicitly tried in reasoning and **rejected**: that
loop's `for tag in tags: ... break` structurally caps output at **one** action_type per input dict —
it can only ever *replace* a value, never *propose several*. Genuine competition (≥2 real candidates
for one goal) requires collecting the **set** of distinct known types, which only makes sense as a
change to how many action dicts `generate_immediate_actions()` itself emits — squarely goal-content
semantics (RULE 6: "Planner reads this... Goals"), not orchestration. `autonomous_loop.py`'s
`_think_tick()` therefore needed only a small, mechanical simplification (its 1:1 dict→Candidate
loop no longer needs its own remap step, since each dict's `action_type` is already final) — not a
restructuring.

Two further, necessary consequences of this choice, both executed:
- The now-fully-superseded `_TAG_TO_ACTION` dict + remap loop was **removed** from
  `autonomous_loop.py` (not just left dead a second time) — this is the exact code E6 diagnosed as
  the bottleneck's own evidence; leaving two divergent, permanently-dead copies of the same table
  (one in `goal_system.py`, now live; one in `autonomous_loop.py`, now doubly dead) would be a
  maintainability landmine, not "no unrelated cleanup" — it is the direct, minimal, mission-relevant
  removal of the exact code this task's own audit centered on.
- `VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/twin.py::auto_candidates_from_goals()` — which exists
  specifically to *faithfully reproduce real production behavior*, dead code included, per its own
  documented design philosophy — was updated to match, since leaving it reproducing REMOVED dead code
  would silently make the lab lie about current reality (§10).

## 10. Files changed

| File | Change |
|---|---|
| `core/brain/goal_system.py` | New `_TAG_TO_ACTION_TYPE` table (relocated, unchanged 22 entries), new `_MAX_STRATEGIES_PER_GOAL = 3`, new `_tag_derived_action_types()` helper, `generate_immediate_actions()` now emits one action dict per distinct tag-derived strategy (or the unchanged horizon fallback) |
| `core/loop/autonomous_loop.py` | `_think_tick()`'s now-fully-superseded `_TAG_TO_ACTION` dict + remap loop removed; the candidate-building loop is now a direct 1:1 `a["action_type"]` → `Candidate` translation |
| `VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/twin.py` | `auto_candidates_from_goals()` updated to match (removed its own mirrored dead-code reproduction; module docstring/comments updated with forward pointers to this report — **not** a rewrite of Task 78's own historical report, which is left untouched) |
| `tests/test_e6_native_candidate_competition.py` | Header note added pointing to this report; the ONE test whose assertion became false for a real structural reason (`test_think_tick_tag_to_action_dict_is_unreachable_dead_code`) replaced with its accurate successor proving the mapping is now genuinely reachable elsewhere; all 4 other tests (including the tags-empty fallback regression) left unmodified — they remain true |
| `tests/test_r11_native_goal_strategy_candidates.py` (new) | Edge cases A–T, behavioral proof, R6/R7 regression against native candidates, safety/adversarial |
| `tests/test_r11_learning_integration.py` (new) | Phase 4 flagship: real native candidates + real PolicyMemory + genuine restart + winner flip + controls |
| `tests/test_r11_end_to_end_trace.py` (new) | Phase 7: real goal → native candidates → real DecisionEngine → real `PermissionGateway.classify()` → RED authorization boundary genuinely stops execution |
| `VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests/test_r11_native_diversity.py` (new) | Second, independently-designed confirmation via the pre-existing Digital Twin Lab's own `auto_candidates_from_goals()` and `Scenario(candidates="auto")` path |

**Also fixed, disclosed transparently**: mid-audit, `python core/brain/goal_system.py` was run
directly (its own long-standing `if __name__ == "__main__":` self-test) without first checking that
it writes to the **real, live** goal store (it does — no `VECTOR_DB_PATH` isolation). This
unintentionally added one real extraneous goal ("Learn Bengali by August") and reset
`g_daily_commit`'s progress from 1.0 to 0.5 on the real goal store. Caught immediately, and reverted
via `GoalSystem`'s own real API (goal removed; `g_daily_commit.progress` restored to 1.0), confirmed
by re-reading the real goal list (10 goals, matching the pre-mistake count). Every check after this
point used isolated (`_persist = lambda: None` / `VECTOR_DB_PATH`-isolated) `GoalSystem` instances
exclusively. No experiment state, `.env`, or any other real setting was touched at any point.

## 11. Exact behavioral changes

`GoalSystem.generate_immediate_actions()`'s return value: for a goal whose tags map to ≥2 distinct
known action_types, the method now returns that many action dicts (previously exactly one, derived
only from horizon). For a goal with no known tags, the return value is byte-identical to before.
`AutonomousLoop._think_tick()`'s candidate list: now can contain ≥2 candidates originating from a
single goal when that goal's tags warrant it (previously always exactly one candidate per goal).
Nothing about `_act_on()`, `Governor`, `PermissionGateway`, `CONFIG["permission"]`, or any reward/
policy-writing code path was touched.

## 12. Safety analysis

- **RED remains RED, YELLOW remains YELLOW, GREEN remains GREEN**: candidate generation only ever
  selects among already-classified `action_type` strings; classification itself
  (`CONFIG["permission"]`, `PermissionGateway.classify()`) is untouched code, confirmed by direct
  diff review and by `test_r11_end_to_end_trace.py`'s real `PermissionGateway()` instance classifying
  `git_status`→GREEN and `code_task`→RED exactly as before.
- **No authority escalation**: `_tag_derived_action_types()` and `generate_immediate_actions()`
  contain zero references to `Governor`, `PermissionGateway`, `update_from_outcome`, or
  `record_suppression` (verified by direct source-text tests, not just description).
- **No malicious-tag execution path**: the mapping table's *keys* are 22 fixed, benign,
  pre-vetted vocabulary words (`"git"`, `"coding"`, …) — never action_type strings themselves. A tag
  crafted to equal a real action_type name (e.g. a goal tagged `"execute_code"`) has **no effect**,
  because `"execute_code"` is not a *key* anywhere in the table — only ever a possible *value*
  reachable through one of the 22 real keys. Proven directly
  (`test_no_action_type_outside_the_fixed_known_table_or_goal_action_map_can_ever_be_proposed`).
- **Malformed/unknown/duplicate tags are all safe by construction**: non-string tags are filtered by
  an `isinstance` guard before any dict lookup (never a crash); unknown tags are a plain `.get()`
  miss; duplicates collapse via a dict-as-ordered-set. No try/except was needed anywhere.
- **Bounded**: `_MAX_STRATEGIES_PER_GOAL = 3` caps per-goal proposals; the caller's own pre-existing
  `limit` parameter remains the final total cap, confirmed even under an adversarial 50-goal ×
  3-strategies-each input.
- **Exactly one candidate still executes per decision**: R11 only affects what *competes*; DecisionEngine
  still selects exactly one winner per `evaluate()` call, exactly as before — more candidates does not
  mean more simultaneous executions, and therefore cannot amplify event-fanout beyond what R2's
  existing per-edge cooldown (Task 89B) already bounds.
- **R6 staleness is not defeated, and does not oscillate pathologically**: proven directly with
  natively generated candidates — a repeatedly-winning tag-derived candidate is still correctly
  suppressed in favor of the real, natively generated alternative, never a fabricated one.

## 13. Test matrix

| Edge case | Covered by |
|---|---|
| A. no tags | `test_a_goal_with_no_tags_falls_back_to_horizon_default` |
| B. one valid tag | `test_b_goal_with_one_valid_tag_produces_one_strategy` |
| C. multiple valid tags, distinct types | `test_c_goal_with_multiple_valid_tags_mapping_to_distinct_types` |
| D. duplicate tags | `test_d_duplicate_tags_collapse_to_one_candidate` |
| E. unknown tags | `test_e_unknown_tags_fall_back_safely` |
| F. malformed tags | `test_f_malformed_tags_do_not_crash_and_are_ignored` |
| G. unrelated tags | `test_g_unrelated_tags_fall_back_safely` |
| H. mixed valid+invalid | `test_h_mixed_valid_and_invalid_tags_only_valid_ones_count` |
| I. tags → RED action | `test_i_tags_mapping_to_a_red_action_still_classified_red` |
| J. tags → YELLOW action | `test_j_tags_mapping_to_a_yellow_action_still_classified_yellow` |
| K. only one applicable | `test_k_goal_where_only_one_candidate_is_genuinely_applicable` |
| L. multiple applicable | `test_l_goal_where_multiple_candidates_are_genuinely_applicable` |
| M. duplicate semantic candidates | `test_m_duplicate_semantic_candidates_collapse` |
| N. missing parameters | `test_n_every_candidate_has_valid_required_parameters` |
| O. invalid/incomplete goal dict | `test_o_goal_missing_optional_fields_does_not_crash` |
| P/Q. real production goal objects | `test_p_real_preseeded_goals_produce_expected_native_diversity`, `test_q_generation_uses_the_real_goal_object_shape_not_a_reimplementation` |
| R. repeated evaluation determinism | `test_r_same_goal_context_evaluated_repeatedly_is_deterministic` |
| S. R6 staleness | `TestR6R7StillWork.test_r6_staleness_suppresses_a_natively_generated_repeat_winner` |
| T. R7 provenance | `TestR6R7StillWork.test_r7_provenance_assigned_to_natively_generated_candidates` |

Plus: bounded-strategies-per-goal, no-Governor/PermissionGateway-reference, malicious-tag-cannot-
execute, action-type-allowlist-exhaustive-proof, candidate-count-cannot-explode-across-many-goals,
no-reward-API-reference — **29/29 pass** (`tests/test_r11_native_goal_strategy_candidates.py`).

## 14. Behavioral proof (Phase 3)

Real goal → real `generate_immediate_actions()` → **2 real, natively generated** `Candidate` objects
(`git_status`, `code_task`, never hand-constructed after generation) → real `DecisionEngine.evaluate()`
→ a genuine winner, confirmed to be one of the exact input objects (`any(decision.winner is c for c in
candidates)`). Same-goal/different-score/different-winner demonstrated: with tag order
`["coding","git"]` and a uniform policy score, natively generated `code_task` wins the near-tie
(listed first); with `code_task`'s own real situation_hash given a poor score, the SAME two natively
generated candidates flip to `git_status` winning. **2/2 tests pass.**

Independently confirmed via the pre-existing Digital Twin Lab's own separate harness
(`auto_candidates_from_goals()` and `Scenario(candidates="auto")`, real isolated `DecisionEngine`):
`{"git_status", "code_task"}` produced natively for `g_daily_commit`'s real tags, both as a direct
adapter call and through the lab's full `Scenario → DigitalTwin → DecisionTrace` path. **2/2 tests
pass.**

## 15. Learning integration proof (Phase 4) — the flagship result

`tests/test_r11_learning_integration.py`, standalone (real `VECTOR_DB_PATH` isolation, matching E1/
R10's own established convention):

```
1. real goal (tags=["coding","git"]) -> real generate_immediate_actions() -> 2 native candidates
   (code_task, git_status) -- never hand-injected
2. real DecisionEngine.evaluate() -> baseline winner: code_task (near-tie, tag order)
   decision_id, candidate_ids recorded
3. real, legitimate PolicyMemory.update_from_outcome() x8, poor reward (0.02), for
   code_task's own real situation_hash
4. real restart: close_db_connection() + reopen against the SAME on-disk file
5. SAME goal, FRESHLY + natively regenerated (new GoalSystem, new DecisionEngine instance)
6. real DecisionEngine.evaluate() again -> winner: git_status

RESULT: WINNER FLIPPED (code_task -> git_status), using candidates the real production
candidate-generation path produced both times, across a genuine restart, with the exact
persisted score value verified to match (not just "some" change).
```

Controls: an **unrelated** goal's natively generated `code_task` candidate shows zero learned
influence from the probe goal's policy history (distinct `situation_hash`); a **no-learning control**
(identical restart mechanics, no `update_from_outcome()` call) does **not** flip the winner, ruling
out the restart mechanics themselves as a confound. R7 provenance re-confirmed: decision_id and both
candidate_ids are genuinely distinct across the restart boundary. **3/3 tests pass.**

## 16. Adversarial findings

All 20 items from the mission's Phase 5 checklist were addressed; no genuine defect was found
(nothing required fixing). Summary:

1–5, 16 (malicious/unknown tag → arbitrary execution, RED/YELLOW→GREEN, tag→shell execution, unknown
action_type reaching execution): **structurally impossible** — proven by
`test_candidate_generation_cannot_reach_arbitrary_execution_via_a_malicious_tag` and
`test_no_action_type_outside_the_fixed_known_table_or_goal_action_map_can_ever_be_proposed` — the
table's keys are a fixed 22-word vocabulary, never derived from tag content dynamically, and every
possible output value is a member of a small, pre-audited allowlist.
6–8 (Governor/PermissionGateway bypass, remote/cloud execution without authorization): no code path
exists — confirmed by source-text absence tests and by the real end-to-end trace test showing the
RED authorization boundary is genuinely reached and genuinely blocks.
9–10 (candidate explosion, duplicate amplification): bounded by `_MAX_STRATEGIES_PER_GOAL` and the
pre-existing `limit` parameter; duplicates collapse to one entry by construction.
11–12 (stale tags causing repeated harm, unintended action cycles): no new repetition mechanism was
added; R6's existing staleness suppression governs repeat-winner behavior exactly as before,
re-verified against native candidates.
13 (event fanout amplification): impossible in principle — exactly one candidate still executes per
decision regardless of how many compete (§12).
14–15 (learning escalating authority / suppressing safety): impossible — candidate generation has
zero reference to reward/policy/authority code (confirmed by direct grep of the diff).
17 (new subprocess path): none introduced — confirmed by direct grep of the diff for
subprocess/eval/exec/os.system/shell=True.
18 (invalid candidate crashing the loop): covered by edge cases F/O — no crash under any malformed
input tried.
19 (runaway LLM calls): the opposite is true — R11's action_types resolve via `Governor`'s fast
exact-match path, reducing reliance on `_llm_classify()`'s LLM fallback relative to today's
`GOAL_ACTION_MAP` defaults, which are NOT exact-match keys (§4).
20 (R6 staleness + new candidates → pathological oscillation): directly tested — a natively generated
pair suppresses and re-enables exactly as R6's own hand-built-candidate tests already proved, with
no different behavior for native origin.

## 17. Regression results

Targeted regression (all R6–E6 own test suites + `test_e6_native_candidate_competition.py` +
`test_task89c_goal_progress.py` + `decision_engine`/`policy`/`governor`/`permission_gateway` tests +
all new R11 files): **0 failures.**

Pre-existing Digital Twin Lab suite (`VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests`, 30 tests
including 2 new R11 confirmations): **7 failures, byte-identical set to the pre-R11 baseline**
(independently confirmed via a `git stash`/re-run control — the exact same 7 tests fail with
**zero** R11 changes applied, root-caused to R6/R8/E4's own scoring additions this pre-R6-session lab
was never updated to account for; unrelated to and unaffected by R11).

Full non-Ollama suite (same exclusion list as Task 90/R9/E4, now also excluding
`tests/test_mcp_server_main_dispatch_fix.py`, a genuine environment subprocess-timeout unrelated to
any file this task touched): **5,121 collected / 5,064 passed / 20 failed / 37 skipped / 0 errors.**
All 20 failures are the exact same set already fully documented and root-caused in this session's own
final adversarial audit (13 pre-existing baseline + 7 blog-dedup test-pollution) — **zero new
failures caused by R11**, classification: **A (13, pre-existing) + D (7, environment/test-pollution),
0×B**.

## 18. Remaining limitations

- Only the 22 pre-existing `_TAG_TO_ACTION_TYPE` tag-vocabulary words produce diversity; goals tagged
  with genuinely novel, unmapped vocabulary (e.g. `g_first_revenue`'s `["revenue","equation","wedge",
  "startups"]`) still fall back to the single horizon default — this is the correct, conservative
  behavior (Principle C: "only reuse a tag if its semantics are sufficiently trustworthy"), not a
  defect, but it does mean R11's benefit is currently concentrated on goals whose tags happen to
  overlap this specific vocabulary.
- `_MAX_STRATEGIES_PER_GOAL = 3` is a fixed constant, not owner-configurable via `CONFIG` — a
  deliberate minimal-change choice (Principle D forbids "new large framework"); if a future task needs
  this tunable, it belongs in `core/config.py`'s existing `CONFIG` dict pattern.
- The pre-existing Digital Twin Lab's own 7 pre-R11 failures (R6/R8/E4 scoring drift) remain unfixed
  — correctly out of scope for R11 (a different, already-identified gap from a prior session, not
  something this mission's audit found or was asked to fix).
- Plan-step candidates (`_get_plan_candidates()`) remain the other legitimate source of real
  diversity; still 0 active plans in the observed real system at the time of this audit — unchanged
  by R11, out of scope (Principle: "do not broaden the mission unnecessarily").

## 19. Level 0–6 classification

```
LEVEL 0 — no diversity:                    SUPERSEDED
LEVEL 1 — isolated-test-only diversity:    SUPERSEDED
LEVEL 2 — real goal objects, >=2 candidates:                    PASS
          (test_p_real_preseeded_goals_produce_expected_native_diversity,
           using the OWNER'S REAL g_daily_commit tags)
LEVEL 3 — real candidates reach DecisionEngine and compete correctly:    PASS
          (TestBehavioralProof, both tests; digital twin lab confirmation)
LEVEL 4 — existing learning evidence changes the winner using REAL
          generated candidates:                                          PASS
          (test_r11_learning_integration.py's flagship result, §15, with
           genuine restart + 2 confound controls)
LEVEL 5 — repeated production-like decisions show persistent adaptation:  NOT ATTEMPTED
          (would require observing VECTOR's live autonomous loop over multiple
           real cycles -- explicitly out of scope: "Do NOT launch VECTOR
           autonomously just for this task")
LEVEL 6 — adaptation transfers across related situations/strategies:      NOT ATTEMPTED
          (out of scope for this mission; E6's own report separately documented
           a PRE-EXISTING, unintentional-looking generalization channel via
           action_type domain-prefix bucketing in _epistemic_penalty(), unrelated
           to and unchanged by R11)
```

**Achieved: Level 4** — the mission's own stated "ideal" target, not merely the Level 3 minimum.

## 20. What is genuinely proven

- Real production `GoalSystem.generate_immediate_actions()` now naturally produces ≥2 distinct,
  legitimate `action_type` candidates for goals whose real tags warrant it — including the owner's
  own actual `g_daily_commit` goal, not a synthetic example.
- Those natively generated candidates genuinely compete inside the real, unmodified
  `DecisionEngine.evaluate()` — different real inputs produce different real winners.
- VECTOR's existing `PolicyMemory` learning mechanism, once given natively generated candidates
  instead of hand-built ones, genuinely and persistently changes which one wins — across a real
  restart, with confound controls ruling out the restart itself or an unrelated goal as the cause.
  This is the mission's own defined **Level 4**, reached honestly, with real production code at
  every step of the CANDIDATE side of the equation.
- RED/YELLOW/GREEN classification, Governor routing, and the PermissionGateway authorization boundary
  are all completely unaffected — proven both by source-text absence tests and by a genuine
  end-to-end trace showing the RED boundary is reached and does block.
- Zero new code-caused regressions across the full relevant test surface.

## 21. What is NOT proven, and must not be claimed

- **Not** Level 5 (persistent adaptation across repeated real production cycles) or Level 6
  (cross-situation generalization) — neither was attempted, per the mission's own explicit scope
  limits.
- **Not** a claim that VECTOR's real, currently-running autonomous loop has, in fact, already made a
  different real-world decision because of this change — that would require observing the live
  process, which this task correctly never did.
- **Not** a claim that every VECTOR goal now has genuine strategic diversity — only goals whose real
  tags intersect the 22-word trustworthy vocabulary do; most of today's real `PRESEEDED_GOALS` still
  fall back to the single horizon default (§18).
- **Not** Astra-level understanding, a world model, causal reasoning, or general intelligence in any
  sense — this task is exactly what it says: giving existing, narrow, deterministic goal-tag matching
  the ability to propose more than one already-known, already-classified action per goal.
- **Not** a claim that the Digital Twin Lab's own 7 pre-existing failures are resolved — they are
  explicitly out of scope and remain open.

## 22. Recommended next milestone

Per E6's own report and this task's own findings: the highest-leverage next step is expanding the
**source** of trustworthy tags/strategies beyond the current fixed 22-word vocabulary — either by
extending `_TAG_TO_ACTION_TYPE` with more real, already-vetted action_type mappings for the
currently-unmapped tag vocabulary already present on real goals (`"revenue"`, `"equation"`,
`"startups"`, `"portfolio"`, `"habit"`, `"academic"`, `"wedge"` — all real, currently-unmapped
`PRESEEDED_GOALS` tags), or by reactivating the `_get_plan_candidates()` source (0 active plans
today) as a second, complementary channel of genuine per-goal diversity. Either is a bounded,
architecture-preserving continuation of exactly this mission — not a new one.

---

## Final Audit Checklist

```
[x] Real goal semantics are used.
    -- _tag_derived_action_types() reads goal["tags"], the real, existing goal schema field.
[x] Candidate diversity is genuinely content-derived.
    -- test_p_real_preseeded_goals_produce_expected_native_diversity uses the owner's real
       g_daily_commit tags; test_c/l prove distinct tags -> distinct types.
[x] No random/artificial production exploration.
    -- Zero randomness anywhere in the diff; test_r proves full determinism across repeated calls.
[x] Existing action types are reused where possible.
    -- All 22 _TAG_TO_ACTION_TYPE values are pre-existing, already-classified, already-routed
       action_types; zero new ones introduced.
[x] Candidates have valid parameters.
    -- test_n; identical {"goal_id","title"} shape to the pre-R11 baseline for every action_type.
[x] Duplicate candidates are prevented.
    -- test_d, test_m (dict-as-ordered-set collapse).
[x] Unknown tags are safe.
    -- test_e, test_g.
[x] Malformed tags are safe.
    -- test_f (non-string/unhashable tags, no crash).
[x] RED remains RED.
    -- test_i; real PermissionGateway.classify("code_task") == "RED" in test_r11_end_to_end_trace.py.
[x] YELLOW remains YELLOW.
    -- test_j (monthly_report).
[x] FORBIDDEN remains FORBIDDEN.
    -- no _TAG_TO_ACTION_TYPE value is FORBIDDEN-tier; classification code itself untouched.
[x] DecisionEngine receives multiple real candidates.
    -- TestBehavioralProof, both tests.
[x] R6 still works.
    -- test_r6_staleness_suppresses_a_natively_generated_repeat_winner.
[x] R7 provenance still works.
    -- test_r7_provenance_assigned_to_natively_generated_candidates.
[x] Existing learning machinery still works.
    -- test_r11_learning_integration.py's full flagship result + 2 controls.
[x] At least one winner-flip uses REAL generated candidates.
    -- Same file -- code_task -> git_status, across a genuine restart.
[x] No new unauthorized side-effect path exists.
    -- Diff-grepped clean for subprocess/eval/exec/shell; source-text-proven no Governor/
       PermissionGateway reference.
[x] No new unbounded LLM loop exists.
    -- Zero new LLM calls; R11's action_types resolve via Governor's exact-match path, REDUCING
       reliance on the pre-existing _llm_classify() fallback relative to the status quo.
[x] No new database/memory subsystem was unnecessarily added.
    -- Zero new tables, zero new persistence mechanisms; only a dict relocation + a pure function.
[x] Full relevant regression passes.
    -- §17.
[x] No new code-caused regression remains.
    -- §17 -- every failure independently classified A (pre-existing) or D (environment), 0xB.
[x] Claims are limited to demonstrated evidence.
    -- §19-21.
```

---

## Git discipline

```
$ git status --short
 M VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/twin.py
 M core/brain/goal_system.py
 M core/loop/autonomous_loop.py
 M tests/test_e6_native_candidate_competition.py
?? VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests/test_r11_native_diversity.py
?? tests/test_r11_end_to_end_trace.py
?? tests/test_r11_learning_integration.py
?? tests/test_r11_native_goal_strategy_candidates.py

$ git diff --stat
 VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/twin.py |  68 ++++++-------
 core/brain/goal_system.py                       | 126 +++++++++++++++++++++---
 core/loop/autonomous_loop.py                    |  50 +++-------
 tests/test_e6_native_candidate_competition.py   |  41 ++++++--
 4 files changed, 195 insertions(+), 90 deletions(-)
```

No unrelated production file touched. No worktree created. No cherry-pick. No merge. No reset/rebase.
Implementation complete, behaviorally verified, adversarially reviewed, and regression-clean — commit
authorized below per the mission's own stated commit policy.

---

## FINAL RESPONSE TO OWNER

```
STATUS:
COMPLETE

HEAD:
(recorded after commit, below)

MILESTONE:
Level 4

WHAT CHANGED:
GoalSystem.generate_immediate_actions() now resolves each goal's own tags into 1+ real,
already-classified action_type strategies (relocated + fixed the previously dead
_TAG_TO_ACTION mapping); a goal whose tags map to >=2 distinct types now proposes that many
real candidates (e.g. g_daily_commit -> git_status GREEN + code_task RED). No-known-tags
goals fall back to the original GOAL_ACTION_MAP horizon default, unchanged. The now-fully-
superseded dead code was removed from autonomous_loop.py; the pre-existing Digital Twin Lab's
own faithful reproduction of that dead code was updated to match.

BEHAVIORAL PROOF:
Real goal -> real generate_immediate_actions() -> 2 real native candidates (never hand-
constructed after generation) -> real DecisionEngine.evaluate() -> genuine winner selection,
confirmed via both a direct tests/ harness and the pre-existing, independently-designed
Digital Twin Lab.

LEARNING PROOF:
Real native candidates + real PolicyMemory.update_from_outcome() + a genuine SQLite restart
(close+reopen) -> the winner flips (code_task -> git_status) using the SAME two natively
regenerated candidates -- with an unrelated-goal control and a no-learning-restart control
both ruling out confounds. This is Level 4, reached with real production candidate-generation
code, not hand-built LAB candidates.

SAFETY:
RED/YELLOW/GREEN classification, Governor, and PermissionGateway are byte-for-byte untouched.
A real end-to-end trace confirms a RED native candidate genuinely stops at the authorization
boundary before reaching the code-execution bridge. No malicious/malformed tag can produce an
action_type outside a small, fixed, pre-audited allowlist. All 20 adversarial checklist items
addressed; zero defects found requiring a fix.

REGRESSION:
Targeted R6-E6 + goal/decision-engine suites: 0 failures. Full non-Ollama suite: 5,121
collected / 5,064 passed / 20 failed (13 pre-existing baseline + 7 environment/test-pollution,
byte-identical to this session's own prior classification) / 37 skipped / 0 errors -- 0 new
code-caused regressions. Pre-existing Digital Twin Lab suite: 7 failures, confirmed via a
git-stash control to be byte-identical with and without R11 applied (unrelated, pre-existing
R6/R8/E4 scoring drift).

REMAINING LIMITATIONS:
Diversity is currently limited to the 22-word pre-existing trustworthy tag vocabulary; most
real PRESEEDED_GOALS (e.g. g_first_revenue's "revenue"/"equation"/"startups" tags) still fall
back to the single horizon default. 0 active plans remain the other unaddressed diversity
source. Level 5/6 not attempted, per explicit mission scope.

NEXT RECOMMENDED MILESTONE:
Extend _TAG_TO_ACTION_TYPE to cover more of the real, already-present goal tag vocabulary
(revenue/equation/startups/portfolio/habit/academic/wedge), or reactivate the
_get_plan_candidates() plan-step diversity source -- both are bounded, architecture-preserving
continuations of this exact mission, not a new one.
```
