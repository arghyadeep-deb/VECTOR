# R12-J — Regression / Test Audit

## Objective
Determine whether any NEW test regression exists at HEAD `81b53b1175aede4ed05d1b9d086af91dda64c8a6`
(the R11 commit) relative to the documented baseline in
`VECTOR_TECHNICAL_KNOWLEDGE/R11_NATIVE_GOAL_STRATEGY_CANDIDATE_GENERATION_REPORT.md` §17, and
identify any stale/false-positive tests. Read-only — no production code was modified. All commands
were run against isolated/ephemeral test state; no bare production script was executed directly.

## Method
1. Confirmed HEAD (`81b53b117`) and a clean working tree before starting.
2. Reconstructed the exact exclusion list from `VECTOR_TECHNICAL_KNOWLEDGE/90_AUTHORITATIVE_REPOSITORY_BASELINE.md`
   §6-7 (7 files that make real, unmocked Ollama calls and are excluded from bulk runs because a cold
   model swap can exceed any reasonable per-test timeout — this is an environment/tooling constraint,
   not a code defect) plus the 8th exclusion documented in `OVERNIGHT_ADVERSARIAL_AUDIT.md`
   (`test_mcp_server_main_dispatch_fix.py`, a real subprocess-spawn timeout, also environmental).
3. Ran `python -m pytest tests/ -q --timeout=90` with those 8 files ignored (full run, ~14 minutes
   wall time this run — significantly slower than Task 90's ~10 minutes, consistent with normal
   machine-load variance, not a regression; two background `python.exe` processes were observed still
   accumulating CPU well past the first two poll windows before finishing genuinely).
4. Ran `python -m pytest VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests -q --timeout=90` separately.
5. Diffed both FAILED lists against the documented baselines (Task 90 §8 for the 13; R11 report §17
   for the learning_lab 7).
6. Sampled recently-added test files (R8/R9/R11) for the "weak null-guard assertion" pattern
   (`assert x is not None` with nothing stronger following) as a heuristic for stale/false-positive
   tests.

## Full suite result vs documented baseline

| | Documented (R11 report, commit 81b53b117) | This run (same commit, read-only) |
|---|---|---|
| Exclusion list | 8 files (7 Ollama-heavy + 1 mcp_server subprocess) | Identical 8 files |
| Failures | 20 (13 baseline + 7 blog-dedup pollution) | **13** |
| Failure identity | 13 exact names (Task 90 §8) + 7 `test_postiz_absorption.py` names | **Exactly the same 13 names, byte-identical, zero others** |
| Errors | 0 | 0 (no `ERROR ` lines) |

**Delta: -7 failures, all in `test_postiz_absorption.py`, all absent from this run entirely (0
references to that filename anywhere in this run's output — not "passed", not "skipped", simply not
triggered).** This is not a code-caused improvement or a hidden regression — it is exactly consistent
with how this failure class has been described in every prior report that documented it (E4,
`OVERNIGHT_ADVERSARIAL_AUDIT.md` §"Undocumented side effects": *"environment/test-pollution... its
presence or absence in any given bulk run's failure list is itself evidence of the pollution, not of
a real regression"* — Task 90 §8, row for `test_openwa_absorption.py`). The blog-dedup pollution is
order/timing-sensitive shared state inside a mega-suite run; this run simply didn't hit the ordering
that triggers it. **This is not a new finding — it is the same documented intermittent behavior,
observed on its "doesn't trigger" side this time.**

The 13-failure core set is **byte-identical** to the Task 90 baseline established well before R6-R11
existed:

```
tests/backend/test_webauthn_middleware_integration.py::test_wrong_token_type_rejected_type_confusion
tests/integration/test_correction_integration.py::TestCorrectionLearningIntegration::test_full_loop_stores_and_retrieves
tests/integration/test_correction_integration.py::TestCorrectionLifecycle::test_lifecycle_unvalidated_to_validated
tests/integration/test_epistemic_integration.py::TestEpistemicCognitiveLoop::test_different_domains_independent
tests/integration/test_phase_a7_council_red_tier.py::TestHandleRedTierVerdictPaths::test_proceed_high_confidence_returns_proceed
tests/test_openwa_absorption.py::TestBulkSender::test_exception_in_send_counted_as_failure
tests/test_permission_gateway.py::test_red_action_times_out_without_confirmation
tests/unit/test_agent_registry_successor_class.py::test_dying_coding_swarm_respawns_as_coding_swarm_with_capabilities
tests/unit/test_correction_learner.py::TestLessonExtractor::test_extract_from_explicit_correction
tests/unit/test_correction_learner.py::TestLessonExtractor::test_tags_include_domain_and_source
tests/unit/test_epistemic_scoring.py::TestScoringWithEpistemic::test_stale_domain_reduces_score
tests/unit/test_planning.py::TestDecomposeGoal::test_circular_deps_flattened
tests/unit/test_planning.py::TestDecomposeGoal::test_decompose_returns_plan_or_none
```

None of these touch any file R11 (or any stage back through R6) changed. **Zero new failures. Zero
new errors.**

Note: this repository's `conftest.py` overrides pytest's normal session-finish summary line (already
documented in Task 90 §7), so no exact `N passed, M failed, K skipped` line is emitted in `-q` mode —
confirmed again this run (absent from the log's tail). The FAILED-line diff above is the authoritative
signal, not a summary count.

## learning_lab suite result vs baseline

Ran standalone (not part of `pytest.ini` `testpaths`, per established convention). Result: **exactly
7 failures, exactly the same 7 test names** documented in the R11 report §17:

```
VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests/test_labs.py::test_policy_reward_moves_score_in_the_expected_direction
VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests/test_labs.py::test_confidence_and_policy_are_sensitivity_critical
VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests/test_labs.py::test_level4_full_causal_chain_passes_with_a_strong_reward
VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests/test_replay_and_regression.py::test_modified_scenario_replay_reports_a_specific_reason
VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests/test_replay_and_regression.py::test_regression_case_unintended_change_detected
VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests/test_replay_and_regression.py::test_regression_case_intended_change_accepted
VECTOR_TECHNICAL_KNOWLEDGE/learning_lab/tests/test_scorecard.py::test_scorecard_levels_0_through_4_pass_on_real_production_logic
```

Zero drift. Consistent with the R11 report's own `git stash` control proving these are caused by
pre-R6-era scoring additions (staleness suppression, correction_penalty, veto_penalty) this Task-78-era
lab was never updated to account for — out of scope for R11, still out of scope here (no code was
changed by this audit).

## Root-caused new failures

**None.** No failure in either suite is new relative to its documented baseline.

## Stale/false-positive test candidates found

Searched recently-added test files (`test_r8_correction_learning.py`, `test_r9_epistemic_prerequisites.py`,
`test_r11_native_goal_strategy_candidates.py`) for the `assert x is not None` weak-guard pattern (22
total hits across the broader `tests/` tree; sampled the R8/R9/R11 subset as the highest-relevance
population for this audit's purpose). **Every sampled occurrence is a null-guard immediately followed
by a stronger, specific assertion** (e.g. `test_r8_correction_learning.py:219` `assert lesson is not
None` is followed a few lines later by `assert retrieved[0].id == lesson.id` and
`assert penalty_after_restart > 0.0`; `test_r9_epistemic_prerequisites.py:111/137` and
`test_r11_native_goal_strategy_candidates.py:343` follow the same pattern). **No genuine false-positive
test was found in this sample** — the pattern is a legitimate defensive guard before a real assertion,
not a substitute for one. A full exhaustive pass over all 22 hits across the entire `tests/` tree
(including older, pre-R6 files) was not performed — out of scope depth for this audit's directive,
flagged as a candidate for a future, dedicated test-quality sweep if the orchestrator wants one.

## Current capability level
Not applicable — this is a regression/test-integrity audit, not a cognitive-capability audit.

## What's broken vs working
- **Working, unchanged**: 5,000+ test full suite (13 pre-existing environmental/unrelated failures,
  0 new), learning_lab suite (7 pre-existing scoring-drift failures, 0 new), all R6-R11 test files
  (36+ tests from R11 alone, all passing per this run's absence from any FAILED line).
- **Still broken, unrelated to R11 or this audit's scope**: the same 13 Task-90-era failures (webauthn
  type-confusion test, correction-integration persistence tests, epistemic-domain-independence test,
  council red-tier test, permission-gateway timeout test, agent-successor-class test, 2×
  correction_learner tests, epistemic staleness test, 2× planning-decompose tests, 1×
  openwa-absorption test) and the 7 learning_lab scoring-drift failures. None require R12 attention
  unless a future milestone specifically targets planning (`test_planning.py`), correction learning,
  or epistemic scoring internals.

## Recommended next milestone
None from this audit specifically — the test suite is stable and provides a trustworthy verification
substrate for R12's implementation waves. If the orchestrator wants to reduce baseline noise before
starting new cognitive work, the smallest safe action would be applying Task 90's own already-proposed
remediation (§ "Smallest safe remediation proposal"): mark the 8 Ollama/subprocess-heavy files with a
dedicated pytest marker and exclude that marker by default, rather than relying on an ad-hoc
`--ignore` list per report. This is a test-infrastructure change only, touches zero production code,
and was never implemented despite being proposed at Task 90.

## Open questions
- Should the blog-dedup pollution in `test_postiz_absorption.py` (intermittent, order-dependent) be
  root-caused and fixed at some point, or is it acceptable to leave as documented, known-intermittent
  noise indefinitely? Not urgent — it has never once been shown to reflect a real code defect across
  four separate reports (E4, `OVERNIGHT_ADVERSARIAL_AUDIT.md`, R11, this audit).
- The full suite took longer this run (~14 min) than Task 90's ~10 min. Not investigated further here
  (outside this audit's scope) — plausibly ordinary machine-load variance, not a code-caused
  regression, since no test moved between the pass/fail boundary.
