# Task 89C — Goal Progress Semantics (R3)

Agent C, Task 89 overnight remediation. Worktree: `.claude/worktrees/agent-aeaac40876e4adf1b`,
branch `worktree-agent-aeaac40876e4adf1b`, base commit `6b5fcf204`.

## Bug

`core/loop/autonomous_loop.py`'s "Goal feedback loop" block, inside `AutonomousLoop._act_on()`,
called `GoalSystem.update_goal_progress()` with a reward-scaled increment on **every** successful
action linked to a goal:

```python
_increment = round(0.10 * reward, 3)  # up to +0.10 per successful action
_new_progress = min(1.0, _goal.get("progress", 0.0) + _increment)
gs.update_goal_progress(_gid, _new_progress, note=...)
```

`GoalSystem.update_goal_progress()` (`core/brain/goal_system.py`) sets `goal["progress"]` and,
**unconditionally**, if `progress >= 1.0`, sets `goal["status"] = "completed"` — with no
completion-criterion check of any kind. `get_active_goals()` filters to `status == "active"`, and
there is no code path anywhere in the repo that reactivates a completed goal.

Combined, this meant a goal could be driven to permanent completion purely by accumulating
enough successful-action reward over time, with zero relationship to whether the goal's actual
objective had been achieved. This is exactly what happened in VECTOR's real persisted goal data:
`g_daily_commit` ("Commit code every single day — no exceptions") — a plainly recurring/habitual
goal that should never have a one-time "done" state — was auto-completed and permanently removed
from the active goal set this way.

## Fix (C1) — remove the mutation, not the semantics

Removed the `gs.update_goal_progress(...)` call site from the reward block. Nothing about
`update_goal_progress()` itself changed — its unconditional `progress >= 1.0 → status="completed"`
behavior is preserved exactly, because that is the correct, intentional behavior for an
**explicit** caller (human/API/self-test). What changed is that autonomous reward accumulation no
longer calls it. A single observability-only debug log line was kept, noting which goal_ids a
reward was associated with, without touching persistence.

### Before (removed)

`core/loop/autonomous_loop.py`, inside `_act_on()` (was lines 1122–1141 in this worktree before
the edit):

```python
                # Goal feedback loop: a successful action on a linked goal advances its progress.
                # Reward-scaled increment so high-reward outcomes move the goal more.
                if winner.goal_ids and completed >= 1.0:
                    try:
                        gs = self._get_goals()
                        _increment = round(0.10 * reward, 3)  # up to +0.10 per successful action
                        for _gid in winner.goal_ids:
                            _goal = next((g for g in gs.get_active_goals() if g["id"] == _gid), None)
                            if _goal is not None:
                                _new_progress = min(1.0, _goal.get("progress", 0.0) + _increment)
                                gs.update_goal_progress(
                                    _gid, _new_progress,
                                    note=f"+{_increment} from {winner.action_type} (reward={reward:.2f})",
                                )
                                logger.info(
                                    "[VECTOR][goal] '{}' progress {:.2f} → {:.2f} (+{} via {})",
                                    _gid, _goal.get("progress", 0.0), _new_progress, _increment, winner.action_type,
                                )
                    except Exception as _gp_err:
                        logger.warning("[VECTOR][goal] progress update suppressed: {}", _gp_err)
```

### After

Same location:

```python
                # Goal feedback loop: REMOVED 2026-09-08 (Task 89C — goal progress semantics).
                # This block used to call gs.update_goal_progress() with a reward-scaled
                # increment on every successful action linked to a goal. Because
                # update_goal_progress() unconditionally sets status="completed" once
                # progress >= 1.0 (with no completion-criterion check), pure reward
                # accumulation could — and did — silently auto-complete goals that were
                # never meant to have a one-time "done" state (e.g. a recurring/habitual
                # goal). See VECTOR_TECHNICAL_KNOWLEDGE/89C_GOAL_PROGRESS.md for the full
                # writeup. Progress is no longer mutated here; explicit callers (human/API)
                # still use update_goal_progress() exactly as before. We keep a
                # observability-only log noting which goals this reward was associated
                # with — no goal.progress mutation happens here anymore.
                if winner.goal_ids and completed >= 1.0:
                    logger.debug(
                        "[VECTOR][goal] reward={:.3f} associated with goal_ids={} via {} "
                        "(progress NOT updated — reward-driven goal completion removed, Task 89C)",
                        reward, winner.goal_ids, winner.action_type,
                    )
```

No new persistence, no new completion criteria, no new formula — the mutation is simply gone.

## The "plan-step equivalent" block — does not exist in this worktree

The task brief (based on prior research on a different branch/worktree) described a second,
near-identical reward-driven `update_goal_progress()` call near "plan-step reward handling"
around lines 1515–1520. I re-verified this myself with a repo-wide grep (scoped to this
worktree) for `update_goal_progress` before and after editing:

- **Before my edit**: exactly one call site in `autonomous_loop.py` — the "Goal feedback loop"
  block above (line 1132 in this worktree's pre-edit file).
- No occurrence of `plan.goal_id`, `plan_step`, or any second `0.10 * reward` pattern exists
  anywhere in this worktree's `core/loop/autonomous_loop.py`.

This worktree is a clean checkout of commit `6b5fcf204` on its own branch
(`worktree-agent-aeaac40876e4adf1b`) — confirmed via `git status`/`git log`. Other agents are
editing the fanout-handler and policy/reward-writing sections of the same file in their own
isolated worktrees per the task brief, so it's expected that different worktrees see different
line numbers and even different code present/absent for regions outside this task's scope. The
plan-step block the brief described is simply not present in the version of the file I was
handed. **Nothing was left un-fixed here** — I confirmed this by re-grepping (see C2 below)
rather than assuming the prompt's line numbers were accurate.

## C2 — repo-wide re-verification: is there any other autonomous path to `update_goal_progress`?

After the C1 edit, grepped this entire worktree for `update_goal_progress` and `complete_goal(`:

```
core\brain\goal_system.py:244:    def update_goal_progress(self, goal_id, progress, note="") -> bool:
core\brain\goal_system.py:287:    def complete_goal(self, goal_id: str) -> bool:
core\brain\goal_system.py:288:        return self.update_goal_progress(goal_id, 1.0)
core\brain\goal_system.py:306:    gs.update_goal_progress("g_daily_commit", 0.5, "committed today")   # __main__ self-test
core\loop\autonomous_loop.py:1123-1131                                                              # comments only, no live call
```

The only remaining call sites are: the method definition itself, its `complete_goal()` wrapper
(an explicit, deliberate one-shot completion helper — not called from anywhere in the autonomous
loop), and `goal_system.py`'s own `if __name__ == "__main__":` self-test. Also grepped for any
direct mutation of a goal's `progress` key (`goal["progress"] = ...` / `goal.progress = ...`)
repo-wide — the only hit inside `GoalSystem` itself is line 248, inside
`update_goal_progress()`. All other `.progress =` hits in the repo belong to unrelated classes
(`claims.py` claim progress, `missions.py` mission progress, `task_queue.py` task progress,
`openmythos/train.py` training-run progress) — none of them touch goal objects.

**Conclusion: C1 alone closes the autonomous path.** No further guard machinery was added or
needed — there is no other place in the codebase that can silently drive a goal's progress to
`>= 1.0` via reward.

## C7 — recurring/habit-goal mechanism search

Grepped `core/brain/` (case-insensitive) for `recurring` and `habit`:

- `goal_system.py:69` — `g_daily_commit`'s `tags` list includes the string `"habit"`. This is
  purely a descriptive tag; nothing in `GoalSystem` reads or special-cases it.
- `anticipation.py` — has "recurring event" detection, but this is about detecting recurring
  *behavioral/action patterns at the same hour of day* for anticipation/nudging, unrelated to
  goal lifecycle or reactivation.

**Confirmed: no recurring/habit-goal mechanism exists anywhere in the codebase.** Per the task
brief, none was built. `g_daily_commit` remains `status="completed"` as a frozen historical fact
(C3/C4). Recurring-goal semantics (e.g., a goal that resets to "active" on a cadence, or that
tracks a streak instead of a one-shot progress bar) remain a real, acknowledged, **unaddressed
gap** — a future task should design a proper recurring-goal type rather than reusing the
one-shot `progress`/`status` model for habitual goals.

## Files changed

| File | Change |
|---|---|
| `core/loop/autonomous_loop.py` | Removed the reward-derived `update_goal_progress()` call in the "Goal feedback loop" block inside `_act_on()` (was ~1122–1141). Replaced with a comment explaining the removal + a `logger.debug()` observability line. No other line in this file was touched — confirmed via `git diff --stat` (1 file changed, 17 insertions, 19 deletions, all within this one block). |
| `core/brain/goal_system.py` | **Not modified.** `update_goal_progress()`, `PRESEEDED_GOALS`, `GOAL_ACTION_MAP`, `get_active_goals()`, `generate_immediate_actions()` all byte-for-byte unchanged. |
| `tests/test_task89c_goal_progress.py` | New test file (see below). |
| `VECTOR_TECHNICAL_KNOWLEDGE/89C_GOAL_PROGRESS.md` | This document (new). |

`GOAL_ACTION_MAP` (C5) was never touched — verified by `git diff` showing zero changes to
`goal_system.py`.

## Tests

`tests/test_task89c_goal_progress.py` — real `GoalSystem` + real `AutonomousLoop`, backed by an
isolated temp-file SQLite DB (`VECTOR_DB_PATH` env override set before any VECTOR import, per
`.claude/rules/testing.md`: "SQLite episodic_memory — use a test DB, not mocks"). Only
`governor.dispatch` (real district execution), `policy` (PolicyMemory), and `memory.recall`/
`store_chain` are stubbed — none of those are what this task changed; stubbing them avoids
triggering real district dispatch, network calls, or Pushover notifications while still
exercising the real reward-computation and (former) goal-feedback code path in `_act_on()`.

Run in isolation (per the task brief — do not run the full suite):

```
python -m pytest tests/test_task89c_goal_progress.py -v
```

Result: **7 passed, 0 failed** (8.67s, Python 3.13.13, pytest 9.0.3).

| # | Test | Proves |
|---|---|---|
| 1 | `test_reward_does_not_mutate_linked_goal_progress` | A real successful-outcome reward run through `_act_on()` leaves `g_daily_commit`'s progress/status byte-identical before/after (C1). |
| 2 | `test_repeated_reward_never_completes_goal` | 50 repeated reward-processing cycles against `g_karpathy_30` never move progress off `0.0` or change status off `"active"` (C2). |
| 3 | `test_explicit_update_goal_progress_still_completes` | A direct, explicit `update_goal_progress(goal_id, 1.0, ...)` call still sets `status="completed"` — the pre-existing explicit mechanism is provably intact (C6). |
| 4 | `test_completed_goal_never_reactivated` | A goal explicitly completed, then subjected to 10 reward-processing cycles, stays `status="completed"`, `progress=1.0`, and is excluded from `get_active_goals()` (C4). |
| 5 | `test_goal_alignment_score_unchanged_by_reward` | `decision_engine.py`'s `_score_goal_alignment()` (unmodified, read-only) returns the identical score for `g_placement_prep` before and after 5 reward-processing cycles, since progress never moved. |
| 6 | `test_generate_immediate_actions_not_shrunk_by_reward_processing` | A fresh zero-progress MID-horizon goal that is unstarter-branch-eligible in `generate_immediate_actions()` remains eligible after one reward-processing cycle — no silent candidate-set regression. |
| 7 | `test_historical_goal_state_read_back_unchanged` | A goal's historical progress value (`0.076`, matching the exact number a `reward≈0.755` successful action would have produced under the old `0.10 * reward` formula) and a simulated pre-existing `g_daily_commit` completion both read back unchanged across a fresh `GoalSystem()` load — no migration, no rewrite (C3). |

Additional verification run:

```
python -c "import ast; ast.parse(open('core/loop/autonomous_loop.py', encoding='utf-8').read())"
```
→ `SYNTAX_OK` (no syntax errors introduced).

## What was intentionally NOT done

- No migration script — `g_daily_commit` and every other persisted goal's current
  `progress`/`status` are untouched by this change; they are read exactly as stored (C3).
- No reactivation logic anywhere (C4) — verified no code path sets `status` from `"completed"`
  back to `"active"`.
- No new completion criteria in `update_goal_progress()` (C6) — its signature and unconditional
  `progress >= 1.0 → completed` behavior for explicit callers is byte-for-byte unchanged.
- `GOAL_ACTION_MAP` (C5) — untouched.
- No recurring/habit-goal mechanism built (C7) — confirmed none exists; left as an open gap.
- No candidate-diversity fix, no goal-tag propagation, no `_TAG_TO_ACTION` change — all
  explicitly out of scope per the task brief and not touched.
- The full repository test suite was **not** run (per instructions — it is large and has a
  known pre-existing hang unrelated to this work). Only the tests directly relevant to this
  change were run, in isolation.

## Summary

The reward-driven goal-completion bug had exactly one live call site in this worktree's
`autonomous_loop.py` (the "Goal feedback loop" block in `_act_on()`); the "plan-step equivalent"
block described in the task brief does not exist in this worktree's version of the file (likely
present only in a different branch/worktree state — re-verified via repo-wide grep rather than
assumed). Removing that single call site, and re-confirming via a full repo-wide grep for
`update_goal_progress`/`complete_goal(`/direct `goal["progress"] =` mutations, closes the
autonomous path completely: the only remaining callers are the method's own definition, its
`complete_goal()` explicit wrapper, and `goal_system.py`'s own self-test. `update_goal_progress()`
itself is untouched — explicit callers (human, API, future deliberate automation) still get
correct unconditional completion semantics at `progress >= 1.0`. `g_daily_commit` remains
`completed` at `progress=1.0` as a frozen historical fact, per instructions, and no
recurring/habit-goal semantics were invented — that remains a real, acknowledged gap for a
future task. Seven new tests, all using a real `GoalSystem` against an isolated temp-file DB
(no mocking of goal_system.py or episodic storage), pass cleanly (7/7) and specifically prove:
no progress mutation from reward, no auto-completion under repeated reward, the explicit
completion mechanism is intact, no reactivation of completed goals, no drift in
`decision_engine.py`'s `goal_alignment` scoring, no silent shrinkage of
`generate_immediate_actions()`'s candidate output, and byte-identical historical-state readback.
