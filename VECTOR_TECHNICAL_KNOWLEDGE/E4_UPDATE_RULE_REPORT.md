# E4 — Update Rule

**Starting HEAD:** `728fcec80701e2f0a1162a09d7d68562f91a6846` (the E3 checkpoint). Clean tree,
confirmed before starting.

## Question

Does repeated experience produce meaningful, predictable future preference changes? Classify the
current update rule: FUNCTIONAL / INERT / PATHOLOGICAL / UNSTABLE / UNSAFE.

## Method

Direct audit of `PolicyMemory`'s full read/write surface (`update_from_outcome`, `get_score`,
`record_suppression`, the `veto_count` column added in Task 89/D3), cross-checked for what
`DecisionEngine._score_candidate()` actually consumes, following the exact same reader/writer
consistency method R9/E2 already used successfully twice this session.

## Findings

### `avg_reward`'s online average: FUNCTIONAL, with a documented (not fixed) saturation property

E1 (this session) already behaviorally proved the mechanism works: a real, persistent,
restart-surviving preference change from repeated experience. E4 adds one further honest
characterization: `new_avg = (old_avg*n + reward)/(n+1)` has **no decay and no cap on
`sample_count`**, so a single new observation's marginal influence shrinks as `1/(n+1)`. After 200
prior samples, the theoretically maximum-possible new observation (0.0 after a run of 0.9s) can only
move the average by `0.9/201 ≈ 0.0045` — quantified exactly, not estimated. This is a real, bounded,
mathematically predictable property of an unweighted running mean applied to what may be a
non-stationary real-world signal (an action's true quality can genuinely change over time, and this
mechanism adapts to that more and more slowly as history accumulates) — **not** instability
(the math is exact and bounded) and **not** pathological (it never runs away or oscillates). **No fix
was implemented** — introducing decay or a sliding window would be replacing a working algorithm with
a theoretically-different one, which E4 explicitly forbids absent evidence of an actual defect; none
was found. **Classification: FUNCTIONAL**, with the saturation property now precisely quantified and
tested rather than merely assumed.

### `veto_count`: found INERT, minimally wired

`record_suppression()` (Task 89/D3) increments `veto_count` on every counterfactual veto — but
repo-wide audit confirmed **nothing ever read it**: `PolicyMemory.get_score()`'s own SQL query
selects only `avg_reward, sample_count`. A situation vetoed 100 times in a row scored identically to
one never vetoed at all, as far as `DecisionEngine`'s ranking was concerned. Crucially, this was not
an oversight discovered for the first time tonight — `record_suppression()`'s own docstring, written
during Task 89, already stated the intent: *"so decision_engine's get_score() / future tooling can
see... how often has this exact canonical situation been suppressed."* That intent was never
completed. **Classification (pre-fix): INERT.**

## Implementation

Minimal, reusing the existing column exactly as its own docstring already intended:

1. `PolicyMemory.get_veto_count(action_type, situation_hash) -> int` (new) — a plain, read-only
   `SELECT veto_count FROM policy_memory WHERE ...`, returning `0` for no data, mirroring
   `get_score()`'s own structure and never-raises contract exactly.
2. `DecisionEngine._veto_penalty(situation_hash, candidate) -> float` (new) — bounded `[0.0, 0.10]`,
   `min(0.10, veto_count * 0.02)`, gated by a soft `CONFIG.get("veto_scoring", True)` kill-switch
   (same undeclared-flag pattern as `epistemic_scoring`/`correction_scoring`). Wired into
   `_score_candidate()`'s formula alongside `bias_penalty`/`correction_penalty`, with a matching
   `reasoning_chain`/`reasoning_steps` entry when nonzero.

Deliberately a **soft, bounded nudge, not a hard block** — `CounterfactualMemory.should_avoid()`'s
Jaccard-similarity check remains the actual hard-avoidance mechanism (it can outright block
execution); this only makes an already-frequently-vetoed situation's *ranking* slightly less
favorable, capped so it can shift a close decision but never dominate the 5-factor formula alone.
Nothing in either new method references `Governor`/`PermissionGateway` (proven by source-text test,
not description), and neither `avg_reward`, `sample_count`, nor `update_from_outcome()`'s signature
was touched.

## Tests

`tests/test_e4_update_rule.py` — **12 tests, all passing**:

- `TestVetoCountWasInertNowWired` (7 tests) — the pre-fix inertness proven directly from
  `get_score()`'s actual SQL query text; `get_veto_count()` reads back real recorded suppressions
  correctly; a **behavioral** proof that a repeatedly-vetoed candidate now scores measurably worse
  than an identical never-vetoed one; the penalty is bounded even under an extreme veto_count (500);
  an unrelated situation is provably unaffected; no Governor/PermissionGateway reference exists in
  the new code; and `update_from_outcome()`'s signature and `get_veto_count()`'s own query are proven
  to never touch `avg_reward`/`sample_count`.
- `TestAvgRewardSaturationDocumented` (2 tests) — the saturation property is **quantified exactly**
  (a real 200-sample history, then one maximally-opposite new observation, shift measured against
  the closed-form `1/(n+1)` prediction to within `0.005`) and a source check confirms no decay
  mechanism was added.
- `TestVetoControls` (3 tests) — positive (zero vetoes, zero penalty), negative (penalty grows
  predictably and linearly with veto count, `n*0.02` up to the cap), and duplicate (two real,
  separately-recorded veto events simply both count — no special-case amplification logic exists or
  is needed, since each `record_suppression()` call already represents one real occurrence).

## Regression comparison

Targeted regression (`tests/test_e4_update_rule.py` + E1-E3's own suites + R6-R9's own suites +
`tests/unit/test_decision_engine.py` + `tests/test_decision_engine.py` + `tests/test_policy_reward_identity.py`
+ `tests/test_counterfactual_block_penalizes_policy.py`): **0 failures.**

## Full non-Ollama suite — one further environmental finding

The full run showed **20 failures**: the 13 byte-identical baseline ones, plus **7 new** in
`tests/test_postiz_absorption.py` (`TestBlogPublisherDevTo`/`Hashnode`/`Medium`). Re-run in true
isolation, all 7 **still fail** — but root-caused directly to `districts/content/blog_publisher.py`'s
own `_check_blog_dedup()`: a real, intentional 24-hour dedup window backed by a `blog_dedup` table in
the SAME shared production `episodic_memory` database every other stage tonight has also been
writing to (`_blog_dedup_hash(platform, title)` → `sha256`). This session has run the full test suite
an unusually large number of times in rapid succession tonight (R6 through E4); the affected tests use
fixed, non-unique titles ("Title", "My Title"), so after enough repetitions within the same 24-hour
window, the dedup check correctly (by its own design) suppresses the "publish" call before the mocked
HTTP request ever fires — which is exactly the observed symptom (`captured["json"]` never populated,
`r.url` empty). **`districts/content/blog_publisher.py` is not touched by, or related to, E4's
`core/memory/policy.py`/`core/loop/decision_engine.py` changes in any way.** Classification:
**ENVIRONMENT / TEST-POLLUTION**, the same category (and now the same root mechanism — a real,
working, time-windowed production safety feature colliding with non-unique test fixtures under an
unusually high same-day rerun count) as the `test_task89c_goal_progress.py`/`test_trust_ladder.py`
findings in R9. Not fixed (out of scope, unrelated subsystem); flagged here in full for the pipeline's
own FINAL ADVERSARIAL AUDIT, since this is now the third distinct subsystem (Ollama model-swap
timing, shared goal/trust-ladder state, and now blog-dedup state) to exhibit this same underlying
"very high full-suite rerun frequency in one session" symptom tonight.

## Explicit non-claims

This does not claim VECTOR now "learns to avoid bad situations" in any general sense — the veto
penalty is a narrow, bounded, exact-match nudge on top of a scoring formula that itself has no
bearing on permission classification. It does not claim the saturation property was "fixed" — it was
quantified and left exactly as it was, because no defect was demonstrated, only a known mathematical
property of the chosen (and functioning) algorithm.

## Final verdict

```
STARTING HEAD: 728fcec80701e2f0a1162a09d7d68562f91a6846
CLASSIFICATION: avg_reward online-average update rule = FUNCTIONAL (saturation property quantified,
                 not fixed -- no defect demonstrated); veto_count = INERT before this stage, now
                 minimally wired
IMPLEMENTATION: 2 new methods (PolicyMemory.get_veto_count, DecisionEngine._veto_penalty), reusing
                 the existing veto_count column exactly as its own original docstring intended.
                 No reward value, aggregation formula, or existing method signature changed.
NEW TESTS: 12/12 PASS, including a real behavioral proof (repeatedly-vetoed candidate scores worse)
           and an exact quantification of the saturation property
FULL NON-OLLAMA SUITE: 5,081 collected / 5,024 passed / 20 failed (13 byte-identical baseline + 7
                        confirmed environment/test-pollution in tests/test_postiz_absorption.py,
                        root-caused to a real 24h blog-dedup window in the shared production DB,
                        unrelated to and unaffected by this stage's code) / 37 skipped / 0 errors
NEW REGRESSIONS: 0 (all 7 "new" failures independently reproduced in isolation and root-caused to an
                    unrelated subsystem's own real, working dedup feature colliding with tonight's
                    unusually high full-suite rerun count -- not code defects)
VERDICT: E4 COMPLETE
```

**FINAL HEAD:** recorded after commit, below.
