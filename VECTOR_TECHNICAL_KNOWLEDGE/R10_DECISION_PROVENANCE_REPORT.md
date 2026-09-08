# R10 — Decision Provenance

**Starting HEAD:** `17ac4b07ca3d78286b08211bec9bbe0aa8a2b5ec` (the R9 checkpoint). `git status --short`
was clean before starting.

## Objective

Complete the causal identity chain — decision → candidate → winner → veto/rejection → execution →
outcome → reward/suppression → persistence → later decision — started by R7 (Task 92), without
redesigning `decision_id`/`candidate_id` or confusing them with the reusable `situation_hash`.

## Audit methodology

Direct re-inspection of R7's own implementation (`core/loop/decision_engine.py`,
`core/loop/autonomous_loop.py`, `core/memory/counterfactual.py`, `core/memory/policy.py`,
`core/loop/loop_state.py`, `core/memory/episodic.py`) plus R7's own report
(`VECTOR_TECHNICAL_KNOWLEDGE/92_R7_DECISION_CANDIDATE_CORRELATION_REPORT.md`) to check whether R8 or
R9's own subsequent changes introduced any new correlation-relevant write that R7 could not have
anticipated, and whether R7's own documented "Remaining limitations" still hold.

## Findings

### R7's design is intact and complete — no new gap introduced by R8 or R9

R8 added `CorrectionLearner.get_correction_penalty()` — a pure READ, no new persistence write; it
does not create a "decision" record of its own, so it needs no decision_id/candidate_id correlation.
R9's only code change (`core/runtime/plans.py`'s reader/writer key fix) is also a pure read-path fix
with no new write. **Neither R8 nor R9 introduced any new correlation gap.**

### R7's own documented limitation still holds, still correctly out of scope

`core/loop/permission_gateway.py:745-746`'s own internal `CounterfactualMemory.record_rejection(
decision_id=action.action_type, ...)` call (inside the council-REJECTED path) still uses the
non-unique `action_type` value, exactly as R7 reported. This task's own inspection list (`DecisionEngine`,
`AutonomousLoop`, `CounterfactualMemory`, `PolicyMemory`, `loop_state`, reasoning chains, episodic
memory, reward writers, suppression writers) does **not** include `PermissionGateway`, and the
pipeline's own SAFETY section forbids weakening or touching `PermissionGateway` without explicit
authorization. Left untouched, honestly re-confirmed as still open.

### What R10 actually needed to add: proof of genuine retrievability

R7's own tests (24 of them) proved that the RIGHT decision_id/candidate_id values were passed into
each write call (`record_rejection(decision_id=...)`, `store_chain(steps=[...])`, etc.) — call-site
assertions, in some cases against mocked sinks. R10's task explicitly requires one level stronger:
*"later retrieval identifies D"* — i.e., that the correlation is actually recoverable from real,
persisted storage after the fact, not just that it was passed into a write. This had not been proven
end-to-end against real (SQLCipher-encrypted) `episodic_memory`/`reasoning_chains` storage. **This is
the one genuine, if modest, gap R10 closes** — not a code defect, a verification-depth gap.

No missing edge required a schema redesign; the STOP CONDITIONS in R10's own instructions were never
triggered.

## Implementation

**Zero production code changes.** R10's audit found R7's design complete and R8/R9 introduced no new
gap; the only artifact of this stage is a new test file providing the stronger, real-storage
retrieval proof the task requires.

`tests/test_r10_decision_provenance.py` — a REAL, unmocked round-trip against
`episodic_memory`/`reasoning_chains` (via the module's own SQLCipher-aware `get_temp_cursor()`
helper — a plain `sqlite3.connect()` cannot open this file directly, proving the test reads through
the real encrypted storage layer, not around it) and a REAL `CounterfactualMemory` on an isolated
temp db. Like `tests/test_task89c_goal_progress.py`, this file sets `VECTOR_DB_PATH` before any
VECTOR import and must be run standalone (documented in its own docstring) — `core.memory.episodic`'s
module-level singleton connection means this isolation only works as the first module to touch it in
a given pytest process.

## Tests

`tests/test_r10_decision_provenance.py` — **4 tests, all passing**:

- `test_decision_to_outcome_to_persisted_reward_retrievable_by_decision_id` — the task's own required
  chain (decision D → candidates → A wins → outcome recorded → reward recorded → later retrieval
  identifies D), proven with a real SQL `SELECT ... WHERE steps LIKE '%<decision_id>%'` against the
  real `reasoning_chains` table, confirming exactly one matching row, with both `decision_id` and
  `candidate_id` recoverable from its `steps` JSON and a real, non-null reward value persisted
  alongside them.
- `test_unrelated_outcome_cannot_attach_to_a_different_decision` — two real, distinct decisions;
  proves decision 2's identity never appears anywhere inside decision 1's persisted record.
- `test_same_situation_hash_aggregates_legitimately_across_distinct_decisions` — proves, together in
  one test (not as separate unrelated assertions), that two decisions sharing an action_type+params
  share one `situation_hash` (legitimate policy-learning aggregation) while their `decision_id`/
  `candidate_id` remain fully distinct per-occurrence identities — the exact distinction R7/R10 must
  never blur.
- `test_veto_retains_decision_identity_in_real_counterfactual_storage` — a real veto, retrieved by a
  direct SQL query (`WHERE decision_id = ?`) against a real, isolated `CounterfactualMemory` db,
  confirming exactly one matching row with the correct `candidate_id` in its `context`.

## Behavioral evidence

```
Real SQLCipher-backed round trip (not a mock assertion):
    decision D1, winner action_type="r10_exec_action"
    _act_on(winner) -> real store_chain() write
    SELECT reward, steps FROM reasoning_chains WHERE steps LIKE '%<D1.decision_id>%'
    -> exactly 1 row; steps contains {"correlation": {"decision_id": D1, "candidate_id": C1}};
       reward is a real non-null float

Cross-decision isolation, real storage:
    D1 (r10_action_one) and D2 (r10_action_two) both executed and persisted
    D2's decision_id string does not appear ANYWHERE in D1's persisted reasoning_chains row

Situation hash vs instance identity, proven together:
    D1, D2: same action_type + same params
    situation_hash(D1.winner) == situation_hash(D2.winner)   <- legitimate aggregation
    D1.decision_id != D2.decision_id                          <- distinct occurrences
    D1.winner.candidate_id != D2.winner.candidate_id          <- distinct candidate instances

Veto, real storage:
    a real veto fires for decision D (should_avoid() matches a seeded rejection)
    SELECT decision_id, context FROM rejections WHERE decision_id = '<D.decision_id>'
    -> exactly 1 row; context.candidate_id == D.winner.candidate_id
```

## Regression comparison

R10 made zero production code changes, so no new regression is possible beyond R9's own established
baseline. Confirmed the new test file collects cleanly as part of the full suite
(`pytest tests/ --collect-only`, 0 collection errors) without being included in a combined run (it
requires the same standalone-only isolation as `test_task89c_goal_progress.py`, for the identical
reason: `core.memory.episodic`'s module-level singleton). R9's full-suite result (5,028 passed / 16
failed [13 baseline + 3 confirmed environment/test-isolation, all individually re-verified clean] /
37 skipped / 0 errors) stands unchanged as the current baseline.

## Historical compatibility

Nothing changed — R10 is test-only. All of R7/R8/R9's existing correlation writes, signatures, and
schemas are untouched.

## Security analysis

No new code, no new attack surface. The new test file uses a dummy, clearly-labeled
`VECTOR_DB_KEY=test-only-key-not-for-production-r10` for its isolated temp database, matching
`test_task89c_goal_progress.py`'s established convention.

## Governance analysis

No production code touched. `PermissionGateway` remains explicitly out of scope, per R7's own
documented limitation, reconfirmed here.

## Remaining limitations

- `permission_gateway.py:745-746`'s own internal `record_rejection(decision_id=action.action_type)`
  call remains unfixed (same limitation R7 already documented; still out of scope without explicit
  authorization to modify `PermissionGateway`).
- `test_r10_decision_provenance.py`, like `test_task89c_goal_progress.py`, cannot be safely included
  in a combined multi-file pytest run — both require standalone execution. This is now a 2-file (plus
  `test_trust_ladder.py` observed as full-suite-fragile in R9, though it does not use the
  VECTOR_DB_PATH pattern) family of tests that need this caveat tracked for future full-suite runs.
- No SQL-level "find chain/rejection by decision_id" convenience API was added to
  `EpisodicMemory`/`CounterfactualMemory` — R10's tests query the underlying tables directly. Adding
  such a helper was judged unnecessary (the direct query is simple, safe, and sufficient to prove the
  requirement) and would have been a small scope expansion beyond "propagate missing identifiers,"
  which R10 found nothing missing to propagate.

## Explicit non-claims

This task proves correlation and retrievability. It does **not** claim VECTOR uses this correlation
for any learning, adaptation, or generalization — that is E1-E6's domain, not R10's.

## Maturity classification

"decision → candidate → winner → veto/execution → outcome/reward → persistence → later retrieval":
**S5 (behaviorally verified)**, now against REAL persisted (SQLCipher-encrypted) storage, not only
call-site/mock assertions — the correlation chain from decision occurrence through to a queryable,
retrievable persisted record is proven end-to-end.

## Final verdict

```
STARTING HEAD: 17ac4b07ca3d78286b08211bec9bbe0aa8a2b5ec
AUDIT RESULT: R7's correlation design confirmed complete; R8/R9 introduced no new gap;
              one already-documented limitation (permission_gateway.py) reconfirmed, still
              out of scope
NEW GAP FOUND REQUIRING SCHEMA REDESIGN: none -- STOP conditions never triggered
IMPLEMENTATION: none (zero production code changes)
NEW TESTS: 4/4 PASS -- real SQLCipher-backed round-trip retrieval proof (episodic_memory,
           reasoning_chains, CounterfactualMemory.rejections)
REGRESSION: 0 possible (no production code changed); collection-clean confirmed
MATURITY: S5 for the full decision->candidate->outcome->persistence->retrieval chain
VERDICT: R10 COMPLETE
```

**FINAL HEAD:** recorded after commit, below.
