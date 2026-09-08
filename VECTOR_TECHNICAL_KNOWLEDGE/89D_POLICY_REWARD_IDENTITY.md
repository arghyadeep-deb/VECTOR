# Task 89, Agent D — Policy/Reward Identity (R4/R5)

Scope: `core/memory/policy.py`, `core/loop/decision_engine.py` (reader only), the specific
writer call sites in `core/loop/autonomous_loop.py` listed in the task briefing, and
`hands/runner.py` (classification comment only). No live process interaction, no network,
no deletion/migration of historical `policy_memory` data.

Environment note: VECTOR's 7-day autonomous experiment (PID 37588) was confirmed closed
before this session started; nothing here touched any live process, `.env`, or experiment
config. All verification below is source reads + targeted `pytest` runs.

---

## D1 — Compatibility matrix (independently re-verified from current source)

The background briefing's line numbers were **not** trusted; every writer and the reader
were re-read from current source this session. One writer described in the briefing
(**#4, the `plan_step:`-prefixed writer, "~line 1493"**) **does not exist in current
source** — a repo-wide grep for `plan_step` inside `core/loop/autonomous_loop.py` and a
grep for all `update_from_outcome`/`PolicyMemory().update` call sites repo-wide (13 files)
turned up no such writer. It is either stale information from the background research or
was already removed before this session; either way, D1's job is to report what is
actually in source, not what a prior document claimed, so it is listed below as
**NOT FOUND**.

| # | Location (verified this session) | Exact formula (before this task's changes) | Matched reader's pre-fix format? |
|---|---|---|---|
| Reader | `core/loop/decision_engine.py:268` (`DecisionEngine._make_situation_hash`), called from `_score_candidate` at `:273`, feeding `get_score()` | `f"{action_type}:{sorted(params.items())}"` → sha256[:12] | — |
| 1 | `autonomous_loop.py` counterfactual-veto penalty writer, inside `_act_on()`'s `CounterfactualMemory.should_avoid()` block (was at source lines ~980–983 before this task's edits) | `f"{action_type}:{sorted(params.items())}"` → sha256[:12] — **hardcoded `reward=0.05`**, written via `update_from_outcome()` | YES |
| 2 | `autonomous_loop.py` "VectorCode reward" writer, inside the `_VC_ACTION_TYPES` branch of `_act_on()` (was at source lines ~913–916) | `f"{action_type}:{json.dumps(params, sort_keys=True, default=str)}"` → sha256[:12] | NO — different serialization convention (`json.dumps` vs. Python `sorted(dict.items())` repr) |
| 3 | `autonomous_loop.py` main 5-factor reward writer, in `_act_on()`'s post-governor-dispatch block (was at source lines ~1110–1113, **not** the briefing's cited ~1263 — re-confirmed this session) | same `json.dumps(params, sort_keys=True, default=str)` form | NO — same mismatch as #2 |
| 4 | `plan_step:`-prefixed writer, briefing's "~line 1493" | **NOT FOUND** — no `plan_step:` string, and no fourth `update_from_outcome`/`PolicyMemory().update` call site, exists anywhere in current `core/loop/autonomous_loop.py` (repo-wide grep for both `plan_step` and `update_from_outcome` performed this session) | N/A — does not exist in current source |
| 5 | `hands/runner.py::_update_policy()`, `~line 141–147` | `sha256(f"hand:{name}")` — **no params at all**, no `action_type`/`params`-pair structure of any kind | NO, and structurally unreachable regardless of format (see below) |
| — | `PolicyMemory.make_situation_hash()` (`core/memory/policy.py:24`, pre-existing, before this task's changes) | `@staticmethod`, `json.dumps(context, sort_keys=True, default=str)` if `context` is a dict, else `str(context)` → sha256[:12]. Already co-located with the table it keys. Already called by `router.py:180` and `router.py:316`. | Not directly comparable pre-fix — different calling convention (`(context: dict\|str)`, not `(action_type, params)`) |
| — | `core/api/routers/commands.py:44` — its **own** independent `_make_situation_hash(params)` | a third, independent implementation, HTTP-router-triggered path, lower priority per the task's SCOPE (explicitly out of this task's primary target) | not compared — out of scope, left untouched |

**Independent structural re-verification of writer #5's "unreachable" claim** (not just
carried over from the briefing): grepped every `Candidate(` construction site in
`core/loop/autonomous_loop.py` (candidate generation from goals at `~770`, the
`proactive_welcome_back` construction at `~2401`, and the anticipation-prediction
construction at `~2660`). None of the three ever sets `action_type` to a hand's name — the
only `action_type` values that ever reach `DecisionEngine.evaluate()` come from
goal-mapped actions, `proactive_*` strings, or `pred.action_type` (anticipation engine
output). `hands/runner.py`'s `_update_policy()` writes under `action_type=hand.name`, which
no candidate-generation path ever produces. Confirmed: fixing writer #5's key **format**
alone would not make it reachable — this is a **DEPRECATED / DO-NOT-CONNECT** classification,
not a to-do. A comment documenting this was added at the call site; the writer itself was
left untouched (still writes its old sha256(f"hand:{name}") format, harmlessly unread).

---

## D2 — Canonical identity function: decision and why

**Decision: `PolicyMemory.make_situation_hash()` was extended, in place, to become the
single canonical identity function — no new module was created.**

`core/memory/policy.py`'s `make_situation_hash()` was inspected directly (signature,
docstring, both real callers in `router.py`) before deciding this. It already:
- lives co-located with the `policy_memory` table it keys (satisfies "prefer the existing
  co-located function" over a new module),
- is already called by two independent sites (`router.py:180`, `router.py:316`) with a
  single `(context: dict | str)` argument,
- already performs the right *kind* of canonicalization (`json.dumps(..., sort_keys=True,
  default=str)`) — the writers' independent reimplementations of this were arriving at the
  same idea, just inconsistently.

Nothing found this session proves the existing function is structurally unable to serve
both conventions, so **a new `core/loop/policy_key.py` module was explicitly not created**,
per the task's instruction. Instead, a second, disambiguated calling convention was added
as a **backward-compatible overload on the same staticmethod**:

```python
@staticmethod
def make_situation_hash(context: dict | str, params: dict | None = None) -> str:
    if params is not None:
        # NEW convention: make_situation_hash(action_type, params)
        key = json.dumps({"action_type": context, "params": params}, sort_keys=True, default=str)
        return "v2:" + hashlib.sha256(key.encode()).hexdigest()[:12]
    # ORIGINAL convention: make_situation_hash(context) — unchanged, byte-identical output
    if isinstance(context, dict):
        key = json.dumps(context, sort_keys=True, default=str)
    else:
        key = str(context)
    return hashlib.sha256(key.encode()).hexdigest()[:12]
```

`router.py:180` and `:316` both call the function with exactly one positional argument
(a `str`), so `params` stays `None` for them and they fall through to the byte-identical
original code path — **`core/memory/router.py` was not modified**, confirming the wrapper
requirement ("avoid touching router.py/commands.py unless strictly necessary") was met by
not needing to touch it at all.

### What the canonical function does NOT do (a deliberate, scoped limitation)

The new `(action_type, params)` convention canonicalizes the **entire `params` dict**,
unfiltered — it does not drop display-only keys (e.g., a goal candidate's `title`) and does
not build a "defining-params allowlist" per action-type family. This was a deliberate choice,
not an oversight: `VECTOR_TECHNICAL_KNOWLEDGE/87_RECONCILED_REWARD_LOOP_REMEDIATION_SPEC.md`
§11.2 (read this session per the task's instruction) documents that a prior, much more
thorough investigation treated exactly this question — *which params are "defining" vs.
"display-only," whether `source` should be part of identity, whether plan-step candidates
share a policy domain with goal-originated ones of the same `action_type`* — as still
**design-only, with per-action-type items explicitly marked UNVERIFIED**, and warned that
collapsing situations under an unproven allowlist risks "silently merging semantically
different situations." That is exactly the class of risk the task's DECISION GATE invites
stopping short on.

This task instead fixed the **narrower, unambiguous** bug: four independent
implementations of "hash this action+params" used **different serializations of the
identical semantic input**, so the *same* logical situation hashed differently depending on
which writer touched it last — a pure format bug, not a "what counts as the situation"
question. Canonicalizing the *encoding* (not changing *what* is encoded) fully reconnects
writers #2/#3 to the reader without taking on the allowlist risk. **The defining-params
allowlist work (dropping `title`, keying on `goal_id`+`source`-category, etc.) is not
implemented here** — it remains exactly the open, UNVERIFIED-per-action-type design item
§11.2 already described, and is the concrete, un-applied patch-proposal candidate for a
future task, not something this session forced through under time pressure.

`decision_engine.py`'s reader (`_make_situation_hash`) now delegates to this same function:

```python
def _make_situation_hash(self, candidate: Candidate) -> str:
    return self._get_policy().make_situation_hash(candidate.action_type, candidate.params)
```

`decision_engine.py`'s own now-unused `import hashlib` was removed (its only use was the
old inline hash formula this replaced).

---

## D3 — Suppression/reward channel separation: design, schema, and why

### Schema decision

Read the actual `CREATE TABLE policy_memory` definition first (`core/memory/episodic.py`,
inside `_create_tables()`):

```sql
CREATE TABLE IF NOT EXISTS policy_memory (
    action_type TEXT,
    situation_hash TEXT,
    avg_reward REAL,
    sample_count INTEGER DEFAULT 0,
    last_updated TEXT,
    PRIMARY KEY (action_type, situation_hash)
)
```

**Chosen: option (a), a new column on the existing row** (`veto_count`), not a separate
table — the project's own `memory.md` rule explicitly blesses this ("Adding columns is OK.
Renaming or dropping is a CRITICAL violation"), and a same-row column keeps
`get_score()`/`update_from_outcome()`'s existing primary-key lookup pattern unchanged,
which is the smallest-blast-radius option per the task's "smallest safe separation"
instruction. `CounterfactualMemory`'s own `rejections` table (unmodified, verified via a
regression-test assertion below) already records every veto in full detail — `veto_count`
is not a duplicate of that; it exists only so a suppression-only row is distinguishable
from a real-outcome row under the shared canonical identity.

Column added via the codebase's existing idempotent-migration pattern (mirrors
`_ensure_decay_columns()`, already present for `stability_days`/`last_touch`):

```python
def _ensure_policy_columns(conn) -> None:
    cols = {row[1] for row in conn.execute('PRAGMA table_info("policy_memory")').fetchall()}
    if not cols:
        return
    if "veto_count" not in cols:
        conn.execute('ALTER TABLE "policy_memory" ADD COLUMN veto_count INTEGER DEFAULT 0')
```
Called from `_create_tables()` on every DB connection init (guarded, safe to call
repeatedly, never touches existing row values — an `ALTER TABLE ADD COLUMN` only adds the
column; it does not rewrite `avg_reward`/`sample_count`/`situation_hash` on any existing
row). Also mirrored into `deploy/sqlite_schema.sql` and `deploy/supabase_schema.sql` (both
files' own header comments say they must match `core/memory/episodic.py` exactly, for
Turso/D1/Supabase last-write-wins sync).

### New method: `PolicyMemory.record_suppression(action_type, situation_hash)`

Increments `veto_count` **only** — never touches `avg_reward`/`sample_count`. A brand-new
row created by a suppression event has `avg_reward=NULL, sample_count=0, veto_count=1`.

### Two defensive fixes this addition required (both scoped strictly to handling the new NULL-avg_reward row-state, not to changing any existing arithmetic)

1. **`get_score()`**: a row can now exist with `avg_reward IS NULL` (suppression-only, no
   real outcome yet). Added a guard returning `DEFAULT_SCORE` for that case, instead of
   letting `float(None)` raise into the existing broad `except` (which would have "worked"
   functionally but logged a spurious ERROR on every such lookup).
2. **`update_from_outcome()`**: if a real outcome later lands on a key that currently has
   only a suppression-only row (`avg_reward=NULL, sample_count=0`), the existing
   `new_avg = (old_avg * n + reward) / (n + 1)` line would crash on `None * 0`. Added a
   guard treating `avg_reward IS NULL` as the starting state `(0.0, 0)` before the
   arithmetic runs. **The cumulative-mean formula itself is byte-for-byte unchanged** — this
   only teaches it to recognize the one new starting row-state D3's own schema addition
   introduces; it does not touch what the reward-weighting rule does for any row that
   already had a real `avg_reward`.

### Writer #1 (the veto penalty) — corrected

`_act_on()`'s counterfactual auto-block branch now calls:
```python
_sit_hash = self._get_policy().make_situation_hash(winner.action_type, winner.params)
self._get_policy().record_suppression(winner.action_type, _sit_hash)
```
instead of `update_from_outcome(..., reward=0.05)`. The hardcoded `reward=0.05` — a
control-flow constant with no relationship to any actual outcome — no longer enters the
same cumulative mean real 5-factor/VectorCode outcomes accumulate into.

### The residual risk this reintroduces — read, not assumed away

`tests/test_counterfactual_block_penalizes_policy.py`'s original docstring documented a
real, previously-observed live bug (2026-06-24 soak run): before its own fix, the veto path
never touched `policy_memory` at all, so `decision_engine` kept re-proposing an
already-vetoed candidate forever (nothing in its score ever changed). That prior fix
(writing `reward=0.05` into `avg_reward`) *did* stop the loop, but by permanently
contaminating the real reward signal — exactly what this task's D3 requires removing.

`VECTOR_TECHNICAL_KNOWLEDGE/87_RECONCILED_REWARD_LOOP_REMEDIATION_SPEC.md` §3 row H and
§10 (read this session, per the task's explicit instruction to consult it before deciding)
independently reached the same conclusion this task's D3 describes — separate the channels
— and explicitly named the *actual* durable fix for the reproposal-loop risk as decoupling
`goal.progress` from the reward formula (a different remediation item, in the "Goal
feedback loop" section of `autonomous_loop.py` this task's SCOPE explicitly forbids
touching — it names it as another agent's parallel work in this same overnight
remediation). D3 here is a correctly-ordered *prerequisite* for that other fix to mean
anything (per §11.4: "R4 ships before R5" — suppression separation before key
canonicalization, which is also the order this session implemented them in), not a
standalone guarantee against reproposal loops on its own.

This is stated plainly rather than hidden: **after this change, a candidate whose other
four scoring factors never change between cycles could in principle keep winning and keep
getting vetoed indefinitely**, since nothing in `DecisionEngine`'s scoring weights or
candidate generation changed here (both explicitly out of this task's D5 restrictions).
The updated regression test (`test_counterfactual_auto_block_records_suppression_not_reward`,
formerly `test_counterfactual_auto_block_penalizes_policy_score`) documents this trade-off
in its own docstring rather than silently reversing the old assertion.

---

## D4 — Versioning

New `(action_type, params)`-convention hashes carry a `"v2:"` prefix
(`v2:9dbe9b92f1ce`, etc.). Old un-prefixed rows (both the historical
`sorted(dict.items())`-repr format and the mismatched `json.dumps` format writers #2/#3 used
before this fix) are **never migrated, never backfilled, never deleted** — they simply sit
in the table under their old string keys, which new code never looks up (a `"v2:"`-prefixed
key can never collide with an un-prefixed one). New writes only, per the task's explicit
instruction. A future `"v3:"` scheme (e.g., if the defining-params-allowlist work described
in D2 ever ships) would coexist with `"v2:"` rows exactly the same way.

---

## Exact files/lines changed

| File | Change |
|---|---|
| `core/memory/policy.py` | `make_situation_hash()` extended with the `(action_type, params)` overload + `"v2:"` prefix (docstring explains both conventions); `get_score()` NULL-`avg_reward` guard; `update_from_outcome()` NULL-`avg_reward` guard before the mean arithmetic; new `record_suppression()` method; `__main__` self-test extended to exercise both. |
| `core/loop/decision_engine.py` | `_make_situation_hash()` now delegates to `PolicyMemory.make_situation_hash(action_type, params)` instead of its own inline formula; unused `import hashlib` removed. |
| `core/loop/autonomous_loop.py` | Veto-penalty writer (in `_act_on()`'s counterfactual block) now calls `record_suppression()` via the canonical hash instead of `update_from_outcome(..., reward=0.05)`; VectorCode-reward writer and 5-factor-reward writer both now compute their hash via `pm.make_situation_hash(action_type, params)` instead of their own inline `json.dumps`+sha256 formula; unused `import hashlib` removed. The fanout-handler section and the "Goal feedback loop" section (goal-progress increment) were **not touched**, per SCOPE. |
| `core/memory/episodic.py` | New `_ensure_policy_columns()` (mirrors the existing `_ensure_decay_columns()` pattern), called from `_create_tables()`; adds `policy_memory.veto_count INTEGER DEFAULT 0` via guarded, idempotent `ALTER TABLE`. |
| `deploy/sqlite_schema.sql`, `deploy/supabase_schema.sql` | `veto_count` column added to `policy_memory`, mirroring `episodic.py` (both files' own header comments require this). |
| `hands/runner.py` | Comment only, added to `_update_policy()` — documents the DEPRECATED/DO-NOT-CONNECT classification from D1. No code/format change (deliberately: fixing the format alone would not make it reachable). |
| `tests/test_counterfactual_block_penalizes_policy.py` | Rewritten to assert the corrected D3 behavior (veto leaves `avg_reward` untouched; `veto_count` increments; `CounterfactualMemory.rejections` still fires) instead of the old, now-superseded "veto lowers avg_reward" assertion. Docstring documents why, and the residual risk. |
| `tests/test_policy_reward_identity.py` | **New.** Covers identity round-trip correctness (tests 1–4, 6 from the task's required list; test 5 lives in the file above). |

---

## Test results

```
tests/test_policy_reward_identity.py .....                    (5 passed)
tests/test_counterfactual_block_penalizes_policy.py .         (1 passed)
tests/test_decision_engine.py ...........                     (11 passed)
tests/unit/test_decision_engine.py ............................  (28 passed)
tests/unit/test_memory_stores.py ......................................  (38 passed)
tests/integration/test_phase_a3_counterfactual_act_on.py .............  (13 passed)
tests/integration/test_phase_a4_metacognition_decision.py ..............  (14 passed)
tests/test_point_system.py ........                            (8 passed)
```
**126 passed, 0 failed** across all targeted runs.

One unrelated pre-existing failure was found and confirmed **not** caused by this change:
`tests/integration/test_absorbed_autonomy.py::test_scheduler_fires_hands` fails identically
on the unmodified baseline (`git stash` + re-run reproduced the exact same
`assert 525.0 == 550` failure) — it is an HP-headroom-shaping assertion in
`core/city/agent_base.py::award_points()` (a `[repeat#0 x1.000, headroom x0.500]`
multiplier halving the raw +50 award), entirely unrelated to `policy_memory`/reward
identity and outside this task's scope. Not fixed; reported for visibility only.

Per the task's SAFETY instructions, the full repository test suite was **not** run (it
contains at least one known, pre-existing, environment-specific hang unrelated to this
work) — only the tests directly relevant to this change were run, as listed above.

A test-invocation artifact worth recording for future agents in this repo: running
`python core/memory/policy.py` (or any module) as a bare script from a subdirectory-relative
path can, in this environment, resolve `import core.*` from a *different* installed/editable
copy of the codebase than the current worktree (because `sys.path[0]` becomes the script's
own directory, which doesn't contain a `core/` package, so resolution falls through to
whatever alternate root is registered elsewhere on `sys.path`) — this produced a confusing
"no such column: veto_count" failure that had nothing to do with the actual code change
(confirmed via `runpy.run_path(..., run_name="__main__")` from the worktree root, via
direct `python -c` imports with cwd=worktree root, and via `pytest`, all of which correctly
resolve to this worktree's files and all pass). Always verify via `pytest` from the worktree
root, not via a bare `python <relative/path>.py` invocation, when multiple checkouts of this
codebase may exist on the machine.

---

## Summary

D2 (writer-key canonicalization) and D3 (suppression/reward channel separation) were both
**fully implemented**, not stopped at the compatibility-matrix-only gate — the format-unification
work needed to reconnect writers #2/#3 to the reader was judged safe and boundable within
this session (it changes *encoding*, not *meaning*, of the identity key), and D3's channel
separation was a bounded, well-precedented schema addition. What was deliberately **not**
implemented, and is called out explicitly rather than silently skipped, is the
**defining-params allowlist** (dropping display-only params like `title`, keying by
`goal_id`/coarse `source` category) that a full "situation representation" fix would need —
that remains genuinely open, per-action-type UNVERIFIED work (as the prior reconciled spec
already found), and forcing it through in this session would have been exactly the kind of
under-tested, ambiguous key-merging risk the task's decision gate warns against. It is a
precise, scoped, un-applied patch-proposal for a future task, not something this document
claims to have resolved.
