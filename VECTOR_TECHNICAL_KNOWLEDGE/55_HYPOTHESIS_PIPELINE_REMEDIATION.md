# 55 — Hypothesis Pipeline Remediation

**Date**: 2026-09-02
**Type**: FOCUSED FIX — two collateral defects discovered while remediating MUST-FIX Blocker 1
(the missing `await` in `hypothesis_loop()`, see
`52_AUTONOMY_BLOCKER_REMEDIATION.md`). Not a redesign, not a new cognitive subsystem.
**Scope**: `core/brain/hypothesis_engine.py` and `core/loop/autonomous_loop.py`'s
`hypothesis_loop()` only. No other file was touched.

---

## 1. Original Defects

The missing-`await` fix made `hypothesis_loop()` actually execute
`HypothesisEngine.generate_hypotheses()` — but tests written for that fix surfaced two more
problems that meant the pipeline could still silently produce zero persisted hypotheses even
with the coroutine properly awaited:

1. **Key mismatch** — `autonomous_loop.py:2874` read `h.get("hypothesis", str(h))`, but
   `generate_hypotheses()` has always returned the generated text under the key `"text"`, never
   `"hypothesis"`. Every qualifying hypothesis was stored as the Python `str()` representation of
   the whole result dict (e.g. `"{'id': '1', 'text': '...', 'confidence': 0.9, ...}"`) instead of
   the plain hypothesis text.
2. **Confidence hardcoded below the storage gate** — `generate_hypotheses()` hardcoded
   `"confidence": 0.7` on every result, while `hypothesis_loop()` only stores a hypothesis when
   `confidence >= 0.85`. No hypothesis could ever cross the gate, regardless of how good the LLM's
   output was.

---

## 2. Runtime Contract (traced, not assumed)

```
hypothesis_loop()                              [core/loop/autonomous_loop.py:2852]
  → engine = self._get_hypothesis_engine()     [lazy singleton, line ~245]
  → context = self._get_context().get_world_state()
  → hypotheses = await engine.generate_hypotheses(context)
        │
        ▼
HypothesisEngine.generate_hypotheses(observation, count=3)  [core/brain/hypothesis_engine.py:75]
  → prompt asks the LLM for `count` hypotheses (id, hypothesis_text, why_it_might_be_true,
    how_to_test, expected_evidence) as free text — NOT structured JSON
  → content = await self._call(prompt)          [routes through ProviderClient, tier="reasoning"]
  → returns ONE dict (not a list, despite requesting `count` hypotheses):
        {"id", "observation", "text", "timestamp", "status", "confidence"}
  → also enqueues hypothesis["text"] + hypothesis["confidence"] into SuggestionQueue
    (a SEPARATE, always-pending persistence path — independent of hypothesis_loop()'s own
    memory.store() call below; this path already correctly read "text", confirming that is
    the established field name, not "hypothesis")
        │
        ▼
back in hypothesis_loop():
  → for h in hypotheses if isinstance(hypotheses, list) else [hypotheses]:
        confidence = h.get("confidence", 0.0)
        if confidence >= 0.85:
            content = h.get("hypothesis", str(h))   ← WRONG KEY (fixed this task)
            self._get_memory().store(event_type="hypothesis", content=content, ...)
        else:
            suppressed (logged at debug level)
```

**A. Exact structure `generate_hypotheses()` returns**: a single dict —
`{"id": str, "observation": <input>, "text": str, "timestamp": iso8601, "status": "generated",
"confidence": float}`. Not a list, despite the prompt asking for multiple (`count`) hypotheses —
all `count` hypotheses come back as one free-text blob under one `"text"` key with one shared
`"confidence"`. This one-dict-not-list shape is a pre-existing structural quirk, unchanged by this
fix (see §8 Remaining Limitations).

**B. Exact fields `hypothesis_loop()` expects**: `"confidence"` (present, correct name, always
was) and — before this fix — `"hypothesis"` (never present; the correct field is `"text"`).

**C. Where the generated hypothesis text is stored**: two independent places —
(1) `SuggestionQueue` (SQLite, `data/suggestion_queue.db`), written inside
`generate_hypotheses()` itself, always, regardless of confidence; (2) `EpisodicMemory` via
`self._get_memory().store(event_type="hypothesis", ...)`, written by `hypothesis_loop()`, only
when `confidence >= 0.85`. This task's key-mismatch fix affects only path (2) — path (1) already
read `hypothesis["text"]` correctly and was never broken.

**D. Where confidence comes from**: before this fix, nowhere — a hardcoded literal `0.7`, never
computed, never parsed from the LLM's response (the prompt didn't even ask the LLM for a
confidence value). After this fix: parsed from a `"CONFIDENCE: <n>"` marker the prompt now
explicitly asks the LLM to emit as the final line of its response, with a safe fallback (see §5).

**E. Intentional or accidental**: confirmed accidental — see §3.

**F. Downstream consumers already expecting `"text"`**: yes — `generate_hypotheses()`'s own
`SuggestionQueue.enqueue(hypothesis["text"][:500], ...)` call (line 101, unchanged this task) and
the module's own `__main__` self-test (`hyp.get("text", ...)`, line 146, unchanged this task). Both
predate this fix and both already used `"text"`. No consumer anywhere in the codebase (grepped:
`core/benchmark/tasks/t06_proactive_cognition.py`, `core/brain/suggestion_queue.py`,
`tests/integration/test_phase_a5_hypothesis_consumer.py`) ever read a `"hypothesis"` key from this
dict.

**G. Would changing the key break another consumer**: renaming the *producer's* field from
`"text"` to `"hypothesis"` would have broken both of the above pre-existing internal consumers.
Fixing the *consumer* (`hypothesis_loop()`) to read `"text"` instead breaks nothing — confirmed by
grep across the full non-test and test codebase for any other read of this dict's `"hypothesis"`
key (none exist) and re-run of the full test suite (§7).

---

## 3. Root Causes

**Key mismatch**: a plain copy/typo-class bug — the consumer was written expecting a field name
that was never the producer's actual contract. No git history exists showing the field was ever
named `"hypothesis"` on either side; the mismatch appears to have existed since both functions were
first written.

**Confidence hardcoding**: `git log -p --all -- core/brain/hypothesis_engine.py` shows
`"confidence": 0.7` present, unchanged, as a static literal in every version of this file since its
introduction — never computed, never derived from `_call()`'s output, never touched in any
subsequent commit. The prompt template itself never asked the LLM for a confidence value at all
(it requests `id, hypothesis_text, why_it_might_be_true, how_to_test, expected_evidence` — no
confidence field in that list). This is strong evidence 0.7 was a scaffolding placeholder, not a
deliberate design constant: nothing in the code, comments, or prompt ties it to any actual
assessment of the generated hypothesis's quality.

This conclusion is further supported by an established, already-existing convention elsewhere in
the *same* `core/brain/` package, for the *same class* of feature (LLM-driven proactive-insight
generation):

- `core/brain/anticipation.py:161` — prompt: `"Respond ONLY with JSON: [{\"need\": \"...\", ...,
  \"confidence\": 0.0-1.0}]"`; parsed at line 193: `confidence=float(item.get("confidence", 0.6))`.
- `core/brain/council.py:94` — `"confidence": raw.get("confidence", 0.75)`, parsed from the
  council LLM call's JSON response.

Both sibling modules ask the LLM to self-rate its own confidence and parse that value, with a safe
fallback default if the field is missing. `hypothesis_engine.py` was the only proactive/insight
module in this family *not* following that convention — its confidence was disconnected from the
LLM entirely.

The **0.85 storage gate itself** (`hypothesis_loop()`, unchanged by this task) is explicit,
documented (`"""Only surfaces insights with confidence > 0.85."""`), and consistent with its own
evident purpose — filtering proactive insights down to only the highest-confidence ones before
interrupting the owner with them. Nothing in code or history suggests this threshold is wrong;
what was wrong is that the generation side could never produce a value capable of clearing it.

---

## 4. Exact Fixes

### Fix 1 — key mismatch (`core/loop/autonomous_loop.py:2874`)

```python
# Before:
content = h.get("hypothesis", str(h)) if isinstance(h, dict) else str(h)
# After:
content = h.get("text", str(h)) if isinstance(h, dict) else str(h)
```

One line. Per Part 2's instruction to prefer correcting the consumer over renaming the producer's
established field: the producer's `"text"` key is proven canonical (§2.F/G above), so the consumer
was corrected to match it — not the other way around.

### Fix 2 — confidence hardcoding (`core/brain/hypothesis_engine.py`)

Three changes, all inside `generate_hypotheses()`'s existing method body and one new private
static helper — no change to the class's public interface, constructor, or any other method:

1. **Prompt**: appended one instruction asking the LLM to end its response with
   `"CONFIDENCE: <a number between 0.0 and 1.0>"` on its own final line — mirroring
   `anticipation.py`'s `"confidence": 0.0-1.0` phrasing, adapted from JSON-field to
   free-text-marker form since this engine's response format is prose, not JSON (changing that
   format itself would be a return-contract redesign — explicitly out of scope; see §8).
2. **New `_extract_confidence(content: str) -> tuple[str, float]`** (static method): regex-searches
   for `CONFIDENCE:\s*([0-9]*\.?[0-9]+)`, clamps to `[0.0, 1.0]`, and strips the marker out of the
   returned text so it doesn't leak into the human-facing hypothesis. If the marker is missing or
   malformed, returns the full content unchanged as `text` and a fallback confidence of `0.5` —
   deliberately *below* the 0.85 gate, so an unparseable response is safely suppressed rather than
   silently treated as high-confidence.
3. **`generate_hypotheses()`** now calls `text, confidence = self._extract_confidence(content)` and
   uses those two values in the returned dict instead of `content` and the literal `0.7`.

```python
_CONFIDENCE_RE = re.compile(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)

@staticmethod
def _extract_confidence(content: str) -> tuple[str, float]:
    match = _CONFIDENCE_RE.search(content)
    if not match:
        return content.strip(), 0.5
    confidence = max(0.0, min(1.0, float(match.group(1))))
    text = content[: match.start()].rstrip()
    return text, confidence
```

`SuggestionQueue.enqueue()` (called inside `generate_hypotheses()`, unchanged) now receives the
real parsed confidence instead of the old constant 0.7 — a strict improvement with no interface
change, since it already accepted a `confidence: float` parameter.

---

## 5. Confidence Semantics

Per Part 3's explicit branching (A. LLM-derived / B. evidence-calculated / C. fixed-by-design /
D. other): the evidence in §3 converges on **A — LLM-derived**, matching the established
`anticipation.py`/`council.py` convention already present in the same package. This is not a guess:
it is grounded in (1) git history proving 0.7 was never computed, (2) the prompt never having asked
for a confidence value, and (3) two sibling modules in the same file already implementing exactly
this pattern for the same category of feature.

**What was explicitly NOT done, per the task's constraints**:
- The 0.85 storage gate was **not** touched — no code or history evidence suggests it is
  incorrect, and Part 3 explicitly forbids weakening it "merely to make the test pass."
- No sophisticated confidence model was invented — the fix is one regex extraction of a number the
  LLM is asked to state directly, the same complexity class as `anticipation.py`'s
  `float(item.get("confidence", 0.6))`.
- The return-value contract (single dict vs. list of `count` per-hypothesis-scored entries) was
  **not** restructured — doing so (e.g. switching to strict per-hypothesis JSON, matching
  `anticipation.py`'s JSON-array pattern exactly) would have required redesigning
  `generate_hypotheses()`'s output shape, which is explicitly forbidden ("do NOT redesign
  HypothesisEngine"). The fix keeps one dict, one text blob, one shared confidence — unchanged
  shape, only the *values* inside it are now real.

**Fallback semantics**: on a missing/malformed marker, confidence defaults to `0.5` (not the old
`0.7`). This default was chosen deliberately conservative — it sits below the 0.85 gate, so a
response the code cannot confidently score is suppressed by default rather than risking a false
positive. Live verification (see §7) confirms this path actually engages in practice: a real,
unmocked LLM call during this task's testing returned a response without the marker, and the
engine correctly fell back to 0.5 without crashing.

---

## 6. Tests

All new tests added to the existing
`tests/integration/test_phase_a5_hypothesis_consumer.py` (no new test file — this repo's existing
convention groups hypothesis-pipeline tests in one file). Existing tests were strengthened in
place, not replaced or duplicated, per Part 4's instruction.

**Strengthened** — `TestHypothesisLoopActuallyExecutes.test_generate_hypotheses_is_actually_awaited`:
previously documented the key-mismatch bug as *current behavior* (`assert stored_kwargs["content"]
== str({...})`); now asserts the fixed behavior (`assert stored_kwargs["content"] ==
"test hypothesis"` and explicitly `!= str({...})`).

**New** — `TestHypothesisPipelineTextAndConfidenceContract` (6 tests, all executing the REAL
`HypothesisEngine` class with only the network call inside `HypothesisEngine._call` mocked — not a
stand-in `FakeEngine` — so these prove the actual producer/consumer contract, not just the
consumer's handling of an already-correct dict):

| Test | Part 4 item(s) | What it proves |
|---|---|---|
| `test_confidence_is_llm_derived_not_hardcoded` | 4 | Two different mocked LLM responses (0.92, 0.31) produce two *different* returned confidences, both ≠ the old constant 0.7 |
| `test_confidence_marker_stripped_from_stored_text` | 2, 3 | The `"CONFIDENCE: <n>"` marker does not leak into the stored/displayed hypothesis text |
| `test_confidence_parse_fallback_when_marker_missing` | 4 | A marker-less LLM response falls back to 0.5 (< 0.85), text unchanged |
| `test_real_engine_qualifying_hypothesis_reaches_stored_memory_as_text` | 1, 2, 3, 5, 8 | **The Part 2 required regression test.** Real engine → real `hypothesis_loop()` → stored memory `content` equals the actual hypothesis text (not `str(dict)`), stored `context["confidence"]` equals the LLM-emitted value (0.93), and the first `asyncio.sleep` call is still `4 * 3600` (cadence unchanged) |
| `test_real_engine_below_threshold_confidence_suppressed_end_to_end` | 6 | A genuinely low real-engine confidence (0.40) is still suppressed by the unchanged 0.85 gate, full pipeline |
| `test_real_engine_llm_failure_does_not_kill_loop` | 7 | A `_call()` exception is caught *inside* the real `generate_hypotheses()` (which returns `{"error": ...}` rather than raising) and `hypothesis_loop()` treats the resulting no-confidence dict as suppressed, not a crash — a different, complementary resilience path from the existing `FakeEngine`-raises test, which exercises `hypothesis_loop()`'s own `except` block instead |

Test-observation inputs in the new class use plain strings, not dicts, deliberately: the real
`generate_hypotheses()` logs `observation[:50]`, which raises on a dict. This is a separate,
pre-existing, out-of-scope type mismatch (`hypothesis_loop()` actually calls
`generate_hypotheses(context)` where `context` is a dict from `get_world_state()`) — see §8.

**Regression discovered while writing tests, dead-ended, not fixed**: a genuinely live,
network-connected self-test run of `core/brain/hypothesis_engine.py`'s own `__main__` block during
this task returned a real hypothesis with confidence correctly falling back to 0.5 (the LLM did not
include the marker in that particular response) — direct real-world confirmation that the fallback
path is reachable and safe, not just theoretically reachable in a mocked test.

---

## 7. Regression Results

```
NEW TESTS: 7/7             (1 strengthened assertion in an existing test +
                             6 new tests in TestHypothesisPipelineTextAndConfidenceContract)
HYPOTHESIS TESTS: 26/26    (tests/integration/test_phase_a5_hypothesis_consumer.py, full file)
FULL SUITE: 2171/2179 PASS (2208 collected, 29 skipped, 0 errors, 8 failures — obtained via
                            --junitxml, tests/unit + tests/integration, excluding
                            test_planning.py's 2 independently-pre-existing-broken
                            MissionPlanAdvisor-patch tests and 1 flaky timing test in
                            test_loop_stall_fixes.py, all three previously confirmed unrelated
                            to plans.py/autonomous_loop.py/hypothesis_engine.py)
PRE-EXISTING FAILURES: 8   (unchanged from 52_AUTONOMY_BLOCKER_REMEDIATION.md §8 — agent_registry
                            successor reconstruction, correction_learner domain classification ×4,
                            decision_engine epistemic scoring ×2, council red-tier verdict logic;
                            same 8 test names, individually re-confirmed unrelated to
                            hypothesis_engine.py or autonomous_loop.py this task)
NEW FAILURES CAUSED BY THIS CHANGE: 0
```

Before this task's changes, the same suite (same exclusions) ran 2202 collected / 2165 passed / 8
failed / 0 errors / 29 skipped (`52_AUTONOMY_BLOCKER_REMEDIATION.md` §8). This task added exactly 6
new collected tests (2208 − 2202) and exactly 6 new passes (2171 − 2165); failures, errors, and
skips are unchanged (8 / 0 / 29 in both runs) — the same 8 failing test names in both runs,
confirmed by diffing the two `short test summary info` failure lists.

All 24 test files that reference `autonomous_loop` anywhere in the repo were run explicitly (not
just the hypothesis file) — result: every one passes except the 2 pre-existing
`test_correction_integration.py` failures already in the confirmed-unrelated list (domain
classification `'general' != 'coding'`), which are unaffected by this task's changes.

`python -m py_compile` clean on both changed production files
(`core/brain/hypothesis_engine.py`, `core/loop/autonomous_loop.py`).

---

## 8. Remaining Limitations

- **Return-shape quirk (unfixed, out of scope)**: `generate_hypotheses()` still returns one dict
  for all `count` requested hypotheses combined into a single free-text blob, rather than a list of
  `count` independently-scored hypotheses — even though `hypothesis_loop()`'s own iteration logic
  (`for h in hypotheses if isinstance(hypotheses, list) else [hypotheses]`) is written as if a list
  were expected. Fixing this would require restructuring the prompt to strict per-hypothesis JSON
  and the return type to a list — a genuine redesign of `HypothesisEngine`'s output contract,
  explicitly forbidden by this task's scope.
- **`observation` type mismatch (unfixed, out of scope, newly confirmed this task)**:
  `hypothesis_loop()` calls `generate_hypotheses(context)` where `context =
  self._get_context().get_world_state()` is a dict, but `generate_hypotheses(observation: str, ...)`
  is typed and internally treated as a string (`observation[:50]` in its logging call, which raises
  `TypeError` on a dict). Because Python doesn't enforce type hints at runtime and the exception is
  caught by `generate_hypotheses()`'s own broad `except`, this doesn't crash the loop — it silently
  falls into the `{"error": ...}` return path every single time in production, meaning
  **`hypothesis_loop()` may currently never successfully reach a real LLM call at all** if
  `get_world_state()` genuinely returns a dict (not independently re-verified against the live
  `ContextEngine` this task, since doing so would mean touching `context_engine.py` — out of
  scope). This is a third, previously-undocumented defect in the same pipeline, discovered as a
  side effect of writing tests for this task. **Not fixed here** — fixing it would require deciding
  whether to change `get_world_state()`'s contract or `generate_hypotheses()`'s signature, either of
  which is a design decision touching code outside this task's stated file scope
  (`hypothesis_engine.py` + `hypothesis_loop()` only). Documented for a future, explicitly-scoped
  follow-up.
- **Marker-compliance is not guaranteed**: the `"CONFIDENCE: <n>"` instruction is a prompt request,
  not an enforced schema — a live test run during this task showed a real model response omitting
  it. The fallback (§5) handles this safely (suppression, not a crash or a false-high value), but
  it does mean the *rate* at which real hypotheses actually clear the 0.85 gate in production
  depends on how reliably the routed model follows a free-text instruction, which this fix cannot
  guarantee. A stricter JSON-schema approach would improve compliance but was explicitly avoided as
  a return-contract redesign (see above).

---

## 9. Experiment-Readiness Impact

Before this task: even with Blocker 1's `await` fix in place, the hypothesis pipeline could still
silently produce zero persisted hypotheses for two independent, compounding reasons (wrong storage
key; confidence permanently capped below the storage gate) — and, per the newly-discovered
`observation` type mismatch above, may never have successfully executed a real LLM call in the
first place.

After this task: the key mismatch is fixed and verified end-to-end with a real (non-fake) engine
instance; the confidence hardcoding is fixed and now genuinely varies with LLM output, verified
both in mocked tests and by one live, network-connected run. The newly-discovered `observation`
type mismatch remains open and is the most likely remaining reason the pipeline might still produce
no output in a live 7-day run — it is documented, not fixed, and explicitly flagged for a future,
narrowly-scoped follow-up rather than silently left unmentioned.

This task does not change the answer to whether VECTOR is ready for the actual 7-day experiment —
see the Final Verdict below and the unchanged scoping caveats in
`51_FINAL_COGNITIVE_INTEGRATION_AUDIT.md`.
