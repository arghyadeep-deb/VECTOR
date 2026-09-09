# R12-D — Planning Audit (read-only)

**HEAD audited:** `81b53b1175aede4ed05d1b9d086af91dda64c8a6` (verified clean, matches expected)

## Objective

Determine whether plan-derived candidate diversity (`_get_plan_candidates()`) is real, safe, and
currently reachable, or dead/inert machinery — and find the smallest defect (if any) blocking it.

## Method

Direct source inspection only. No production code modified. One read-only Python check of the real
persisted `data/plans/plans.json` (read, no write). No plan was created, no DB mutated.

## Findings

1. **`core/runtime/plans.py`** (1062 lines) is a real, substantial, DAG-based multi-step plan system:
   `PlanStep`/`PlanEvent`/`Plan` dataclasses with full JSON round-trip, `PlanStore` (atomic JSON-file
   persistence with Windows-safe tmp+rename, restart-crash recovery via `_recover_stale_running_steps()`
   which correctly gates auto-resume on the SAME GREEN/YELLOW/RED classification `permission_gateway.py`
   uses — no new safety taxonomy), `decompose_goal_to_plan()` (LLM-first via `MissionPlanAdvisor`, rule-based
   `ObjectiveDecomposer` fallback), `replan_plan()` (fallback-step strategy → LLM restructure, budget-capped
   at `MAX_REPLANS=2` → abandon), and `PlanRunner.execute_step()` (executes one step at a time through
   `AutonomousExecutor`, which itself goes through the permission gateway — confirmed no bypass).

2. **`_get_plan_candidates()`** — `core/loop/autonomous_loop.py:1517-1541`. Genuinely called from
   `_think_tick()` at line 930, wrapped in try/except (failures suppressed to a debug log, never crash the
   loop). It queries `plan_store.active_plans()` and, for each plan, `plan.next_ready_steps(limit=2)`
   (DAG-correct — only steps whose `depends_on` are all `"completed"`), turning each ready step into a real
   `Candidate` with `source=f"plan:{plan.id}:{step.id}"` and a +0.05 urgency "plan momentum" bonus. This is
   NOT a duplicate/parallel candidate path — the exact same `Candidate` dataclass, same `DecisionEngine`,
   same competition as goal-derived candidates (confirmed: `candidates.extend(plan_candidates)` at line
   932, both lists feed the same `evaluate()` call at line 949).

3. **Dispatch on win is real**: `_act_on()` checks `winner.source.startswith("plan:")` at line 1043 and
   routes to `_act_on_plan_step()` (line 1543), which resolves the plan/step, calls
   `PlanRunner.execute_step()` (real gateway-gated execution), and writes a PolicyMemory reward using the
   SAME canonical `make_situation_hash()` identity as every other writer (this was itself a prior fix
   noted in the E2 outcome-attribution audit's own comment at plans.py area — re-confirmed still correct,
   not re-broken).

4. **`data/plans/plans.json` does not exist** — confirmed via a direct read-only check
   (`PlanStore().path.exists() == False`). Zero plans currently persisted in the real production state.
   This reproduces R11's own finding ("0 active plans") and confirms it is STILL true today, not stale.

5. **Root cause of zero plans is NOT a bug in the plan machinery — it's an unreached trigger.**
   `decompose_goal_to_plan()` / `create_and_activate_plan()` are only ever invoked from
   `GoalSystem.add_goal()` (`core/brain/goal_system.py:380-388`), which fire-and-forgets
   `self._decompose_to_plan(goal_id, title)` via `asyncio.get_running_loop().create_task(...)` — but ONLY
   for MID/LONG horizon goals. Two structural facts prevent this from ever firing today:
   - **The 7 real `PRESEEDED_GOALS`** (including the two richest MID/LONG goals, `g_first_revenue` and
     `g_equation_portfolio`) are loaded directly into `self._goals` at `_load_or_seed()`
     (`goal_system.py:202`) — they bypass `add_goal()` entirely, so they were NEVER plan-decomposed, ever,
     including at first boot.
   - **The only production caller of `add_goal()` with a real horizon** is
     `core/api/routers/brain.py:63-73`'s `POST /goals/add` — an owner/API-triggered action, not anything
     the autonomous loop calls on its own. `grep` for `.add_goal(` repo-wide (excluding the unrelated
     `SEOPortfolio.add_goal()`, a different class in `core/seo/portfolio.py`) confirms this is the only
     real production call site; all other hits are tests, benchmarks, or the module's own `__main__`
     self-test (which itself accidentally mutated the real goal store once this session per R11's own
     disclosed incident — unrelated to this finding).

6. **Minor, non-blocking defect found**: `goal_system.py:387-388`'s `except RuntimeError: pass  # no
   running loop — plan will be created on next think tick` — this comment is FALSE. No code anywhere
   retries a dropped decomposition on a later think tick; if `add_goal()` is ever called from a sync
   context with no running loop, that MID/LONG goal silently never gets a plan, permanently, with a
   misleading comment claiming otherwise. **Currently inert in practice**: the only production caller
   (`brain.py`'s `async def add_goal`) always has a running loop, so this defect has never actually fired
   in production. Classification: P4 (stale/misleading comment), not P0-P2 — does not block anything
   today, but should be fixed or the comment corrected if this module is touched again.

## Current capability level (L0–L6)

- **Plan machinery itself (decompose → persist → compete → execute → learn):** mechanically complete,
  IMPLEMENTED + INTEGRATED + RUNTIME_REACHABLE — the code path from a plan step candidate through
  DecisionEngine competition through gateway-gated execution through PolicyMemory reward is real and wired,
  matching the exact rigor R11 established for goal-derived candidates. Not separately BEHAVIORALLY_VERIFIED
  in THIS audit (no plan was created or executed here — read-only scope) — `tests/unit/test_planning.py`
  and `tests/integration/test_planning_integration.py` exist and should be the source of any existing
  behavioral proof; not read in depth here (out of this audit's scope, flagged for R12 synthesis).
- **Plan-derived candidate diversity in the real running system today: L0.** Zero plans exist in
  production. `_get_plan_candidates()` is reachable and correct but currently always returns `[]` because
  nothing has ever created a plan — not because of a defect in the candidate-generation or competition
  path, but because the ONE trigger (`add_goal()` for a MID/LONG goal) has never fired for any of the 7
  real preseeded goals and is only owner-reachable via an API call for a NEW goal.

## What's broken vs working

**Working (do not touch without cause):**
- DAG resolution, circular-dep flattening, crash recovery, replanning strategy chain, atomic persistence.
- `_get_plan_candidates()` → `Candidate` → `DecisionEngine.evaluate()` competition (same path as goals).
- `_act_on_plan_step()` → `PlanRunner.execute_step()` → `AutonomousExecutor` → permission gateway → reward.

**Broken/inert (candidates for R17, not this audit):**
- The 7 real `PRESEEDED_GOALS` (2 of which are MID/LONG and would be the natural first real plan subjects)
  never had `_decompose_to_plan()` called for them, because they were seeded, not `add_goal()`-ed.
- No autonomous code path (only an owner-facing API endpoint) ever calls `add_goal()` for a MID/LONG goal
  — so even for a brand-new goal, plan creation is owner-initiated, not something VECTOR does on its own
  in the autonomous loop today.
- Stale "next think tick" comment (P4, currently inert, see finding 6).

## Recommended next milestone (for orchestrator synthesis, not a commitment)

The smallest safe mutation that would make plan-derived diversity real without inventing new architecture:
decompose the 2 existing real MID/LONG `PRESEEDED_GOALS` (`g_first_revenue`, `g_equation_portfolio`) once,
using the EXISTING `decompose_goal_to_plan()` path, either via a one-time startup hook or an explicit
owner-triggered backfill — NOT a new plan-creation mechanism. This is R17's stated mandate
("If plan machinery is healthy: integrate minimally") — this audit's conclusion is that it IS healthy;
the gap is purely that the one existing trigger has never been pointed at the real preseeded goals.

## Open questions (for R12 synthesis / other auditors)

- Does `tests/integration/test_planning_integration.py` already behaviorally prove the
  decompose→compete→execute→reward chain end-to-end? (Not read in this audit — R12-J/regression auditor
  should confirm pass/fail status and whether it uses real or hand-built candidates.)
- Is `MissionPlanAdvisor`'s LLM decomposition call subject to the same per-cycle LLM-call caution the
  mission's absolute rules flag ("no unbounded LLM expansion")? It is called once per `add_goal()`, not
  per tick, so likely bounded — worth R12-G (runtime/liveness) confirming call frequency assumptions hold.
- Should seeding include an explicit one-time plan-backfill for the 2 real MID/LONG preseeded goals, or is
  that out of scope until R13/R17 formally authorizes it? Left to orchestrator synthesis.
