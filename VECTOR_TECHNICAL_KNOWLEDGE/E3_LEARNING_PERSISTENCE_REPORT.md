# E3 — Persistence

**Starting HEAD:** `b1423fcccc074243f6862c792ea18bf982640abe` (the E2 checkpoint). Clean tree,
confirmed before starting.

## Question

Does legitimate learning survive a process boundary / database close-reopen / restart — without
relying on any global, cache, process-local counter, or singleton in-memory state that could silently
mask a real persistence defect?

## Method

Direct source audit of the two learning-relevant stores (`PolicyMemory`, `EpistemicTracker`) for any
in-memory state that could diverge from what is actually durable on disk, followed by a targeted
positive/negative behavioral test of the one real risk found.

## Findings

### `PolicyMemory` — no cache exists; already proven by E1

`core/memory/policy.py` is a fully stateless wrapper: `get_score()` and `update_from_outcome()` issue
a real SQL `SELECT`/`INSERT ... ON CONFLICT` on every single call, with no intermediate dict or cache
of any kind. There is no code path by which an in-memory value could diverge from disk. E1 (this
session) already proved `PolicyMemory`'s persistence end-to-end — a real connection close, fresh
instances afterward, an actual winner flip caused by the restored value, plus duplicate-update and
old-update-across-restart controls. That proof is not repeated here; `TestPolicyMemoryHasNoCache`
adds one direct structural confirmation (no cache-like attribute exists on the object at all) so the
absence-of-risk claim is verified, not merely asserted.

### `EpistemicTracker` — a real in-memory cache exists; this is the one genuine risk in scope for E3

`EpistemicTracker.__init__()` loads all beliefs into `self._beliefs: dict` from the DB, and
`update_belief()` writes to `self._beliefs[key]` **before** calling `self._persist_belief(key,
belief)`, which is wrapped in a broad `except Exception: logger.debug(...)`. This is architecturally
the exact class of problem E3 warns about: if the SQL write silently fails, `get_belief()` on the
**same instance** would still report the new value, because it reads the in-memory dict, not the
database — a genuine persistence failure could be invisible to a caller that never restarts.

R9 (this session) already tested restart behavior correctly, using a **fresh instance** rather than
the same object — the right methodology, since a fresh instance's `self._beliefs` starts empty and
must genuinely reload from disk. But nothing had yet tested the FAILURE boundary directly: what
happens if a write genuinely fails? This is the one thing E3 adds.

## Implementation

**None.** The audit found no defect requiring a fix — `EpistemicTracker`'s cache-before-persist
ordering is architecturally normal (most in-memory-cached persistence layers work this way), and the
critical property (a real restart cannot be fooled by the cache) needed to be *tested*, not *fixed*.

## Tests

`tests/test_e3_learning_persistence.py` — **4 tests, all passing**:

- `TestPolicyMemoryHasNoCache` — direct structural confirmation of the "no cache exists" claim (scans
  the object's own attributes for anything cache-like).
- `test_in_memory_value_visible_before_persistence_completes` — documents the real, honest
  intermediate state: within the same instance, a just-written belief is visible via the cache even
  when the underlying SQL write is made to fail (via a patched `_persist_belief`) — this is expected,
  not a defect, and is stated plainly rather than hidden.
- **`test_a_failed_persist_is_honestly_absent_after_a_real_restart`** — the core proof: with
  `_persist_belief` forced to raise, a genuine restart (fresh `EpistemicTracker` instance, same db
  file) correctly shows the belief as `None` — the cache never manufactures false durability across
  the one boundary that actually matters (a real restart).
- `test_a_successful_persist_survives_a_real_restart` — the necessary positive control: without the
  induced failure, the identical restart sequence DOES preserve the value — proving the negative
  result above is a real property of the failure path, not an artifact of a broken restart test.

## Regression comparison

No production code changed in this stage; no regression risk. All 4 new tests pass in isolation
(no `VECTOR_DB_PATH` isolation needed here — both `PolicyMemory` object introspection and
`EpistemicTracker`'s own `db_path` constructor argument already avoid the shared-singleton problem
that required standalone execution for E1/R10).

## Explicit non-claims

This does not claim `EpistemicTracker`'s cache-before-persist ordering is the "correct" or "best"
architecture — only that, as implemented, it does not create a false-durability risk across a real
restart, which is the property that matters for the claims this pipeline makes about persistent
learning. It also does not claim anything about `EpisodicMemory`'s separate
`CircuitBreakerOpenError`-triggered write-buffering behavior beyond noting it exists and is logged
honestly (a `logger.warning` fires whenever a write is buffered rather than persisted immediately) —
that mechanism was not the subject of this stage's targeted test.

## Final verdict

```
STARTING HEAD: b1423fcccc074243f6862c792ea18bf982640abe
DEFECT FOUND: none
RISK IDENTIFIED AND TESTED: EpistemicTracker's in-memory cache -- confirmed it does NOT mask a real
                              persistence failure across an actual restart (both positive and
                              negative cases proven)
IMPLEMENTATION: none (verification only)
NEW TESTS: 4/4 PASS
REGRESSION: 0 (no production code changed)
VERDICT: E3 COMPLETE
```

**FINAL HEAD:** recorded after commit, below.
