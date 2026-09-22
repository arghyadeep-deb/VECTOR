# VECTOR V1 Stage 5 — Restart / Persistence / Coherence

Date: 2026-09-22. Branch `vector-integration`, HEAD `e175152df5` (unchanged
— no new production code needed; see §1).

**VERDICT: STAGE_5_PASS.**

## 1. Governance and scope

Design/investigation delegated to Codex (consult, read-only), verified by
Claude against the real code before use. Conclusion: no new production
code needed — real persistence and crash-recovery machinery already
exists and was never exercised end-to-end across an actual restart. Live
verification done directly by Claude (not a bridge package).

Codex's key discipline point, followed exactly: **do not merely prove a row
survives.** Every claim below proves reloaded state actually changes a
real, fresh computation (`generate_immediate_actions()`, `next_ready_steps()`,
`DecisionEngine._score_candidate()`), not just that `GoalSystem()`/
`PlanStore()`/`PolicyMemory()` can read back what they wrote.

## 2. Design — a genuine restart, not a same-process reread

Two **separate OS processes** (`python -u rgd_stage5_restart.py phase1 ...`
then a second, independent `python -u ... phase2 ...` invocation), sharing
only the on-disk isolated `VECTOR_DB_PATH` SQLite file and `PlanStore` JSON
path — nothing carried over in memory. This is what makes it an actual
restart simulation rather than a same-process persistence check.

**Phase 1 (seed, then process exits):**
- A fresh, isolated `GoalSystem` (trimmed of `PRESEEDED_GOALS` noise, same
  practice as Stages 3-4) with one `SHORT` goal, tag `["git"]`, progress
  set to `0.4` via the real `update_goal_progress()`.
- Plan A: `s1` already `completed`, `s2` (`recent_commits`, GREEN-tier) left
  at `status="running"` — simulating a crash mid-step.
- Plan B: a single step (`push_github`, **not** GREEN-tier, no declared
  fallback) also left at `status="running"` — simulating a crash on a
  side-effecting action.
- `PolicyMemory.update_from_outcome("git_status", <real canonical hash>, 0.95)`
  for a specific, real `(action_type, params)` pair.

**Phase 2 (genuine restart — fresh interpreter, fresh objects):**

| Claim | Real result |
|---|---|
| Goal reloads with correct progress/status | `status="active"`, `progress=0.4` — exact |
| Reloaded goal **coherently affects a fresh computation**, not just a value read-back | `generate_immediate_actions()` — real method, unmodified — proposed `git_status` for this exact goal (`tags=["git"]` → `git_status` via the real `_tag_derived_action_types()` mapping) |
| GREEN step interrupted mid-run recovers safely | `PlanStore(path=...)`'s real `_ensure_loaded()` → real `_recover_stale_running_steps()` fired automatically on first load. `s2.status` → `"planned"`, `retry_info["recovery_decision"]=="reset_to_planned"`, exactly one real `step_recovered` event, and `plan.next_ready_steps()` correctly returns `["s2"]` — the work is not lost, and is ready to be picked up by the normal decision cycle (which will re-apply the permission gate on its own next attempt) |
| Non-GREEN step interrupted mid-run is **not** auto-resumed | `s1.status` → `"failed"`, `actual_outcome["status"]=="interrupted"` (an honest admission it doesn't know whether the real side effect already happened), `retry_info["recovery_decision"]=="marked_failed_not_auto_resumed"`, `plan.review_required is True` |
| **No unsafe/duplicate side effect** | `plan.next_ready_steps()` for Plan B returns `[]` — the interrupted `push_github` step is never offered again for re-execution. This is the actual proof requested: after a crash, VECTOR cannot know whether `push_github` already ran for real, so it must not — and does not — silently retry it. |
| Learned policy state survives restart AND changes real scoring | Fresh `DecisionEngine()._score_candidate()` on a candidate matching the seeded `(git_status, {"repo":"VECTOR","stage":"stage5_restart_policy"})`: `policy_score=0.95`, `total_score=0.3944`. A control candidate with the same action but different params (never seeded): `policy_score=0.5` (default), `total_score=0.3332`. The restart-surviving learned score measurably changes a fresh decision, not just a fresh read. |

All values above are copied verbatim from the real run's printed evidence
JSON, not summarized from memory.

## 3. Why this is a clean PASS, not PARTIAL

Every sub-claim in the directive's checklist has direct, unmocked,
cross-process evidence:

- **Goals**: reloaded correctly, and the reload demonstrably changes what
  the goal system proposes next.
- **Plans**: reloaded correctly; a GREEN interruption self-heals; a
  non-GREEN interruption is honestly quarantined, never silently replayed.
- **Learning/policy state**: reloaded correctly and demonstrably changes a
  fresh `DecisionEngine` computation, not merely readable.
- **Outcome evidence**: the `actual_outcome`/`retry_info` fields on the
  recovered steps are real, structured, and honest about uncertainty
  (`"a real-world side effect may already have occurred"`), not a fabricated
  success or a silent void.
- **Pending/recoverable work**: Plan A's `s2` is concretely, correctly
  recoverable (`next_ready_steps()` proves it, not just a status string).
- **Owner/background coherence**: `generate_immediate_actions()` — the same
  real surface a live autonomous tick reads from — reflects the restart
  state correctly.
- **No unsafe/duplicate side effects**: proven the way Codex recommended —
  by checking that the recovery bookkeeping never re-offers the interrupted
  non-GREEN action, rather than by actually re-triggering a real external
  side effect twice (which would be irresponsible to test for real).

## 4. Provider usage this stage

Codex: investigation/design consult only (correctly concluded no new code
was needed, and specified exact real field names/methods that all matched
on inspection — no rework needed this time). Claude: live-verification
scripting (two-process design), execution, this report. No bridge program
was needed or run.

---

**STAGE_5_PASS.** Continuing to Stage 6 (JWT/authorization security
closure) per the owner's standing instruction — but Stage 6 carries an
explicit owner-approval gate (this project's own `POLICY.md` §14 and the
original V1 directive both require it). Preparing the bounded proposal now;
will stop and report `V1_OWNER_APPROVAL_REQUIRED` before implementing
anything, per the one planned interruption before Stage 7.
