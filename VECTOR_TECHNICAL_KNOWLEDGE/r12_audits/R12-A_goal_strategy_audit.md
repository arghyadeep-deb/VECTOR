# R12-A — Goal / Strategy Audit

**Read-only. No production code, database, or goal store was modified.**
**HEAD audited:** `81b53b1175aede4ed05d1b9d086af91dda64c8a6` (verified via `git rev-parse HEAD`, clean tree)

## Objective

Determine what legitimate goal→strategy candidate diversity exists in production RIGHT NOW
(not what R11's report claimed at the time), and identify the smallest safe next step, if any.

## Method

Direct source read of `core/brain/goal_system.py` (full file, 436 lines) and
`core/loop/autonomous_loop.py`'s `_think_tick()` (lines 894-936) and plan-integration block
(lines 1508-1574). Cross-referenced every real `PRESEEDED_GOALS` tag against
`_TAG_TO_ACTION_TYPE`'s keys by hand. Located `PlanStore`/`get_plan_store()` in
`core/runtime/plans.py` and traced its persistence path (`core/runtime_paths.py::data_path()`)
to confirm plan state without importing any module or touching the real SQLite/episodic store.
**Did not run `python core/brain/goal_system.py`** — its own `__main__` block (lines 419-436)
calls `gs.update_goal_progress(...)` and `gs.add_goal(...)` against the REAL production goal
store with no isolation (this is the exact mechanism that caused an accidental production
mutation during R11 — see that report's Errors section — and remains unfixed at this HEAD;
flagged here as a standing hazard for any future agent, not something this audit touched).

## Findings

### 1. `generate_immediate_actions()` (goal_system.py:287-336) — confirmed as R11 left it

Two loops:
- **SHORT-goal loop** (307-319): every active SHORT goal, regardless of progress, emits one
  action dict per `_tag_derived_action_types(goal["tags"])` entry (or the `GOAL_ACTION_MAP["SHORT"]`
  fallback `research_topic` if none match).
- **MID/LONG "unstarter" loop** (321-334): only fires when `goal.get("progress", 0) == 0.0 and
  goal["horizon"] in ("LONG", "MID")`. **A MID/LONG goal with progress > 0 never produces an
  action dict through this path at all** — not narrowed, not degraded, simply absent. This is
  unchanged pre-R11 behavior, not something R11 introduced, but it is a real, currently-active
  gap: any MID/LONG goal that has ever received a single progress update above 0.0 permanently
  stops generating goal-loop candidates until/unless progress resets to exactly 0.0.

### 2. Coverage table — real `PRESEEDED_GOALS` tags vs. `_TAG_TO_ACTION_TYPE` (goal_system.py:47-56, 100-165)

| Goal id | Horizon | Progress | Tags | Known tags → types | Distinct types produced | Candidates? |
|---|---|---|---|---|---|---|
| `g_kiit_attendance` | LONG | 0.0 | kiit, academic | kiit→check_attendance; academic→∅ | {check_attendance} | 1 (single-strategy) |
| `g_karpathy_30` | MID | 0.0 | learning, ml, karpathy | learning→search_arxiv; ml→search_arxiv; karpathy→search_arxiv | {search_arxiv} | 1 (all 3 tags collapse to the SAME type — no real diversity) |
| `g_vector_phase1` | MID | **0.25** | vector, coding, build | vector→∅; coding→code_task; build→code_task | {code_task} | **0 — excluded entirely** (progress > 0.0, MID/LONG unstarter loop never runs, and it's not SHORT) |
| `g_placement_prep` | LONG | 0.0 | placement, dsa, interview | placement→search_web; dsa→search_web; interview→search_web | {search_web} | 1 (all 3 tags collapse) |
| `g_daily_commit` | SHORT | 0.0 | git, habit, coding | git→git_status; habit→∅; coding→code_task | **{git_status, code_task}** | **2 — genuine competition** |
| `g_first_revenue` | MID | 0.0 | revenue, equation, wedge, startups | all 4 → ∅ | {} → falls back to `analyze_progress` | 1 (horizon default) |
| `g_equation_portfolio` | LONG | 0.0 | equation, portfolio, startups | all 3 → ∅ | {} → falls back to `analyze_progress` | 1 (horizon default) |

**Bottom line: of the 7 real seeded goals, exactly ONE (`g_daily_commit`) produces genuine
multi-candidate competition right now.** Three goals (`g_karpathy_30`, `g_placement_prep`, and
`g_kiit_attendance`) have multiple known tags but they all alias to the *same* action_type, so
R11's mechanism is present but inert for them — this is not a bug (the tags genuinely all mean
"go read/search"), but it means R11's real-world diversity yield in the current seed set is much
narrower than "22 mapped tags" suggests. Two goals (`g_first_revenue`, `g_equation_portfolio`,
also the two highest-priority MID/LONG goals under The Equation) have zero tag coverage and fall
back to the pre-R11 default. One goal (`g_vector_phase1`) is silently excluded from the entire
mechanism by the pre-existing progress>0 gate, unrelated to R11.

### 3. Plan-derived candidates — ALREADY WIRED, contrary to the R11 report's framing

`autonomous_loop.py::_think_tick()` line 930 calls `self._get_plan_candidates()` and **extends**
the goal-derived `candidates` list with its result (line 932) before the single
`self._get_decision().evaluate(candidates)` call at line 949 — both sources compete in the SAME
decision, not a separate path. `_get_plan_candidates()` (lines 1517-1541) is a real, complete
implementation: iterates `plan_store.active_plans()`, takes up to 2 `next_ready_steps()` per
plan, and builds a real `Candidate` with `source=f"plan:{plan.id}:{step.id}"`, a real
`estimated_cost_inr`, and a +0.05 urgency bonus. The winning path (`_act_on_plan_step()`,
lines 1543+) routes execution through `PlanRunner.execute_step()`, which itself wraps
`AutonomousExecutor` around `permission_gateway` — same governance boundary as everything else.

**This directly corrects the R11 report's Section 18/22, which described plan candidates as an
"unaddressed diversity source" needing reactivation.** The wiring is not missing — what's
missing is any actual plan data. Confirmed via direct filesystem read (no import): `data/plans/`
does not exist at all in the production data root (`core/runtime_paths.py::get_data_root()` →
`<repo>/data`), meaning `PlanStore._ensure_loaded()` finds no file and `active_plans()`
unconditionally returns `[]`. Zero plans, zero plan candidates, but the CODE PATH is real and
already reachable — no new integration work is needed, only plan data.

### 4. Why zero plans exist — architectural, not incidental

`GoalSystem._decompose_to_plan()` (goal_system.py:392-403) is only ever invoked from inside
`add_goal()` (lines 380-388), gated on `horizon.upper() in ("MID", "LONG")` AND a currently
running asyncio event loop (`asyncio.get_running_loop()`; on `RuntimeError` it silently comments
"plan will be created on next think tick" but **no code anywhere in `autonomous_loop.py`
actually retries or reconciles goals-without-plans** — confirmed via grep, zero matches for
`decompose_goal_to_plan`/`_decompose_to_plan`/`plans_for_goal` outside `goal_system.py` itself).
Critically, **`PRESEEDED_GOALS` are loaded directly into `self._goals` by `_load_or_seed()` /
`_merge_new_seeds()` (lines 187-214), never through `add_goal()`** — so none of the 7 real
seeded goals, including the 3 MID/LONG ones eligible by horizon, have ever been capable of
triggering plan decomposition through this path. Zero plans is not "hasn't happened yet"; it is
the necessary and unavoidable consequence of how the seed goals are loaded.

## Current capability level (this session's L0-L6 ladder)

Tag-derived native candidate diversity: **L4** (per R11's own report — real production
candidates, real DecisionEngine, real PolicyMemory learning across a restart, winner flip —
re-verification of that specific claim was out of this audit's read-only scope, but nothing
found here contradicts it). Scope of that L4 proof, however, is effectively **one real goal**
(`g_daily_commit`) — the other 6 do not currently exercise genuine candidate competition.

Plan-derived candidate diversity: code is **IMPLEMENTED** and **INTEGRATED** and
**RUNTIME_REACHABLE** (wired into the live `_think_tick()`/`_act_on()` path with a real
governance-respecting execution route) but is at **L0** in practice — no plan has ever existed
in the production data root, so this path has never fired outside of whatever isolated tests
exercise `core/runtime/plans.py` directly. Not TEST_VERIFIED at the integration level either —
did not find (and did not search exhaustively for, given read-only/audit-scope limits) a test
that drives a real goal → real `add_goal()` inside a running loop → real plan → real
`_get_plan_candidates()` → real decision, end to end.

## What's broken vs. working

**Working:** R11's tag-derivation mechanism itself is sound and exactly as documented. Plan
candidate wiring in `_think_tick()`/`_act_on_plan_step()` is real, complete, and already governed
by the same permission boundary.

**Not broken, but narrower than assumed:** R11's real-world yield is 1-of-7 goals, not "up to
3 strategies per goal across the board" — the other goals either alias-collapse or have zero tag
coverage.

**Genuinely missing:** (a) a path for `PRESEEDED_GOALS` (or any goal added outside a running
event loop) to ever get plan-decomposed, and (b) any reconciliation for the `RuntimeError`
fallback case in `add_goal()` that the code comment claims will "self-heal on next think tick"
but does not.

## Recommended next milestone

Two independent, small, safe candidates — NOT recommending both be done in the same milestone:

1. **Extend `_TAG_TO_ACTION_TYPE` coverage for `g_first_revenue`/`g_equation_portfolio`** — these
   are the two highest-priority Equation goals and currently get zero benefit from R11. Requires
   deciding what real action_type(s) legitimately apply to "revenue"/"equation"/"wedge"/"startups"/
   "portfolio" tags — this needs a real architectural judgment call (e.g. does `search_web` or a
   startups-district action type apply?), not a mechanical tag copy.
2. **Give `_decompose_to_plan()` (or an equivalent reconciliation tick) a path to reach seeded
   goals** — smallest safe version: on a MID/LONG goal with progress 0.0 and zero plans
   (`plan_store.plans_for_goal(goal_id) == []`), let `_think_tick()` itself trigger decomposition
   once, inside its own already-running event loop, rather than only at `add_goal()` time. This
   would make the ALREADY-WIRED plan-candidate path exercise for the first time in production
   without touching `DecisionEngine`, `PolicyMemory`, `Governor`, or `PermissionGateway` at all.

Both are out of this audit's scope to implement (read-only).

## Open questions for the orchestrator

- Is extending tag coverage for Equation goals in scope for R13, or does "revenue/wedge/startups"
  require a genuinely new action_type (which Section 7 of the mission says must STOP and escalate
  for separate architectural review) rather than reuse of an existing one?
- Should plan reconciliation (finding #4) be its own milestone (candidate: fits R17's "plan-derived
  strategy diversity" mandate) rather than bundled into R13's tag-coverage work — they touch
  different files (`goal_system.py` tag table vs. either `goal_system.py::add_goal` or
  `autonomous_loop.py::_think_tick`) and have independent risk profiles.
- The `g_vector_phase1` progress>0 exclusion is pre-existing (not R11-caused) but blocks VECTOR's
  own highest-priority MID goal from ever generating a candidate through the goal loop — worth
  flagging to R12 synthesis even though it's outside R11's original scope.
