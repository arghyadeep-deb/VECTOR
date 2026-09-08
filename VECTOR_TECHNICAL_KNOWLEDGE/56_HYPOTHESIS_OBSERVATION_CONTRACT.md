# 56 — Hypothesis Observation Contract

**Date**: 2026-09-02
**Type**: FOCUSED FIX — resolves the one remaining potentially production-blocking defect flagged
(but not verified) by `55_HYPOTHESIS_PIPELINE_REMEDIATION.md` §8: whether `hypothesis_loop()`
passes a real-world-state object into `HypothesisEngine.generate_hypotheses()` that its own
`observation[:50]` logging slice can actually handle. Not a redesign of either `HypothesisEngine`
or `ContextEngine`.
**Scope**: one call site in `core/loop/autonomous_loop.py`'s `hypothesis_loop()`. No other
production file was touched — `core/brain/hypothesis_engine.py` and `core/loop/context_engine.py`
are unmodified by this task.

---

## 1. Actual Runtime Contract (verified with code evidence, not inferred)

**`ContextEngine.get_world_state(query: str | None = None) -> dict`** (`core/loop/context_engine.py:82`):
declared return type is `dict`. The method body has exactly one `return` statement
(line 126), a literal dict construction with 16 keys (`timestamp`, `time_of_day`, `owner`,
`recent_episodes`, `goal_summary`, `presence`, `screen_summary`, ...). There is no conditional path
that returns anything other than this dict — confirmed by reading the full method body, not just
its signature. A live call (`ContextEngine().get_world_state()`, timed during this task) returned
in 0.49s and `isinstance(state, dict)` was `True`.

**`HypothesisEngine.generate_hypotheses(observation: str, count: int = 3) -> dict`**
(`core/brain/hypothesis_engine.py:75`): declared parameter type is `str`. The method body treats
`observation` as text in three places: (1) interpolated directly into the prompt template
(`f"...{observation}..."`), (2) sliced for logging (`observation[:50]`), (3) stored verbatim in the
returned dict's `"observation"` field. None of these are dict-compatible operations — `observation[:50]`
in particular raises on a dict (see §4).

**Established callers of `get_world_state()`** (grepped across the full non-test and test codebase,
excluding the one under investigation):

| Caller | Usage pattern | Confirms dict? |
|---|---|---|
| `core/loop/decision_engine.py:458` | `c.context_snapshot = world_state` (opaque dict assignment) | Consistent with dict |
| `core/loop/planner.py:66-67` | `world.get("health", {}).get("energy_level", "high")` | Explicit dict `.get()` chain |
| `districts/chief_of_staff/chief_of_staff.py:269-272` | fallback `world_state = {}` on failure | Explicit dict |
| `districts/chief_of_staff/subconscious_loop.py:32,36` | `str(world_state)[:500]` embedded in an LLM prompt | Dict, explicitly stringified for text use |
| `core/mcp_tools/builtins.py:145-147` | `json.dumps(state, indent=2, default=str)` | Dict, explicitly JSON-serialized for text use |
| `core/loop/context_engine.py:300` (`session_hydration_prompt`, RULE 1) | `state['timestamp']`, `state.get("presence")`, etc. | Explicit dict key/`.get()` access throughout |
| 6+ test files (`test_ambient_perception.py`, `test_phase_b3_multimodal.py`, etc.) | direct `ContextEngine().get_world_state()` calls, dict assertions | Dict |

Every single established caller — six-plus in production code, several more in tests — treats the
return value as a dict. Two of them (`subconscious_loop.py`, `builtins.py`) go further and already
implement their own dict→string conversion specifically because they need to hand the world state
to something text-only (an LLM prompt and a JSON-string MCP tool response, respectively).

**Established callers of `generate_hypotheses()`** (grepped, excluding `hypothesis_loop()` itself):

| Caller | Argument passed |
|---|---|
| `core/brain/hypothesis_engine.py:145` (`__main__` self-test) | `"User tends to be more productive in the morning"` — a plain string literal |
| `core/benchmark/tasks/t06_proactive_cognition.py:73` | a plain string built from a hardcoded observation sentence, not from `get_world_state()` |

Both of the engine's other callers already pass a plain string. Neither derives its string from
`get_world_state()` — so no pre-existing conversion between these two specific functions exists
anywhere in the codebase (answering Part 1 item 7: no).

**Conclusion for items 1-7**: the return type is unambiguously and always `dict` (items 1-3, not
inferred from the type hint alone — verified against the method body and a live call). Every other
established caller of `get_world_state()` — six-plus production call sites plus tests — confirms
dict is the intended, working contract (item 4). `generate_hypotheses()` is genuinely intended to
accept a plain string, not the full world-state dict — its own signature, prompt template, and
internal string slice all agree, and its two other actual callers both already pass strings
(item 5, item 6). No existing code already bridges these two specific functions (item 7) — the
bridge needed to be written.

---

## 2. Call-Chain Trace

```
hypothesis_loop()                                    [autonomous_loop.py:2852]
  engine = self._get_hypothesis_engine()
  context = self._get_context().get_world_state()    ← returns dict, always (§1)
  hypotheses = await engine.generate_hypotheses(context)   ← BEFORE THIS FIX: raw dict passed
        │
        ▼
generate_hypotheses(observation: str, count=3)        [hypothesis_engine.py:75]
  prompt = f"...{observation}..."                      ← works with a dict too (str-interpolation
                                                           doesn't care about type) — NOT where it
                                                           broke
  content = await self._call(prompt, ...)              ← real LLM call — reached fine either way,
                                                           since the crash happens AFTER this
  text, confidence = self._extract_confidence(content) ← reached fine
  hypothesis = {..., "observation": observation, ...}  ← reached fine
  logger.info("...Generated hypothesis from: {}...", observation[:50])
        ↑ THIS is where a raw dict breaks: dict.__getitem__(slice(None,50,None))
          raises — see §4 for the exact exception, verified empirically.
  caught by generate_hypotheses()'s own broad `except Exception as e:` wrapping the WHOLE
  try block (including the logger.info + LLM call), which returns {"error": str(e)}
        │
        ▼
back in hypothesis_loop(): hypotheses = {"error": "slice(None, 50, None)"}
  for h in [hypotheses]:  # single dict, not a list
      confidence = h.get("confidence", 0.0)  → 0.0 (error dict has no "confidence" key)
      confidence >= 0.85 → False → suppressed, no crash, loop continues
```

The critical detail: the `observation[:50]` logging line sits **inside** the same `try` block as
the real `await self._call(...)` LLM call — so the exception it raises is caught by the *same*
`except` that would also catch a genuine LLM/provider failure, and produces an *identical*-shaped
`{"error": ...}` result. This is why the defect was silent and easy to miss: `hypothesis_loop()`
never crashes, never logs anything alarming beyond a routine-looking "low-confidence, suppressed"
debug line, and the failure is indistinguishable from an ordinary provider outage unless the error
string itself is inspected.

---

## 3. Classification: **B — CONTRACT MISMATCH, CALLER BUG**

`get_world_state()` intentionally and consistently returns structured context (a dict) — this is
its correct, working, multiply-confirmed contract, used successfully by six-plus other callers.
`generate_hypotheses()` intentionally and consistently expects a string observation — this is also
its correct, working contract, confirmed by its own signature, prompt logic, and its two other
actual callers. Neither producer nor consumer is wrong in isolation. The bug is entirely in
`hypothesis_loop()`, the one caller that fails to convert between the two — it is the only call
site in the entire codebase that hands `get_world_state()`'s dict directly to something expecting
a string.

This is not classification D (ambiguous): the evidence from six-plus independent callers on each
side converges without contradiction. There is no competing evidence suggesting `get_world_state()`
should return a string for this consumer, nor that `generate_hypotheses()` should accept a dict.

---

## 4. Root Cause

Empirically confirmed (not assumed) during this task: calling `some_dict[:50]` in Python 3.13
raises **`KeyError`**, not `TypeError` — a dict's `__getitem__` receives the `slice(None, 50, None)`
object as an ordinary (if unusual) key, looks it up, finds nothing, and raises `KeyError`. This was
directly observed twice: once via a standalone reproduction (`generate_hypotheses failed:
slice(None, 50, None)` in the logged error), and once via a dedicated test
(`test_get_world_state_returns_dict_confirming_the_contract`) that confirms `state[:50]` raises on
the real `ContextEngine.get_world_state()` output.

This is a plain producer/consumer mismatch introduced when `hypothesis_loop()` was written: whoever
wrote the `context = self._get_context().get_world_state()` line assumed (incorrectly, and without
precedent elsewhere in the codebase) that the engine's `observation` parameter could accept the raw
world-state dict directly.

---

## 5. Exact Fix

One call site, `core/loop/autonomous_loop.py`, inside `hypothesis_loop()`:

```python
# Before:
context = self._get_context().get_world_state()
hypotheses = await engine.generate_hypotheses(context)

# After:
context = self._get_context().get_world_state()
observation = str(context)[:500]
hypotheses = await engine.generate_hypotheses(observation)
```

Per Part 3's instruction to fix the boundary closest to the incorrect assumption rather than the
shared `ContextEngine` contract used by six-plus other consumers: the fix is entirely inside
`hypothesis_loop()`. Neither `get_world_state()` nor `generate_hypotheses()`'s signature, return
shape, or internal logic was touched.

The `str(world_state)[:500]` conversion is **not a new serialization format** — it is the exact
convention `districts/chief_of_staff/subconscious_loop.py:36` already uses for the same purpose
(turning `get_world_state()`'s dict into text for an LLM prompt, in another proactive/insight-style
loop). The 500-character budget matches that precedent exactly, rather than picking an arbitrary
new number. (`core/mcp_tools/builtins.py`'s `json.dumps(..., default=str)` was the other candidate
convention found, but it serves a different purpose — a structured, machine-readable string for an
external MCP tool response — not a text summary meant to be read as prose inside an LLM prompt,
which is what `hypothesis_loop()` needs; `subconscious_loop.py`'s convention is the closer match.)

**Preserved, unchanged, per the fix constraints**:
- `generate_hypotheses()`'s return shape, confidence parsing, and the 0.85 storage gate — untouched
  (verified: `_extract_confidence` and the gate check in `hypothesis_loop()` are byte-identical to
  before this task).
- Routing/model/provider selection — untouched (the live verification in §7 shows the same
  groq→deepseek→mistral fallback chain as before this task, unaffected).
- The 4-hour cadence — untouched (verified: `sleep_calls[0] == 4 * 3600` in the new tests, and the
  live check in §7 logged exactly one `sleep(14400)` call).
- Existing error handling — untouched (`hypothesis_loop()`'s `except asyncio.CancelledError` /
  `except Exception` blocks are unmodified).
- No new persistence schema — none introduced.

---

## 6. Behavioral Tests

Added to `tests/integration/test_phase_a5_hypothesis_consumer.py`, new class
`TestHypothesisObservationContract` (4 tests). Per Part 4's explicit requirement, none of these use
a `FakeEngine` for the core boundary — they instantiate the real `HypothesisEngine`, and three of
the four also instantiate the real `ContextEngine` (only `HypothesisEngine._call`, the actual
network/provider boundary, is mocked):

| Test | Part 4 item(s) | What it proves |
|---|---|---|
| `test_real_world_state_reaches_real_engine_as_string_and_is_stored` | 1, 2, 3, 4, 5, 6, 10 | Real `ContextEngine().get_world_state()`'s dict flows through real `hypothesis_loop()` → real `generate_hypotheses()` → `_call()` is actually reached (proving no crash on `observation[:50]`) → the captured prompt contains real world-state content (`"time_of_day"`/`"timestamp"`) → a qualifying (0.91) result is stored as plain text (not `str(dict)`) → the 4h cadence sleep value is unchanged |
| `test_real_world_state_below_threshold_confidence_still_suppressed` | 8 | With the real observation-conversion boundary in place, a genuinely low real-engine confidence (0.35) is still suppressed by the unchanged 0.85 gate |
| `test_real_world_state_llm_failure_remains_contained` | 9 | With the real observation-conversion boundary in place, a `_call()` provider failure is caught inside the real `generate_hypotheses()` and does not propagate to kill `hypothesis_loop()` |
| `test_get_world_state_returns_dict_confirming_the_contract` | — (Part 1 evidence) | Direct, standalone proof that `get_world_state()` returns a real dict and that slicing it raises — the exact premise this fix depends on |

Two pre-existing tests were updated (not replaced) because they referenced the old code path by
name/exact-string:
- `test_hypothesis_loop_source_awaits_generate_hypotheses` (static source-text guard) — updated to
  match the renamed local variable (`observation` instead of `context` as the argument to
  `generate_hypotheses`).
- `test_real_engine_qualifying_hypothesis_reaches_stored_memory_as_text` and 2 sibling tests from
  `55_HYPOTHESIS_PIPELINE_REMEDIATION.md`'s work (in `TestHypothesisPipelineTextAndConfidenceContract`)
  already used plain-string `mock_context.get_world_state.return_value` values as a workaround for
  this exact defect (documented at the time as "a separate, pre-existing, out-of-scope dict/str
  mismatch bug") — left unchanged, since they intentionally isolate the confidence/key-contract
  question from this observation-contract question; both sets of tests are complementary, not
  duplicates.

**Full file result**: 30/30 pass (24 pre-existing/previously-added + 4 new + 2 updated-in-place =
matches exactly 26 (previous session total) + 4 new = 30).

---

## 7. Live Verification

Per Part 5, one real, fully non-mocked run was executed through the corrected production boundary
— real `ContextEngine`, real `HypothesisEngine`, real provider call (only `EpisodicMemory.store`
was stubbed, to avoid writing a throwaway row from a diagnostic script, and `asyncio.sleep` was
patched to skip the real 4h wait — the same technique the automated tests use).

Observed, in order:
1. `get_world_state()` executed successfully, returning a dict (confirmed by the process not
   crashing at that line).
2. `hypothesis_loop()`'s outer sleep fired once at `14400` seconds (`4 * 3600`) — cadence confirmed
   live, not just in a mocked test.
3. The real provider fallback chain ran normally: `groq` (HTTP 404, model not found) →
   `deepseek` (HTTP 402, insufficient balance) → `mistral` (`ministral-3b-2512`, succeeded) —
   unaffected by this fix, confirming no routing change.
4. `HypothesisEngine.generate_hypotheses()`'s own log line fired successfully:
   `"Generated hypothesis from: {'timestamp': '2026-09-02T01:25:16.254455', 'time_..."` — this is
   the exact `observation[:50]` slice that would have raised `KeyError` on a raw dict (§4). Its
   successful execution, printing the first 50 characters of the *stringified* world-state dict, is
   direct, unambiguous proof the fix works on the real production path, not just in a test double.
5. Confidence parsing engaged: the live LLM response in this run did not include a parseable
   `CONFIDENCE:` marker, so the engine correctly fell back to `0.5` (per
   `55_HYPOTHESIS_PIPELINE_REMEDIATION.md`'s documented fallback semantics).
6. Storage/suppression behaved correctly: `hypothesis_loop()` logged
   `"[VECTOR][hypothesis] Low-confidence insight suppressed (conf=0.50)"` and did not call
   `memory.store()` — the correct outcome for a sub-0.85 result, and not a crash.

Per Part 5's explicit instruction, no attempt was made to force a high-confidence result
deterministically — the purpose was to prove the boundary and call path, which it does.

---

## 8. Regression Results

`python -m py_compile` clean on `core/loop/autonomous_loop.py` and the modified test file.

All 24 test files in the repo that reference `autonomous_loop`, `get_world_state`, or
`ContextEngine` anywhere were run explicitly (30+ files, batched). Result: the only failures are
the same 4 of the 8 already-confirmed-pre-existing, unrelated failures that happened to fall inside
this batch (`test_correction_integration.py` ×2, `test_epistemic_integration.py`'s unit variant ×1,
`test_epistemic_scoring.py` ×1) — all previously traced to `correction_learner.py`'s domain
classification and `decision_engine.py`'s epistemic scoring, neither touched by this task.

```
NEW FAILURES CAUSED BY THIS CHANGE: 0
PRE-EXISTING FAILURES: 8   (full-suite baseline, unchanged from
                            52_AUTONOMY_BLOCKER_REMEDIATION.md / 55_HYPOTHESIS_PIPELINE_
                            REMEDIATION.md — agent_registry successor reconstruction,
                            correction_learner domain classification ×4, decision_engine
                            epistemic scoring ×2, council red-tier verdict logic)
```

Full-suite `--junitxml` run (`tests/unit` + `tests/integration`, same exclusions as the two prior
remediation tasks — `test_planning.py`'s 2 independently-broken `MissionPlanAdvisor`-patch tests
and 1 flaky timing test in `test_loop_stall_fixes.py`) confirms the same 8 pre-existing failures,
zero new ones, and exactly 4 additional collected/passed tests over the
`55_HYPOTHESIS_PIPELINE_REMEDIATION.md` baseline (2208 → 2212 collected, 2171 → 2175 passed),
matching the 4 new tests added this task.

---

## 9. Remaining Limitations

- **Marker-compliance is still not guaranteed** (unchanged from `55_HYPOTHESIS_PIPELINE_
  REMEDIATION.md` §8) — the live verification run in §7 is itself an example: the real model's
  response didn't include the `CONFIDENCE:` marker, so it fell back to 0.5 and was suppressed. This
  is expected, documented, safe behavior, not a defect — but it does mean not every real hypothesis
  generation cycle will produce a storable result, independent of this task's fix.
- **`hypothesis_loop()` does not call `session_hydration_prompt()` (RULE 1)** — noticed while
  tracing the call chain for this task, but out of scope: `HypothesisEngine._call()` builds its own
  system/user messages directly rather than going through `ContextEngine.session_hydration_prompt()`,
  which is the codebase's official RULE 1 mechanism ("Call this before EVERY LLM call") and is
  itself a third, different dict→string world-state conversion (a purpose-built prompt-context
  builder, richer than the simple `str(dict)[:500]` used here). This task's fix deliberately did
  NOT switch to `session_hydration_prompt()` — doing so would mean passing extra context params,
  changing what text actually reaches the LLM in `generate_hypotheses()`'s system+user messages,
  and arguably redesigning part of `HypothesisEngine._call()`'s prompt construction, all of which
  are explicitly out of scope ("DO NOT redesign HypothesisEngine", "DO NOT broaden this into a
  general cognitive audit"). Documented as a known, pre-existing, unrelated RULE 1 gap for a future,
  separately-scoped task.
- **500-character truncation may drop useful world-state fields** for a dict this large (16 keys) —
  inherited directly from the `subconscious_loop.py` precedent this fix reused, not a new choice.
  Whether 500 characters is the "right" budget for hypothesis generation specifically was not
  evaluated — that would be a tuning/design question, not a contract-correctness one, and is out of
  this task's scope.

---

## 10. Experiment-Readiness Impact

Before this task: `55_HYPOTHESIS_PIPELINE_REMEDIATION.md` correctly flagged, but had not
independently verified, that `hypothesis_loop()` might never reach a real LLM call in production at
all, due to an unconfirmed dict/str mismatch at the `get_world_state()` → `generate_hypotheses()`
boundary.

After this task: independently verified (not just documented as a risk) via direct code tracing,
new behavioral tests using the real `ContextEngine` and real `HypothesisEngine`, and one live,
fully non-mocked run through the actual fixed production boundary. The mismatch was real
(Classification B, confirmed), and is now fixed with the smallest possible change at the correct
boundary, reusing an established codebase convention rather than inventing a new one.

Combined with `52_AUTONOMY_BLOCKER_REMEDIATION.md`'s `await` fix and
`55_HYPOTHESIS_PIPELINE_REMEDIATION.md`'s key/confidence fixes, the hypothesis pipeline's three
known execution-blocking defects (never awaited; wrong storage key + permanently-capped confidence;
observation type mismatch) are now all fixed and each individually behaviorally verified. This does
not by itself constitute 7-day-experiment readiness — see the unchanged scoping caveats in
`51_FINAL_COGNITIVE_INTEGRATION_AUDIT.md` and the RULE 1 gap noted in §9 above, which remains open.
