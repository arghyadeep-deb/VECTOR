# Task 88 — R1 Runtime Boundary Remediation Report

**Scope: exactly one change** — bound `_multi_backend_fallback()`'s previously-ignored `timeout`
parameter, per `VECTOR_TECHNICAL_KNOWLEDGE/87_RECONCILED_REWARD_LOOP_REMEDIATION_SPEC.md`'s R1
specification (§28). R2 through R10, HP shaping, successor lifecycle, `TrustLadder`, `GOAL_ACTION_MAP`,
goals, PolicyMemory, event fanout, epistemic systems, and understanding systems were **not**
touched. The live Segment-2 process (PID 37588) was **not** started, stopped, signaled, or
interacted with in any way — confirmed still running, untouched, throughout this task (see §15).

---

## 1. Exact pre-fix defect

`core/inference/ollama_safe.py::_multi_backend_fallback(model, messages, timeout, *, caller_id)`
accepted a `timeout: float` parameter and **never referenced it anywhere in the function body**. A
grep for the literal string `timeout` inside the pre-fix function returned zero matches. All three
fallback engine calls —

```python
LiteLLMEngine().generate(fallback_messages, model=litellm_model, max_tokens=2048)
AppleFMEngine().generate(fallback_messages, model=model, max_tokens=2048)
GemmaCppEngine().generate(fallback_messages, model=model, max_tokens=2048)
```

— passed no timeout, no deadline, and were wrapped in no circuit breaker (unlike the primary
Ollama call in `chat()`, which is wrapped in `_wrap_with_circuit_breaker("ollama", _call)`). This
function is reached from three call sites inside `chat()` (lines 269, 314, 325 pre-fix — semaphore-
acquire-timeout, circuit-breaker-open, and general-exception branches), and `chat()` itself is
called **synchronously from `async def` functions** at `Governor._llm_classify()`
(`governor.py:1655`, reached from `route_task()` inside `async def dispatch()`) and
`AgentBase.vchat()` (`agent_base.py:335`), both of which sit on VECTOR's highest-volume path (the
district event-fanout/dispatch pipeline). A hang inside any of the three fallback engines therefore
had no upper bound and could block the event-loop thread indefinitely.

---

## 2. Engine signature inspection results

Read in full this session, before writing any code (Step 0), exactly as instructed:

| Engine | File | `generate()` signature | Genuinely honors a `timeout=` kwarg? |
|---|---|---|---|
| `LiteLLMEngine` | `vectorcode/src/vc_engine/litellm.py:45` | `generate(self, messages, *, model, temperature=0.7, max_tokens=1024, **kwargs)` — `**kwargs` is merged into `call_kwargs` and forwarded to `litellm.completion(**call_kwargs)` | **Plausibly yes**, via pass-through to `litellm.completion()`, which per LiteLLM's own documented API does accept a `timeout` parameter — but this session could not empirically verify litellm's exact runtime behavior without installing/executing it, which is out of scope. Not relied upon (see §3). |
| `AppleFMEngine` | `vectorcode/src/vc_engine/apple_fm_shim.py` | **Does not exist.** This file has no `class AppleFMEngine` at all — it is a standalone FastAPI *server* module (`app = FastAPI(...)`, meant to be run via `uvicorn vector.engine.apple_fm_shim:app --host ... --port ...` as a separate process) exposing `/v1/chat/completions`. | N/A — irrelevant. `_multi_backend_fallback`'s existing `from ...apple_fm_shim import AppleFMEngine` already raises `ImportError` on **every** platform, not just non-macOS, today, independent of this fix. Caught by the pre-existing broad `except Exception`, so this branch has always been a silent no-op in practice. **This is a genuine, unexpected finding — see §13. Not fixed, per this task's explicit scope (`core/inference/ollama_safe.py` only).** |
| `GemmaCppEngine` | `vectorcode/src/vc_engine/gemma_cpp.py:95` | `generate(self, messages, *, model, temperature=0.7, max_tokens=1024, **kwargs)` — `**kwargs` is accepted but **never forwarded anywhere inside the method body**; the actual blocking call is `self._gemma.completion(prompt)` (a synchronous pybind11 native call into `pygemma`), invoked with no kwargs at all. The method's own comment confirms: *"pygemma v0.1.3 completion() does not accept temperature/max_tokens; these params are accepted in the signature for ABC compliance but not forwarded."* | **No.** A `timeout=` kwarg passed to this `generate()` would be silently absorbed into `**kwargs` and have zero effect — the exact same "accepted at a boundary, silently discarded" defect shape as the bug being fixed. |

**Conclusion from this inspection, decisive for the implementation choice in §3:** support for
`timeout=` is not uniform across the three engines (one plausible-but-unverifiable, one moot due to
an unrelated pre-existing bug, one confirmed non-functional despite accepting the kwarg). Per the
task's explicit rule — *"If one or more engines do NOT support timeout: do NOT invent an unsupported
keyword argument. Use the smallest appropriate hard-deadline mechanism"* — no `timeout=` kwarg was
added to any of the three `.generate()` calls.

### Existing tests inspected

`tests/unit/test_ollama_semaphore_timeout.py` (KNOWN_ISSUES #0 Part 1 — the semaphore-acquire
bound) was read in full. It establishes the codebase's existing convention for this exact class of
test: real `time.monotonic()` timing assertions against a small configured bound, `monkeypatch` used
to isolate the measurement to the mechanism under test (e.g. stubbing `_multi_backend_fallback`
itself to isolate the semaphore's own timing), module-level imports inside test functions, and
`pytestmark = pytest.mark.unit`. This session's new test file (§6) follows the same convention.
`tests/unit/test_ollama_concurrency.py` and `tests/unit/test_inference_observability_gaps.py` were
also identified and run (§7) as the closest existing regression coverage for this module.

---

## 3. Exact implementation chosen and why

**Chosen: wrap the existing, unmodified three-engine sequential attempt in a dedicated
single-worker `concurrent.futures.ThreadPoolExecutor`, and bound `_multi_backend_fallback()`'s
*wait* on that worker to `timeout` seconds via `Future.result(timeout=timeout)`.**

- **Not `asyncio.wait_for`** — explicitly prohibited by the task, and structurally wrong regardless:
  `_multi_backend_fallback` is a synchronous function that may be invoked from a thread with no
  running event loop (it is called from `chat()`, itself often called synchronously from worker
  contexts).
- **Not per-engine `timeout=` kwargs** — rejected per §2's finding that support is non-uniform, and
  passing an unhonored kwarg to `GemmaCppEngine.generate()` would create a false sense of safety for
  that specific engine while changing nothing.
- **Not touching `Governor._llm_classify()` or `AgentBase.vchat()`** — explicitly deferred follow-up
  work per the task; this fix operates entirely inside the one function named in the task's
  objective.
- **A fresh, single-worker executor is created per call, not a shared pool.** This was a deliberate
  choice beyond the task's minimum requirement, to avoid a new, different unbounded-risk: a shared
  pool could be exhausted by accumulated stuck workers across many calls, silently reintroducing an
  unbounded wait for a *later*, independent caller queued behind a full shared pool. A per-call
  executor means a stuck call can leak at most its own one thread, never blocks a different call's
  executor.
- **`executor.shutdown(wait=False)` in a `finally` block, on both the success and timeout paths.**
  This was the single most important correctness detail in the implementation: using
  `with ThreadPoolExecutor() as ex:` would have called `shutdown(wait=True)` on exit, which
  **blocks until the worker thread actually finishes** — silently reintroducing exactly the
  unbounded wait this fix exists to remove. `wait=False` returns immediately regardless of whether
  the worker is still running.

### Code structure

The pre-existing three-engine sequential body (LiteLLM → Apple FM → Gemma C++, unchanged
byte-for-byte in its internal logic, try/except structure, and logging) was extracted verbatim into
a new top-level function, `_attempt_all_fallback_engines(model, fallback_messages, *, caller_id)`.
`_multi_backend_fallback()` now: converts messages (unchanged, synchronous, outside the bound —
matching its original position before any engine is attempted), submits
`_attempt_all_fallback_engines` to a fresh `ThreadPoolExecutor(max_workers=1)`, and returns
`future.result(timeout=timeout)`, catching `TimeoutError` (Python 3.11+: identical to
`concurrent.futures.TimeoutError`, confirmed via `concurrent.futures.TimeoutError is TimeoutError
== True` in this environment) to log a warning, record one honest observability entry (§5), and
return `""` — the pre-existing total-failure contract, unchanged.

---

## 4. Files modified

| File | Nature of change |
|---|---|
| `core/inference/ollama_safe.py` | The **only** production file modified. `_multi_backend_fallback()` restructured as described above; new top-level helper `_attempt_all_fallback_engines()` added (extracted, not rewritten, from the pre-fix function body). +214 / −13 lines (per `git diff --stat`). |
| `tests/unit/test_ollama_multi_backend_fallback_timeout.py` | New test file (§6). |
| `VECTOR_TECHNICAL_KNOWLEDGE/88_R1_RUNTIME_REMEDIATION_REPORT.md` | This report. |

No other production file was touched. `git status`/`git diff --stat` were checked explicitly to
confirm this — the repository has a number of **pre-existing, unrelated uncommitted changes** from
before this session (visible in `git status`, e.g. `.claude/rules/phase_status.md`,
`core/city/governor.py`, and many others); none of those were created, modified, or touched by this
task, and none were staged, committed, or discarded.

---

## 5. Invariants preserved

Verified against the task's explicit list of 15 semantic requirements, plus its own restated
"critical semantic requirements":

1. **Same fallback engine order** — LiteLLM → Apple FM → Gemma C++, unchanged (verified by test,
   §6).
2. **Same successful return behavior** — a fast-succeeding engine's text is returned exactly as
   before (verified by test).
3. **Total-failure `return ""`** — unchanged for both "all engines cleanly failed" and "the deadline
   was hit" (verified by test).
4. **Existing exception/failure handling** — each engine's own `try/except Exception` block is
   byte-for-byte unchanged inside `_attempt_all_fallback_engines`; an exception in one engine still
   falls through to the next, exactly as before.
5. **`caller_id` observability** — unchanged for the success path (each engine's own
   `_record_observability` call, with the real `caller_id`, is untouched); a new, additional
   observability record is added *only* on the timeout path (§5 of the spec explicitly permitted
   this, using pre-existing free-text `status`/`error_kind` columns, no schema change).
6. **Provider-selection logic** — untouched; no engine was reordered, added, or removed.
7. **Ollama semaphore** — `_OLLAMA_SYNC_SEMAPHORE`, its bounded `acquire(timeout=...)`, and its
   `finally: release()` are entirely outside the function this task modified and were not read for
   modification, only for context (§0).
8. **No coroutine-level timeout added** — nothing in `autonomous_loop.py`'s 21 coroutines was
   touched; `hypothesis_loop` (explicitly named in Task 87 as a *different*, deferred fix) was not
   modified.
9. **Fanout untouched** — `core/event_bus/wiring.py`, `_fanout_handler`, `Governor.dispatch` were
   not read for modification and were not changed.
10. **Goals untouched** — `core/brain/goal_system.py` was not modified.
11. **PolicyMemory untouched** — `core/memory/policy.py` was not modified.
12. **Permissions/governance untouched** — `PermissionGateway`, `core/config.py`'s tier lists,
    `TrustLadder` were not modified.
13. **No persistent state added** — the new observability record uses the pre-existing
    `inference_calls` table's existing, unmodified schema (`status TEXT`, `error_kind TEXT`, both
    free-text columns with no `CHECK` constraint, confirmed by reading
    `core/metering/inference_observability.py`'s schema and `record()` signature before writing any
    code) — no migration, no new table, no new column.
14. **Experiment configuration untouched.**
15. **Live Segment-2 process untouched** — confirmed still running (PID 37588) both before and after
    this task's work, never signaled, attached to, or interacted with (§15).

---

## 6. Tests added/changed

New file: `tests/unit/test_ollama_multi_backend_fallback_timeout.py` — 8 tests (7 assertion tests +
1 helper). All mock every fallback engine at its real import location
(`vectorcode.src.vc_engine.litellm.LiteLLMEngine`,
`vectorcode.src.vc_engine.apple_fm_shim.AppleFMEngine` — patched with `raising=False` since, per §2,
no such attribute exists in real source today — and `vectorcode.src.vc_engine.gemma_cpp.GemmaCppEngine`),
so **no real network call, model load, or subprocess is ever reached**, per the task's explicit
"Testing Safety" requirement and in deliberate avoidance of the Task-58A "stale mock" incident (two
real process launches during testing before mocking was complete).

| Test | Purpose | Matches task requirement |
|---|---|---|
| `test_bounded_wait_when_every_engine_hangs` | The mocked LiteLLM engine blocks on a `threading.Event` (released only by the test, never by a fixed sleep) for up to 30s; asserts `_multi_backend_fallback` returns within `6×` the configured 0.3s deadline. | **TEST 1 — BOUNDED BLOCKING** |
| `test_fallback_order_preserved_on_success` | LiteLLM succeeds immediately; asserts Apple FM and Gemma are never even attempted (short-circuit-on-success, matching pre-fix behavior) and the returned text is exact. | **TEST 2 — SUCCESS REGRESSION** |
| `test_fallback_order_falls_through_on_failure` | LiteLLM and Apple FM fail, Gemma succeeds; asserts all three run in the documented order and the correct final text is returned. | Order regression (explicit task requirement) |
| `test_total_failure_returns_empty_string` | All three engines fail cleanly (not a timeout); asserts `""`. | Total-failure contract |
| `test_timeout_recorded_honestly_in_observability` | On a genuine deadline hit, asserts exactly one observability record is written, with the real `caller_id`, empty `content` (never fabricated), and `status="timeout"` distinct from the ordinary `status="error"` used elsewhere — using the pre-existing free-text schema, no migration. | **TEST 3 — FAILURE/OBSERVABILITY REGRESSION** |
| `test_caller_id_reaches_a_successful_engine_record` | Ordinary success path still records the real `caller_id` through to the per-engine observability call. | `caller_id` invariant (§5 item 5) |
| `test_no_asyncio_wait_for_used_and_function_stays_synchronous` | Guards against a future regression reintroducing `asyncio.wait_for(` (call, not the docstring's prose mention of the name) or `await ` inside this synchronous function. | Explicit task prohibition on `asyncio.wait_for` |

---

## 7. Test results

**New R1 tests:** `python -m pytest tests/unit/test_ollama_multi_backend_fallback_timeout.py -v`
→ **7 passed**, 0 failed, 5.05s. (One test needed one iteration: the guard test's first draft
matched the docstring's own prose explanation of *why* `asyncio.wait_for` is not used; corrected to
check for the literal call `asyncio.wait_for(` rather than the bare substring, then passed.)

**Existing regression tests** (the closest, most directly relevant pre-existing coverage):
`python -m pytest tests/unit/test_ollama_semaphore_timeout.py tests/unit/test_ollama_concurrency.py
tests/unit/test_inference_observability_gaps.py -v` → **25 passed**, 0 failed, 8.69s. Zero
regressions in the semaphore-timeout suite (which itself stubs `_multi_backend_fallback` to isolate
its own measurement — confirming that suite's own isolation still holds against the restructured
function) or the concurrency/observability suites.

---

## 8. Full-suite comparison against baseline

**Baseline** (per the task): ~2212 collected, 2175 passed, 8 pre-existing failures, 0 errors, 29
skipped.

`python -m pytest tests/ -q --timeout=300` was launched in the background for the full comparison.
[**FILL-IN AT PUBLICATION TIME** — see the exact figures appended at the end of this report /
reported separately in the final response if the run had not completed at the time this document
was first written. No pre-existing failure was targeted for a fix, per the task's explicit
instruction not to "fix" unrelated pre-existing failures — this task's own new/changed tests are
counted separately from that baseline and are not expected to appear in it.]

Static checks: no repository-wide linter/type-checker invocation was found configured as a single
"run this" command distinct from the test suite itself in the portion of the repository inspected
for this task; none was run beyond `python -c "import ast; ast.parse(...)"` (confirmed valid syntax
immediately after the edit) and the successful, warning-free module import already exercised by
every test above.

---

## 9. Disposable-clone behavioral proof

**Method chosen, and why it differs in form (not in substance) from "boot a second full
`run_vector.py loop` process":** the task's own R0 diagnostic design (Task 87 §6) specifies enabling
`VECTOR_THREAD_DUMP_SEC` and inspecting `data/logs/thread_dumps.log` on a disposable clone. Standing
up a second complete VECTOR process (its own config, its own attempt to bind ports, its own
`bootstrap_agents()`, its own database) is disproportionate risk and complexity for verifying one
function's timing behavior, and — more importantly — would not actually change what is being
measured: the question is whether a thread executing inside `_multi_backend_fallback` is captured by
`faulthandler.dump_traceback_later` while blocked, and whether that frame persists past the
deadline. This session instead built a small, self-contained, fully isolated diagnostic script that:

- sets `VECTOR_TEST_DATA_DIR` to a freshly created `tempfile.mkdtemp()` directory (never touching
  the real `data/` directory or its live database),
- calls the repository's own, real, unmodified `core.loop.thread_dump.enable_if_requested()`
  (the exact `VECTOR_THREAD_DUMP_SEC` mechanism named in the task) with a 1-second dump interval,
- replaces `vectorcode.src.vc_engine.litellm.LiteLLMEngine` with a mock that blocks on a
  `threading.Event` (never a real network call),
- calls the real, post-fix `ollama_safe._multi_backend_fallback()` with a 2.0-second deadline
  against that permanently-hanging mock, from a background thread, and
- inspects the resulting `thread_dumps.log` for frames inside the fallback path, both while the call
  is in flight and after it has already returned to its caller.

This is a genuinely isolated, disposable, no-mock-of-the-mechanism-under-test run — no live process,
no live database, no real provider, no real subprocess — and it exercises the actual repository
diagnostic tool named in the spec, not a substitute.

### 9.1 Result

```
[diag] calling _multi_backend_fallback() with a 2.0s deadline against a permanently-hanging engine...
[diag] _multi_backend_fallback returned '' after 2.04s wall clock (deadline was 2.0s)
[diag] non-main threads still alive after return: ['ThreadPoolExecutor-1_0']
```

The bound held: the caller returned at 2.04s against a 2.0s configured deadline — a ~2% overshoot
consistent with normal scheduling/dump-interval jitter, not an unbounded wait.

`data/logs/thread_dumps.log` (in the isolated temp directory) captured, in **three consecutive
1-second dumps**, the worker thread's real Python stack:

```
Thread 0x0000cc40 (most recent call first):
  File "...\r1_thread_dump_diagnostic.py", line 54 in generate
  File "...\core\inference\ollama_safe.py", line 676 in _attempt_all_fallback_engines
```

**Two facts, both directly observed, not inferred:**

1. **The dump correctly captured the thread genuinely blocked inside the fallback path** at the
   exact call site expected (`_attempt_all_fallback_engines` → the mocked engine's `generate()`),
   confirming the diagnostic mechanism itself works and is capable of catching this class of block.
2. **That same thread — same identity, same frame — was still present in dumps taken *after* the
   caller had already returned** (the 2.04s-elapsed return was logged before the second and third
   of the three dumps showing this frame). This is direct, observed evidence of the documented
   residual limitation (§12): the *wait* is bounded, the underlying worker is not cancelled and
   continued running, blocked, for at least ~2 more seconds after its caller had already moved on
   with an honest `""` result. The worker only unblocked because the test explicitly released it at
   the very end (in a genuine, unmocked hang, it would not).

---

## 10. Thread-dump result

Covered in §9.1 above in full. Summary: **frames inside the fallback path were captured while
blocked (yes)**; **a frame inside the fallback path persisted beyond the configured 2.0s bound
(yes, confirmed for at least ~2 additional seconds in this run)**; the calling thread itself was
not captured stuck in the same location in any dump taken after its 2.04s return — it had genuinely
moved on.

---

## 11. Historic starvation attribution

Per the task's required scale:

**PROVEN:** the `timeout` parameter is now enforced/bounded. Confirmed by (a) the unit test suite
(§6/§7 — a mocked, indefinitely-hanging engine no longer blocks the caller past a small multiple of
the configured deadline) and (b) the independent, isolated thread-dump diagnostic (§9), which
observed the actual bound holding in real wall-clock time against a real (mocked) blocking call,
using the repository's own diagnostic instrumentation, not a self-reported timer alone.

**UNKNOWN → remains UNKNOWN, not upgraded:** whether this specific defect explains the historic
69.9-hour `hypothesis_engine` inference-call anomaly recorded in `data/telemetry.db`
(`inference_calls` row with `latency_ms=251,520,681`, `status=error`, first identified in Task 84
§9.1). This task's diagnostic proves the *mechanism* (an unbounded synchronous fallback call can
block a thread indefinitely, and the fix bounds it) is real and now closed — it does **not**
establish, and does not attempt to establish, that the historic 69.9-hour call specifically passed
through `_multi_backend_fallback` rather than hanging somewhere else in the call chain (e.g., inside
`hypothesis_loop`'s own unguarded `await`, a separate, still-open, explicitly-deferred issue per
Task 87). No live-process evidence was or could be gathered this session (the live process, PID
37588, was never interacted with), and no attempt was made to reproduce the exact historic hang
against the live system. Consistent with Task 87 §5.3's classification, this remains **PROVEN as a
defect, LIKELY as a contributing explanation for the historic anomaly, UNKNOWN as a confirmed sole
cause.** This report does not upgrade that classification merely because the unit tests and the
isolated diagnostic both passed.

---

## 12. Residual worker/cancellation limitation

**Documented in three places, deliberately, so this cannot be missed by a future reader:** the
function's own docstring (in `core/inference/ollama_safe.py`), the log line emitted at the moment a
timeout actually occurs, and this report (§9.1, §3).

**Exact statement:** `Future.result(timeout=...)` bounds how long `_multi_backend_fallback()`
*waits* for `_attempt_all_fallback_engines` to finish. It does **not** terminate that function if it
is still running when the deadline is reached — Python threads cannot be forcibly killed. If the
worker is inside a blocking network call (`litellm.completion(...)`) or a blocking native call
(`self._gemma.completion(prompt)`) when the deadline fires, that call continues running, on its own
thread, until it finishes on its own or the process exits. Its eventual result (success or
exception) is silently discarded — nothing is listening for it anymore. This was directly observed
in this session's own diagnostic run: the mocked engine's completion (once released) produced a
real log line (`fallback: litellm -> vector-fast`) roughly 1.3 seconds *after* the caller had
already returned `""` to its own caller.

**Consequences, stated plainly, not solved by this task (correctly out of scope per the task's own
"do not expand scope to solve worker termination" instruction):**
- A process that repeatedly hits this deadline against a genuinely-hanging backend will accumulate
  abandoned, still-running worker threads (one per timed-out call) until each one eventually
  finishes or the process exits. Each call's executor is independent (§3), so this cannot exhaust a
  *shared* pool and block an unrelated *later* call — but it is still a real, unbounded-in-count (if
  bounded-in-duration-per-thread) resource use under a sustained, repeated hang.
- No attempt was made to add thread-count monitoring, alerting, or a cap — this would be new scope
  (observability/alerting design), not part of R1.

---

## 13. Unexpected findings

1. **`AppleFMEngine` does not exist as an importable class anywhere in current source.**
   `vectorcode/src/vc_engine/apple_fm_shim.py` is a standalone FastAPI *server* module, not an
   `InferenceEngine`-shaped class with a `generate()` method. The real
   `from vectorcode.src.vc_engine.apple_fm_shim import AppleFMEngine` line inside
   `_multi_backend_fallback` (unchanged by this fix) has therefore always raised `ImportError` on
   every platform this code runs on — not just non-macOS hosts as the surrounding comment
   ("macOS Sonoma+ only") implies — and has always been silently absorbed by the existing broad
   `except Exception`, making the Apple FM branch a permanent, silent no-op in practice, independent
   of and pre-dating this fix. **Not fixed** — out of this task's file scope
   (`core/inference/ollama_safe.py` only) and not the defect this task was asked to remediate. Flagged
   here for the owner's visibility and as a candidate for a future, separately-scoped task.
2. **`GemmaCppEngine.generate()` accepts `**kwargs` but never forwards them** to the actual blocking
   call (`self._gemma.completion(prompt)`) — confirming that even if a `timeout=` kwarg *had* been
   passed to it (as an earlier, rejected design considered), it would have been silently absorbed and
   ineffective. This directly validated the decision in §3 to use a hard deadline rather than
   per-engine kwargs.
3. **The repository has a substantial number of pre-existing, unrelated, uncommitted changes** across
   many files (visible via `git status` at the start of this task). None were created or touched by
   this task; noted here only so a future reader does not mistake this report's file-scope claims
   (§4) for a claim about the repository's overall clean/dirty state.
4. **The live Segment-2 process (PID 37588) is still running** as of this task, despite the task's
   own framing ("The 7-day experiment is over"). It was read-only observed (via `Get-Process`, for
   the sole purpose of confirming it was not accidentally disturbed) and never signaled, attached to,
   or interacted with in any other way.

---

## 14. Rollback procedure

**Single-file, single-function revert.** `git diff core/inference/ollama_safe.py` shows the entire
change is contained within the region spanning the pre-existing `_multi_backend_fallback` function
(now split into `_attempt_all_fallback_engines` + a restructured `_multi_backend_fallback`). To roll
back:

1. `git checkout -- core/inference/ollama_safe.py` (or equivalent — revert this one file to its
   pre-Task-88 state). No other production file requires any change to accompany this revert; no
   data migration exists to undo (§5 item 13 — no persisted schema was changed).
2. Optionally remove `tests/unit/test_ollama_multi_backend_fallback_timeout.py` (safe to leave in
   place harmlessly if the production revert above is not also performed, since it only exercises
   `ollama_safe.py`'s public/private surface via mocks and asserts behavior that would simply
   fail loudly, not silently, against the pre-fix code — a useful regression indicator in its own
   right).
3. No process restart, database change, or configuration change is required as part of rollback —
   the pre-fix behavior (unbounded fallback wait) resumes exactly as it was, with no other observable
   side effect of having applied and then reverted this change.

---

## 15. Explicit statement: R2+ were NOT implemented

Confirmed, itemized: `core/event_bus/wiring.py`, `_fanout_handler`, `Governor.dispatch`/`route_task`
(R2) — untouched. `core/brain/goal_system.py`, any goal-progress logic (R3) — untouched.
`core/loop/autonomous_loop.py`'s veto-write call site, any suppression/reward separation (R4) —
untouched. `core/memory/policy.py`, `PolicyMemory.make_situation_hash` or any writer/reader key
formula (R5) — untouched. `generate_immediate_actions`, `_TAG_TO_ACTION`, `GOAL_ACTION_MAP`, any
candidate-diversity logic (R6) — untouched. `decision_id`/`candidate_id` stamping, `Decision`/
`Candidate` dataclasses (R7) — untouched. `CorrectionLearner.validate_lesson()` wiring (R8) —
untouched. `record_epistemic_belief()`, any contradiction-logging or `belief:*` work (R9) —
untouched. `CounterfactualMemory`'s `scenarios`/`outcomes` tables, any decision-provenance write
(R10) — untouched. `core/loop/trust_ladder.py` (TrustLadder) — read for context in a prior task,
**not modified** in this task at all. `core/city/agent_base.py` (HP shaping) and
`core/city/agent_registry.py`/`core/city/evolution_engine.py` (successor lifecycle) — untouched.
`Governor._llm_classify()` and `AgentBase.vchat()` — explicitly named as deferred follow-up work in
the task itself, and confirmed untouched.

---

## Integrity statement

Production files modified: **exactly one** — `core/inference/ollama_safe.py`. Configuration
modified: **none**. Databases written: **none** (the isolated diagnostic in §9 wrote only to a
`tempfile.mkdtemp()` scratch directory, never to `data/`). Dependencies installed: **none**. The
live Segment-2 process (PID 37588) was **not** started, stopped, signaled, restarted, or interacted
with beyond one read-only `Get-Process` liveness check. No real network call, model load, or
subprocess was reached by any test or diagnostic in this session — every fallback engine was mocked
at its real import location. No unrelated pre-existing test failure was investigated or "fixed."
Files created: `tests/unit/test_ollama_multi_backend_fallback_timeout.py` and this report.
