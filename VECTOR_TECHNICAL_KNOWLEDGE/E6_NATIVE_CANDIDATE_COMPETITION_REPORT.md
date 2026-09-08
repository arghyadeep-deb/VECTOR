# E6 — Native Candidate Competition (THE FINAL LEARNING GATE)

**Starting HEAD:** `a9004d87860d6ffbf7dd63d9852a2d71b3bff591` (the E5 checkpoint). Clean tree,
confirmed before starting. **No production code was modified in this stage** — this task's own
instructions explicitly require the audit to run to completion, unmodified, before any implementation
is even considered, and the audit result below means no implementation was authorized.

## Question

Can VECTOR's REAL candidate-generation pipeline naturally produce at least TWO meaningfully different
action types for the same decision context? This determines whether the R1–E5 correction/epistemic/
persistence/attribution/update-rule/contradiction machinery this whole overnight pipeline built and
verified has anything real to act on in production, or whether it is exercising a decision loop that
never actually has a genuine choice to make.

## Method

Traced `context → goals → candidate generation → candidate list → scoring → winner` directly against
the REAL, currently-running production code and the REAL current goal/plan state — not a simulation,
not an assumption from reading code alone. Two live queries were run read-only against the actual
production stores (confirmed zero writes, verified before/after goal count unchanged at 10).

## Findings

### 1. `GoalSystem.generate_immediate_actions()` — action_type keyed by horizon, never by content

```python
GOAL_ACTION_MAP: dict[str, str] = {
    "SHORT": "research_topic",
    "MID":   "analyze_progress",
    "LONG":  "analyze_progress",
}
```
Every SHORT-horizon active goal — regardless of whether it's "check KIIT attendance," "commit code,"
or "read an arxiv paper" — produces the literal same `action_type="research_topic"`. Every stalled
MID or LONG goal produces `"analyze_progress"` — MID and LONG even collapse to the identical string.
**At most 2 distinct action_types are structurally possible from this source, ever, and neither one
depends on what the goal is actually about.** Proven directly (`test_goal_action_map_has_at_most_two_distinct_values`,
`test_all_short_horizon_actions_share_the_identical_action_type` — 3 goals with completely unrelated
content, real `generate_immediate_actions()` call, all three collapse to `"research_topic"`).

### 2. `autonomous_loop._think_tick()`'s `_TAG_TO_ACTION` dict — confirmed DEAD CODE

A 14-entry mapping (`kiit→check_attendance`, `git→git_status`, `coding→code_task`,
`ml→search_arxiv`, …) exists in `_think_tick()`, reading `tags = a.get("tags", [])` from each action
dict `generate_immediate_actions()` returns. **Those dicts never contain a `"tags"` key at all** —
confirmed directly against real production output (`tags: None` when accessed via `.get()`) and via
source inspection of `generate_immediate_actions()` itself (its returned dict literals list
`goal_id, title, action, action_type, urgency, source` — no `tags` field). The remapping loop
therefore can never fire; `action_type = a["action"]` (the `GOAL_ACTION_MAP` value) is what is always
actually used. This rich-looking dictionary — the ONE piece of code in the entire candidate-generation
path that looks like it should produce genuine content-driven diversity — has never once executed in
production.

### 3. `_get_plan_candidates()` — CAN produce genuine diversity, but is currently inactive

Each plan step carries its own real `action_type`, set at plan-decomposition time — this path is
structurally capable of real diversity. **Querying the real production `PlanStore` directly returned
0 active plans.** This source currently contributes nothing to any real decision.

### 4. The real, live decision RIGHT NOW has exactly one candidate

`GoalSystem().generate_immediate_actions(limit=10)` against the actual current goal state returned
**exactly 1 action**, `action_type="analyze_progress"`. There is, at this literal moment, no SHORT-
horizon goal active alongside a stalled MID/LONG one — meaning even the weak, purely-horizon-derived
2-value "diversity" the architecture is theoretically capable of is not currently realized. A real
`evaluate()` call today has nothing to compete against.

## Conclusion

**NATIVE CANDIDATE COMPETITION DOES NOT EXIST.** This is not a matter of degree or a "weak but present"
signal — it is structurally absent for the one candidate source that is currently active, and the
apparatus that looks like it should provide content-driven diversity (`_TAG_TO_ACTION`) has never
executed. The theoretical ceiling of today's architecture (2 fixed, horizon-derived, content-blind
action_types) is not "genuine candidate diversity" in any sense that would let learning (R1–E5's own
mechanisms) express itself against real alternatives — and even that ceiling is not always reached in
practice.

Per this task's own explicit instruction, this is reported exactly as specified:

> **"NATIVE CANDIDATE COMPETITION IS THE CURRENT LEARNING BOTTLENECK."**

## What was NOT done (per explicit instruction)

- `GOAL_ACTION_MAP` was **not** expanded.
- `_TAG_TO_ACTION` was **not** wired up or made reachable.
- No new candidate generator, tag-routing mechanism, or content-classification logic was added.
- No production code was modified in this stage at all.

This is a direct consequence of the task's own decision tree: *"IF NATIVE COMPETITION DOES NOT
EXIST: DO NOT IMPLEMENT IT TONIGHT."* Implementing a fix here would mean either inventing new
content→action_type routing (explicitly forbidden: "DO NOT expand GOAL_ACTION_MAP," "DO NOT add
tag-based routing") or a new candidate-generation mechanism (explicitly forbidden: "NO FEATURE
CREEP... new candidate generation"). The correct action, per the task's own rules, is to report this
precisely and stop — which this report does.

## Tests

`tests/test_e6_native_candidate_competition.py` — **5 tests, all passing, zero production writes**
(before/after real goal count independently verified unchanged at 10):

- `TestNativeCandidateGenerationAudit` (4 tests) — direct proof of findings 1, 2, and the "3 unrelated
  goals collapse to 1 action_type" behavior, all against the real `GoalSystem`/`generate_immediate_actions()`
  code (goal state fully test-isolated: real `GoalSystem()` instance with `_persist` neutralized and
  `_goals` replaced by test-controlled fake entries, so the method under test runs for real while the
  live goal store is never touched).
- `TestLevelALabOnly` (1 test) — the LAB-level checkpoint: the real `DecisionEngine`, given two
  hand-constructed candidates (explicitly labeled LAB, never claimed as a production finding), still
  adapts correctly given real, persisted `PolicyMemory` learning — the same mechanism E1/R6/R7 already
  proved, restated here as this pipeline's final LAB-vs-NATIVE distinction, made explicit.

## LEVEL A vs LEVEL B (per the task's own anti-cheating framework)

**LEVEL A (LAB): ACHIEVED.** The real `DecisionEngine` can adapt when supplied two valid,
hand-constructed candidates — proven repeatedly across this session (R6, R7, E1, E4, and again here).

**LEVEL B (NATIVE): NOT ACHIEVED.** Real production candidate generation does not naturally produce
multiple action types for one decision context. **Only LEVEL A supports the strong claims this
session has made about persistent learning, correction influence, epistemic dampening, veto
penalties, and contradiction handling — every one of those was proven at LAB scope, using
hand-constructed candidates, and none of them has ever been shown to engage during a real,
unmodified production decision cycle**, because a real production decision cycle right now typically
has nothing to choose between.

## Explicit non-claims

This report does not claim:
- VECTOR has general candidate diversity, exploration, or multi-strategy reasoning;
- VECTOR has L4 adaptation or L5 generalization in production (only LAB-scope L3/L4, per E1's own
  explicit LAB-scoping);
- any of R6 through E5's mechanisms are currently influencing a real autonomous decision in a
  meaningful way, since those mechanisms only matter when a real ranking is contested by ≥2 real
  candidates, which does not currently happen.

## Recommendation for whoever picks this up next (not started tonight)

The single highest-leverage next architectural task, based on tonight's full R1–E6 audit, is:
**give `generate_immediate_actions()` (or a genuinely new candidate-generation stage) real,
content-derived action_type diversity** — e.g., actually populating the `tags` field its own output
already has a dead code path waiting for, sourced from each goal's own `tags` field (already present
on every goal dict, per `add_goal()`'s own schema — this data already exists, it is simply never
read at this step). This is squarely a NEW task, requiring its own audit, design, and explicit
authorization — not started here.

## Final verdict

```
STARTING HEAD: a9004d87860d6ffbf7dd63d9852a2d71b3bff591
NATIVE CANDIDATE COMPETITION: DOES NOT EXIST (confirmed against real running code + real current
                                goal/plan state, not simulated)
ROOT CAUSES: GOAL_ACTION_MAP keyed by horizon only (2-value ceiling); _TAG_TO_ACTION confirmed dead
             code (depends on a "tags" key generate_immediate_actions() never sets); 0 active plans
             (the one source capable of real diversity is currently inactive)
CURRENT REAL STATE: exactly 1 candidate generated by the live goal system right now
IMPLEMENTATION: none (explicitly required by the task's own decision tree)
LEVEL A (LAB): ACHIEVED, repeatedly, across this entire session
LEVEL B (NATIVE): NOT ACHIEVED
NEW TESTS: 5/5 PASS, zero writes to real production state (independently verified before/after)
VERDICT: "NATIVE CANDIDATE COMPETITION IS THE CURRENT LEARNING BOTTLENECK."
E6 COMPLETE. Do NOT implement candidate diversity tonight.
```

**FINAL HEAD:** recorded after commit, below.
