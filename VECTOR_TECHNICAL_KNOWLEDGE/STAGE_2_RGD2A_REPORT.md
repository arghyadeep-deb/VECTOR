# VECTOR V1 Stage 2 — RG-D2a: Honest Live Policy-Score Adaptation Gate

Date: 2026-09-22. Branch `vector-integration` (bridge packages) + a direct live
verification run from the `_integration` worktree (HEAD `3732975ea4`). Not yet
promoted to `production-hardening-complete` — that promotion is the owner's,
never automatic (see Safety, below).

**VERDICT: STAGE_2_PASS** (for the deliberately narrowed scope defined below —
see "Scope, and why it was narrowed" for what this does NOT claim).

## 1. Governance

Implementer/reviewer roles alternated through `tools/vector_dev_orchestrator`
(Claude and Codex, per `POLICY.md` — no self-certification). The live-gate
execution itself (starting/stopping the process, sending probes, injecting
feedback, reading the database) was performed directly by Claude, in the same
pattern as the three prior closure missions (Owner Routing Closure, V1 Trust,
PRE-RG-D2), because a live-process behavioral gate is not a bridge work
package. Before implementation began, Claude consulted Codex directly
(`/codex` consult mode) for an adversarial design review of the Stage 2 plan;
Codex disagreed with the original wider "RG-D2" framing and that disagreement
is the reason this gate is scoped the way it is.

## 2. Scope, and why it was narrowed

The owner-command path in `core/api/routers/commands.py` builds **exactly one
Candidate** per request before `DecisionEngine` scores it. There is no live
path today where VECTOR "picks a different strategy" after a failure — only a
path where a repeated identical request's `PolicyMemory` score can honestly
change. Full strategy-switching RG-D2 would need either a live owner path
producing multiple legitimate candidates, or an explicit adaptation
mechanism; neither exists, and this mission did not add one (out of scope,
per Codex's own recommendation).

This gate proves the narrower, honestly-named claim only:

> failure -> real outcome evidence -> `PolicyMemory.update_from_outcome()` ->
> a later `PolicyMemory.get_score()` read changes -> `DecisionEngine`'s
> `total_score` for the identical repeated request changes accordingly, in
> both directions (negative and positive).

This is a real instance of the directive's failure->learning->adaptation
chain, not a substitute for it. "RG-D2 meaningful" is not claimed to have
grown beyond the 2/4 Candidate/DecisionEngine reach established in
`PRE_RG_D2_FINAL_CLOSURE_REPORT.md` — that number is unchanged by this
mission.

## 3. Pre-gate fix (bridge program `prog-1fbdc181`, 3 packages, all accepted)

Before the gate could be run honestly, a real gap had to be closed: in
`core/api/routers/commands.py`'s `/command` handler,
`reward = 0.8 if (gateway_result.approved and not _is_not_implemented(gateway_result)) else 0.2`
treated any gateway-approved, non-`"not_implemented"`/`"rejected"` result as
a *success* reward — including a handler that ran but genuinely failed.
`_is_not_implemented()` only ever checked for `status in ("not_implemented",
"rejected")`, so a real failure would have been rewarded exactly like a real
success, which would poison any adaptation gate before it could produce
honest evidence.

| Package | What | State | Commit |
|---|---|---|---|
| `RGD2A-1-REWARD-HONESTY` | Real failure/no-data handler outcomes for `git_status`/`recent_commits` now earn reward=0.2, not 0.8 | accepted (1 correction cycle — targeted tests failed once, fixed, passed) | `e56a9e7d18` |
| `RGD2A-2-ADAPTATION-OBSERVABILITY` | `situation_hash` and `policy_score` added to the existing per-`/command` episodic record (no new side channel) | accepted | `359d3bff5f` |
| `RGD2A-3-PROBE-STABILITY-TESTS` | Deterministic tests proving `git_status`/`recent_commits` reach Candidate->DecisionEngine->PermissionGateway->real handler with a stable, reproducible `situation_hash` | accepted (1 correction cycle — Codex rejected the first attempt: "the test replaces ContextEngine with..."; interrupted mid-retry by an unrelated host memory-pressure kill, safely resumed, retried clean) | `3bfe97206e` |

All three: implementation + targeted pytest + independent cross-provider
review, merged onto `vector-integration` (HEAD `3732975ea4`). Program-level
usage: 3/4 packages, 10/30 provider calls, 2/4 correction cycles — well
within budget.

## 4. Live gate execution

Run from an isolated `_integration` git worktree (its own `vector_memory.db`,
never the owner's real production database) at `vector-integration` HEAD
`3732975ea4`, with the owner's `.env` temporarily copied in for realistic
provider routing and removed again immediately after. `python run_vector.py
api`, port 8000, same launch command as every prior closure mission.
Probe: `"What's the git status?"` — matches the existing deterministic
`_REGEX_PRECLASSIFY` pattern for `git_status` (`coding` district), so it
never depends on the LLM classifier or the embedding matcher, exactly the
"safe shape" Codex recommended (no risk of an `is_action=false` miss or a
PermissionGateway-vocabulary gap producing a false "execution failure").

**First attempt (self-caught error, kept here for honesty):** the situation
hash was initially computed independently as
`PolicyMemory.make_situation_hash("git_status", {})` = `v2:f5559a4fe8c3`,
assuming empty params. The real hash the server actually uses is
`v2:24417a9ec8a1` (read directly from the live episodic-memory record via
`RGD2A-2`'s new logging). Feedback sent to the guessed hash landed on a row
nothing ever reads — three probes in a row showed **zero** score movement in
either direction, which is exactly what a broken/misdirected gate looks like.
Caught by comparing the raw `policy_memory` row instead of trusting a flat
result. Re-run with the correct, actually-logged hash below.

**Corrected run — real result:**

| Step | Action | `winner_score` |
|---|---|---|
| P1 | baseline probe | 0.6591 |
| — | inject 5x real negative outcome (`/command/feedback`, rating=1, reward=0.0, correct `situation_hash`) | — |
| P2 | repeat probe | **0.5835** (-0.0756 vs P1) |
| — | inject 5x real positive outcome (rating=5, reward=1.0) | — |
| P3 | repeat probe | **0.6237** (+0.0402 vs P2) |

Raw `policy_memory` row after the run: `action_type='git_status'`,
`situation_hash='v2:24417a9ec8a1'` -> `avg_reward=0.6235294117647059`,
`sample_count=17` — consistent with the full write history (automatic
reward=0.8 on every one of this mission's successful `/command` calls, plus
the 5 injected 0.0s and 5 injected 1.0s), confirmed by direct SQL read, not
inferred.

**Interpretation, honestly, including the asymmetry:** `PolicyMemory` is a
plain cumulative average with no decay (`core/memory/policy.py`,
`update_from_outcome`) — every sample ever recorded for a
`(action_type, situation_hash)` pair carries equal, permanent weight. That is
why the positive recovery (+0.0402 over 5 samples, applied at n=12->17) is
smaller than the negative drop (-0.0756 over 5 samples, applied at n=6->11):
later samples move a larger, already-larger `n` less. This is a real,
observed property of the *current* learning mechanism, not a test artifact —
worth carrying into Stage 3 (organic goal progress), since a policy memory
that never forgets becomes steadily less responsive to new evidence as
`sample_count` grows. Not fixed here — out of this mission's scope.

**Hard stop confirmation.** `taskkill /PID 46808 /F` succeeded; `tasklist`
shows no `python.exe`; `netstat` shows no `LISTENING` socket on port 8000
(only expected `TIME_WAIT` entries from already-closed connections). The
worktree's temporary `.env` copy was deleted after the run.

## 5. Evidence category (do not collapse these)

| Claim | Category |
|---|---|
| Reward-honesty fix, observability logging, probe-stability tests | SOURCE IMPLEMENTED, INTEGRATED (`vector-integration`), TEST VERIFIED |
| Failure -> outcome evidence -> changed future `PolicyMemory` score -> changed `DecisionEngine.total_score`, in both directions | BEHAVIORALLY VERIFIED, live, real process, real SQLite row, this run |
| Full strategy-switching RG-D2 (multiple competing candidates chosen differently after failure) | NOT ATTEMPTED — explicitly out of scope, unchanged from `PRE_RG_D2_FINAL_CLOSURE_REPORT.md`'s 2/4 reach |
| Promotion to `production-hardening-complete` (the live branch) | NOT DONE — owner-only, never automatic |

## 6. What this does NOT claim

- Does not claim VECTOR "learns to try something different" — only that it
  scores the same thing differently after real evidence, which is what was
  honestly claimable given the current single-candidate owner-command path.
- Does not claim the cumulative-average staleness property above is fixed.
- Does not promote `vector-integration` to the live branch.

## 7. Provider usage this stage

Codex: 1 consult call (design brainstorm) + review calls inside the 3 bridge
packages (bounded within `prog-1fbdc181`'s 30-call budget, 10 used).
Claude: implementation + live-gate execution (this session). Quota bands
before and after: both providers "normal" (Claude ~72%, Codex ~89%
remaining) — no material quota consumption.

---

**STAGE_2_PASS.** Continuing directly to Stage 3 (organic goal progress /
purpose) per the owner's standing instruction not to stop until Stage 7.
