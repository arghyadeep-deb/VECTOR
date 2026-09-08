# E5 — Contradiction

**Starting HEAD:** `e49f3ed353a532000864fc26b81148f48a5a826f` (the E4 checkpoint). Clean tree,
confirmed before starting.

## Question

Does VECTOR detect belief A vs. belief NOT-A (or conflicting correction lessons)? Does it store both,
select one, use confidence/provenance/recency, silently overwrite, or become unstable?

## Method

Direct audit of `EpistemicTracker` (already covered in R9; not repeated) and
`CorrectionLearner`'s full dedup/consolidation/retrieval pipeline
(`_find_duplicate`, `_consolidate`, `retrieve_applicable_lessons`), then a genuine
build-test-investigate-revert cycle when the first attempted fix was found, via direct regression
testing, to break real pre-existing correct behavior.

## Findings

### `CorrectionLearner._consolidate()` already has a real, deterministic contradiction policy

```python
if new.correction != existing.correction and new.confidence > existing.confidence:
    existing.supersedes = existing.id
    existing.id = f"cl_{uuid.uuid4().hex[:10]}"
    existing.correction = new.correction
    ...
```
This is exactly what E5 asks for: confidence-gated, deterministic, provenance-preserving (`.supersedes`)
supersession — not a new mechanism, one that already existed.

### Bug (a): `_find_duplicate()` could hand consolidation a STALE base state

`_consolidate()` never updates a stored row in place — every call (initial store, every later
reinforcement or supersession) issues its own fresh `mem.store()`. `_find_duplicate()` returned
whichever matching row `mem.recall()` happened to return *first*, with no guarantee that was the most
current snapshot. **Fixed**: it now scans all matches sharing the candidate's `situation_hash` and
keeps the one with the highest `(confidence, timestamp)` — the same authority rule `_consolidate()`
itself already uses to decide supersession.

### Bug (b): `retrieve_applicable_lessons()` had the identical staleness exposure on the read side

For the same reason, an old, already-reinforced/superseded snapshot of one logical lesson could be
returned alongside its own current replacement, as two apparently-independent lessons — a genuine
"stores both, selects none" failure mode. **Fixed**: results are now deduplicated by `situation_hash`
before sorting/limiting, keeping the same highest-`(confidence, timestamp)` winner as fix (a).

### Investigated, attempted, and REVERTED: broadening `situation_hash` to (domain, situation) only

The reason `_consolidate()`'s supersession branch could never actually fire for genuinely
contradictory corrections (different wording, same real fact — e.g. "the deadline is Friday" vs "the
deadline is Monday") is that `situation_hash` is computed from `(domain, situation,
correction_text[:100])` — different wording always produces a different hash, so `_find_duplicate()`
can never recognize the two as related in the first place.

**Attempted fix**: hash only `(domain, situation)`. This did make cross-wording contradictions
consolidate correctly (verified with a real "Friday" → "Monday" → "Tuesday" sequence, confidence-gated
exactly as designed, provenance recorded).

**Why it was reverted**: a full regression pass immediately surfaced that this breaks real,
pre-existing, CORRECT behavior — `tests/integration/test_correction_integration.py::
test_multiple_corrections_same_domain` stores three genuinely independent, non-contradictory tips
("use httpx", "always use type hints", "prefer async over sync") all under `situation="coding"`.
Under the broadened hash, all three collapsed into one — actively wrong, since none of them
contradicts any other; they are simply three separate pieces of applicable advice for one broad
context.

**Why no fix was forced instead**: distinguishing "a different answer to the same underlying
question" from "an additional, compatible tip for the same broad situation" requires semantic
judgment. Every non-LLM signal available in this codebase was checked and found insufficient:
- Exact-hash equality (the original design): too strict — misses genuine contradictions entirely.
- Domain+situation only: too loose — conflates independent tips (proven by the regression above).
- Word-overlap/Jaccard similarity (the same technique `CounterfactualMemory` already uses elsewhere
  in this codebase) between the two correction texts: also insufficient — "Friday" and "Monday" share
  **zero** lexical overlap, exactly as much as "use httpx" and "use type hints" do. A similarity
  threshold cannot separate the two cases because the discriminating information (are these two
  statements answers to the *same slot*?) is not present in the text at all without understanding
  what the sentences mean.

Per E5's own explicit instruction — *"Only implement a minimal deterministic contradiction policy IF
supported by existing architecture... Do not invent authority semantics without evidence"* — this is
not supported by the existing architecture, and no fix was forced. `situation_hash`'s original,
fine-grained formula (including the correction text) was restored exactly as it was.

## Implementation

1. `CorrectionLearner._find_duplicate()`: now returns the highest-`(confidence, timestamp)` match
   among all rows sharing the exact `situation_hash`, instead of the first one encountered.
2. `CorrectionLearner.retrieve_applicable_lessons()`: results are deduplicated by `situation_hash`
   (same authority rule) before the existing confidence-sort and `limit` truncation.
3. `situation_hash`'s formula: **unchanged from before this task** (investigated, reverted, confirmed
   correct as originally written).

No new table, no new subsystem, no new confidence formula, no change to `_consolidate()`'s own logic
or `PolicyMemory`/`EpistemicTracker`.

## Tests

`tests/test_e5_contradiction.py` — **9 tests, all passing**:

- `TestExactDuplicateReinforcement` (5 tests) — the real, reachable contradiction/consolidation path:
  A alone; an identical resubmission reinforces confidence and consolidates into one row (not two);
  a direct proof that `_find_duplicate()` now returns the current, reinforced snapshot rather than
  the stale original; a direct proof that repeated reinforcement never leaves stale and current
  snapshots simultaneously retrievable; and a genuine restart (fresh instance, same durable store)
  preserving the reinforced state exactly.
- `TestIndependentCoLocatedCorrectionsStayIndependent` (1 test) — the regression that caused the
  revert, now encoded as a permanent guard: three genuinely independent tips for one broad situation
  remain all independently retrievable.
- `TestContradictionCannotEscalateAuthority` (3 tests) — confidence never exceeds the documented 0.95
  ceiling even for a maximally-loaded explicit correction; neither `_consolidate()` nor
  `_find_duplicate()` references `Governor`/`PermissionGateway`.

## Behavioral evidence

```
Exact-duplicate reinforcement (the real, reachable path):
    "hmm, use httpx" (confidence < 0.95) submitted 4 times, same situation
    -> confidence increases each time (reinforcement), one consolidated row, not four
    -> restart (fresh instance, same store): confidence and times_applied both preserved exactly

Independent tips correctly stay independent:
    "use httpx" / "always use type hints" / "prefer async over sync", same situation="coding"
    -> 3 separate, simultaneously-valid lessons, all retrievable (unchanged from before this task)

Cross-wording contradiction (investigated, NOT shipped):
    "the deadline is Friday" -> "the deadline is Monday" -> "the deadline is Tuesday"
    WITH the (domain, situation)-only hash: correctly supersedes with confidence gating and
    provenance -- but ALSO collapses "use httpx"/"type hints"/"async" into one, which is wrong.
    REVERTED for this reason.
```

## Regression comparison

Full targeted regression (`tests/test_e5_contradiction.py` + `tests/unit/test_correction_learner.py`
+ `tests/integration/test_correction_integration.py` + E1-E4's own suites + R6-R9's own suites +
`tests/unit/test_decision_engine.py` + `tests/test_decision_engine.py`, excluding the 4 known
pre-existing baseline failures by name): **0 failures**, including
`test_multiple_corrections_same_domain` now passing again exactly as before this stage began.

## Explicit non-claims

This does **not** claim VECTOR can detect genuine cross-wording contradictions between correction
lessons — it explicitly cannot, and this report says so plainly rather than shipping a fix that
appeared to work on one example while breaking a real, different, already-correct case. This does not
claim any new "authority" semantic was invented — `_consolidate()`'s confidence-gate already existed;
this stage only fixed staleness bugs in what feeds it and read from it, for the one case
(exact-duplicate resubmission) that mechanism already correctly handles.

## Maturity classification

Exact-duplicate reinforcement and its persistence/staleness properties: **S5 (behaviorally
verified)**, now correct at both the write-check and read side. Cross-wording contradiction
detection: **S0 (does not exist)**, honestly reported as an open architectural question requiring a
future semantic-judgment capability this pipeline explicitly keeps out of scope, not a defect to be
silently patched over.

## Final verdict

```
STARTING HEAD: e49f3ed353a532000864fc26b81148f48a5a826f
EXISTING POLICY FOUND: CorrectionLearner._consolidate()'s confidence-gated supersession -- already
                        deterministic, already provenance-preserving, no new authority semantic
                        needed
BUGS FOUND AND FIXED: _find_duplicate() returned a stale (not current) match; retrieve_applicable_
                       lessons() could surface stale + current snapshots of the same lesson together
ATTEMPTED FIX REVERTED: broadening situation_hash to (domain, situation) -- made cross-wording
                         contradiction resolution reachable, but broke real independent-tips behavior;
                         reverted after direct regression proof, root cause requires semantic
                         judgment out of scope, reported not forced
NEW TABLE: none / NEW SUBSYSTEM: none / NEW AUTHORITY SEMANTIC: none invented
NEW TESTS: 9/9 PASS
REGRESSION: 0 new failures; the one test the attempted fix broke (test_multiple_corrections_same_domain)
            confirmed passing again after revert
GOVERNANCE: unaffected (source-text proven)
VERDICT: E5 COMPLETE
```

**FINAL HEAD:** `91da51b23ccdd2e6a07ab1a44b24ef34cc546b77`
