# 89A — Runtime Boundary Review (Agent A)

Scope: independent re-verification of the "Task 88" runtime-remediation fix
described in this task's briefing, plus a repo-wide trace of every
`ollama_safe.chat()`/`chat_stream()` production caller, plus a narrow,
evidence-justified fix for `Governor.dispatch()`'s event-loop-blocking path.

---

## 0. BLOCKING FINDING — the "Task 88" fix described in the briefing does not exist in this codebase

The task briefing asserted that `core/inference/ollama_safe.py::_multi_backend_fallback()`
had already been fixed: extracted into `_attempt_all_fallback_engines()`, run
on a fresh per-call `ThreadPoolExecutor`, bounded via
`future.result(timeout=timeout)`, `executor.shutdown(wait=False)` in
`finally`, with a `_record_observability(..., status="timeout",
error_kind="fallback_deadline_exceeded")` call on timeout, backed by a
`VECTOR_TECHNICAL_KNOWLEDGE/88_R1_RUNTIME_REMEDIATION_REPORT.md` report.

**None of this exists.** Independently verified, not just re-read:

- `VECTOR_TECHNICAL_KNOWLEDGE/` did not exist anywhere in this worktree before
  this task created it (`Glob "VECTOR_TECHNICAL_KNOWLEDGE/*"` → no files;
  confirmed again via `find . -iname "*RUNTIME_REMEDIATION*"` and
  `git log --all --oneline --diff-filter=A -- "*88_*"` → no such file was
  ever added on any branch).
- `_attempt_all_fallback_engines`, `_record_observability`, and
  `concurrent.futures`/`ThreadPoolExecutor` do not appear anywhere in
  `core/inference/ollama_safe.py`. The file's only `ThreadPoolExecutor`
  reference is a *comment* (line 245) pointing at a fix that lives in a
  **different file** (see below).
- `core/inference/ollama_safe.py::_multi_backend_fallback()` (lines 594–643,
  read in full) is **unchanged from its originally-broken shape**: it accepts
  a `timeout: float` parameter and never uses it anywhere in the function
  body. It calls `LiteLLMEngine().generate(...)`, `AppleFMEngine().generate(...)`,
  and `GemmaCppEngine().generate(...)` sequentially, each wrapped only in a
  bare `try/except Exception` with **no timeout, no thread bound, no
  cancellation** — i.e. exactly the unbounded-blocking defect the briefing
  claimed was fixed, still present, still reachable from `chat()`'s two
  `except` branches (`CircuitBreakerOpenError` and the generic
  `except Exception as e:` at ollama_safe.py:293).
- No `inference_calls` table and no `_record_observability` function exist
  anywhere in the repo (repo-wide grep, zero hits for either).
- `tests/unit/test_ollama_multi_backend_fallback_timeout.py`, which the
  briefing said to read for house style, **does not exist**. Its sibling,
  `tests/unit/test_ollama_semaphore_timeout.py`, does exist and does pass
  (see §4) — that file documents a *different*, real fix (semaphore
  acquire-timeout, commit `6b5fcf204`).
- `git log --all --oneline -- core/inference/ollama_safe.py` shows the real
  recent history: `6b5fcf204` "bound the Ollama semaphore; make loop-blocking
  chat() calls visible" and `4247dd3dc` "close ollama.Client — every LLM call
  leaked a TCP connection". Neither touches `_multi_backend_fallback()`.

**What actually happened, and is real:** commit `fccdeb91f` ("the loop-stall
timeout was decorative — ThreadPoolExecutor re-blocked") fixed the *exact
same class* of bug — `with ThreadPoolExecutor() as pool: pool.submit(...).result(timeout=)`
re-blocking on `__exit__ -> shutdown(wait=True)` — but in
**`core/inference/vectorcode_llm.py::chat()`**, wrapping `ProviderClient().chat()`,
not in `ollama_safe.py::_multi_backend_fallback()`. Verified in the current
file (`vectorcode_llm.py:706-710`): a fresh `_cf.ThreadPoolExecutor(max_workers=1)`
is created per call, `result = _pool.submit(...).result(timeout=timeout + _grace)`,
and `_pool.shutdown(wait=False)` runs in a `finally` block — this one is
correct and matches every criterion the briefing described, just attached to
the wrong function name and file.

**Conclusion:** the briefing's "Task 88" background conflated two different
fixes (the real `vectorcode_llm.py` one, and a `_multi_backend_fallback()`
fix that was apparently planned/described but never implemented or committed
on this branch). Re-verifying the checklist in the task prompt against the
*actual* code:

| # | Checklist item (against `ollama_safe.py::_multi_backend_fallback`) | Verdict |
|---|---|---|
| 1 | `future.result(timeout=timeout)` bounds the wait | **FALSE** — no `future`, no executor, no timeout use at all |
| 2 | fresh executor per call | **FALSE** — no executor exists |
| 3 | `shutdown(wait=False)`, not `with` | **N/A** — no executor exists |
| 4 | timeout logging | **FALSE** — no timeout path exists to log |
| 5 | exception propagation via `future.result()` | **N/A** |
| 6 | engine order LiteLLM→AppleFM→GemmaCpp unchanged, `""` on total failure | **TRUE** — this part is correct and unchanged |
| 7 | `chat()`'s 3 call sites still work | **TRUE** — `chat()` itself is unaffected; only the fallback-timeout property is missing |
| 8 | residual limitation documented in code | **FALSE** — no such fix or comment exists in this function |

Per the task's own instruction ("only fix it if the fix is small and clearly
correct; otherwise report and stop") — implementing the missing
`_multi_backend_fallback()` bound (extracting the three engine attempts,
adding a fresh executor, wiring an observability/telemetry call that doesn't
currently exist under any name) is **not a small fix**; it is the entirety of
the originally-scoped Task 88 work. I did **not** attempt it. This is
reported here as the blocking finding for the lead agent to route to whoever
owns Task 88 (or to re-open it).

Residual, real, currently-live risk this leaves in place: if the local
Ollama daemon is down or the circuit breaker is open, `chat()` falls into
`_multi_backend_fallback()`, which can block the calling thread indefinitely
on `LiteLLMEngine.generate()` (network call, no timeout) if a
`VECTOR_LITELLM_FALLBACK_MODEL`/candidate model is configured. `AppleFMEngine`
is confirmed (per the task briefing, and consistent with the module being
Apple-Silicon-only) a dead import on this Windows/RTX box — not a live risk.
`GemmaCppEngine` risk depends on whether the binary is installed; not
verified further (out of scope — point 1 was re-verification, not a new
audit of the fallback engines themselves).

---

## 1. Confirmed defects and their exact locations

| Defect | File:Line | Status |
|---|---|---|
| `_multi_backend_fallback()`'s `timeout` param is accepted and never used; three fallback engines can block the calling thread indefinitely | `core/inference/ollama_safe.py:594-643` | **CONFIRMED STILL PRESENT** (see §0) — not fixed this session, reported only |
| `Governor._llm_classify()` reached via `route_task()` is called directly (no thread hop) from `dispatch()`'s `async def` body | `core/city/governor.py` (pre-fix: line 1884 in the original file) | **FIXED this session** — see §3 |
| `AgentBase.vchat()` calls sync `ollama_safe.chat()` directly, called unawaited from ~15 district agents' `async def run()`/`answer_*()` methods | `core/city/agent_base.py:302-319` | **CONFIRMED, NOT FIXED** — see §3 for why |
| `core/ui/web_ui.py::web_chat()` (`async def`, FastAPI `/chat` POST) calls `ollama_safe.chat()` directly, `timeout=120.0`, no thread hop | `core/ui/web_ui.py:719-738` | **CONFIRMED, NOT FIXED** (out of scope) |
| `core/ui/web_ui.py::web_chat_ws()` iterates `ollama_safe.chat_stream()` synchronously inside an `async def` websocket handler | `core/ui/web_ui.py:757-780` | **CONFIRMED, NOT FIXED** (out of scope) |
| `core/engine/channels/runtime.py::ChannelRuntime._default_agent()` (`async def`) calls `ollama_safe.chat()` directly as its post-Governor fallback | `core/engine/channels/runtime.py:239-266` | **CONFIRMED, NOT FIXED** (out of scope) |
| `core/engine/agents/subagent_runner.py::SubagentRunner._default_llm()` (`async def`) calls `ollama_safe.chat()` directly, `timeout=60.0` | `core/engine/agents/subagent_runner.py:133-150` | **CONFIRMED, NOT FIXED** (out of scope) |
| `core/api/routers/inference.py::inference_run()` (`async def` FastAPI endpoint) calls `ollama_safe.chat()` directly | `core/api/routers/inference.py:54-69` | **CONFIRMED, NOT FIXED** (out of scope) |
| `web_ui.py::web_tasks_submit()`'s inner `_work()` coroutine and `core/ui/chat.py`'s `/bg` `_deep_work()` coroutine and `core/api/routers/tasks.py::submit_task()`'s `_work()` all call `ollama_safe.chat()` directly inside an `async def` submitted as a bare coroutine to `TaskQueue` | see table in §2 | **CONFIRMED, NOT FIXED** (out of scope) |

**Important, independently-confirmed context for why these are real (not
theoretical) blocking risks even though `autonomous_loop.py` wraps its ticks
in `asyncio.timeout(...)`:** `asyncio.timeout()` can only deliver cancellation
at an `await` point. A synchronous, non-yielding call (`self.route_task(task_type)`,
pre-fix, or `self.vchat(...)`, today) never yields, so the tick-level
`asyncio.timeout(60)` around the "think" tick (`autonomous_loop.py:654`)
cannot actually interrupt it — the timeout can only fire *after* the blocking
call finally returns control to the loop, if ever. This was confirmed by
reading `autonomous_loop.py` (grep for `_supervised`/`asyncio.timeout`,
context only, not modified) — it has real per-tick timeouts and a
`_supervised()` restart wrapper (`autonomous_loop.py:2130-2134`), but neither
mechanism can bound a purely-synchronous call inside a tick.

---

## 2. Every production caller of `ollama_safe.chat()` / `chat_stream()`

Excludes `tests/`. "Async-safe" means the call is either made from genuinely
synchronous code, or is already off-loaded via `asyncio.to_thread`/an
equivalent bounded thread-hop before an `await`.

| Caller | Context | Class |
|---|---|---|
| `core/city/governor.py::Governor._llm_classify()` (called via `route_task()`) | sync `def`, ~10 other sync call sites (tests, `core/api/routers/commands.py`, `core/memory/router.py`, `core/voice/realtime.py`, `vc_agents/routing_agent.py`) | **(c)** genuinely sync at those call sites — **(b)** was true for the one call from `dispatch()`, now fixed via `route_task_async()` (§3) |
| `core/city/agent_base.py::AgentBase.vchat()` | sync `def`, called unawaited from ~15 district agents' `async def run()`/`answer_*()` (`kiit_scraper.py`, `malware_hunter.py`, `project_planner.py`, `doc_writer.py`, `zk_steward.py`, `feedback_synthesizer.py`, `venture_pipeline.py`, `problem_clusterer.py`, `federation_agent.py`, `credential_manager.py`, `autopilot.py`, `performance_benchmarker.py`, `video_pipeline.py`, `comfyui_adapter.py`) | **(b)** confirmed live blocking risk, **not fixed** (see §3 for why) |
| `core/voice/realtime.py::classify_intent_llm()` | sync `def`, but its only production caller (`try_device_action`'s sibling voice-loop code, `realtime.py:618`) already does `await asyncio.to_thread(classify_intent_llm, text)` | **(a)** already async-safe |
| `core/ui/web_ui.py::web_chat()` | `async def` FastAPI POST `/chat`, direct call, `timeout=120.0` | **(b)** confirmed live blocking risk |
| `core/ui/web_ui.py::web_chat_ws()` | `async def` FastAPI websocket, synchronous `for token in chat_stream(...)` loop | **(b)** confirmed live blocking risk |
| `core/ui/web_ui.py::web_tasks_submit()`'s inner `_work()` | `async def` coroutine object handed to `TaskQueue.get().submit(_work(), ...)`, direct call, `timeout=600.0` | **(b)** confirmed — blocks whatever loop `TaskQueue` runs queued coroutines on |
| `core/ui/chat.py::_chat_with_vector()` | plain sync `def`, called from `run_chat()`'s blocking `while True` terminal REPL (no event loop involved) | **(c)** genuinely sync, not a concern |
| `core/ui/chat.py`'s `/bg` command inner `_deep_work()` | `async def` coroutine handed to `TaskQueue.get().submit(_deep_work(), ...)`, direct call, `timeout=600.0` | **(b)** confirmed — same TaskQueue pattern as above |
| `core/inference/vectorcode_llm.py::_try_ollama()` | sync `def`, its only caller (`achat()`'s legacy fallback chain) invokes it via `await asyncio.to_thread(_fn, ...)` (`vectorcode_llm.py:845`) | **(a)** already async-safe |
| `core/inference/vectorcode_llm.py::chat_stream()` | plain `def` generator (not async), iterates `ollama_safe.chat_stream()` sync-to-sync | **(c)** not itself async; safety of ITS callers is outside this trace's scope (none of them import `ollama_safe` directly) |
| `core/inference/model_router.py::TaskClassifier._classify_with_llm()` | sync `def`, called from `classify()` (also sync `def`); `classify()`'s own callers were not fully traced in this session | **(b)-probable, unverified** — flagged, not confirmed to the same evidence bar as the others |
| `core/engine/channels/runtime.py::ChannelRuntime._default_agent()` | `async def @staticmethod`, direct call, `timeout=30.0`, fallback path after a failed `Governor.dispatch()` | **(b)** confirmed live blocking risk |
| `core/engine/agents/subagent_runner.py::SubagentRunner._default_llm()` | `async def @staticmethod`, direct call, `timeout=60.0` | **(b)** confirmed live blocking risk |
| `core/runtime/missions.py::MissionPlanAdvisor._call_model()` | sync `def`, called from `advise()` (also sync `def`); `advise()`'s own callers were not fully traced in this session | **(b)-probable, unverified** — flagged, not confirmed |
| `core/api/routers/tasks.py::submit_task()`'s inner `_work()` | `async def` coroutine handed to `TaskQueue.get().submit(_work(), ...)`, direct call, `timeout=300.0` | **(b)** confirmed — same TaskQueue pattern |
| `core/api/routers/inference.py::inference_run()` | `async def` FastAPI POST `/inference/run`, direct call, `timeout=60.0` | **(b)** confirmed live blocking risk |
| `scripts/audit_wiring.py` | asserts a source string is present (repo-audit tooling, not a runtime call site) | **(c)** not applicable |
| `districts/data_analytics/performance_benchmarker.py` | docstring reference only (`"Time N calls to ollama_safe.chat()..."`) — actual import is `vectorcode_llm.chat`, not `ollama_safe.chat` | **(c)** not applicable |

**Scale note:** most district agents (`districts/startups/_base.py`,
`skill_mapper.py`, `contact_manager.py`, the language coaches, etc.) import
`chat` from **`core.inference.vectorcode_llm`**, not `ollama_safe` directly.
`vectorcode_llm.achat()` (the async entry point) is already correctly
thread-hopped (`fccdeb91f`, verified §0); `vectorcode_llm.chat()` (sync) is a
separate, still-synchronous entry point whose own caller safety was not
re-audited here (different task scope: this trace is `ollama_safe` direct
callers only, per the task's explicit instruction).

---

## 3. Exact modifications made

**Files changed:** `core/city/governor.py` only. `core/city/agent_base.py`
was edited and then **reverted to its original content** — final diff is
empty (confirmed via `git diff --stat`).

### `core/city/governor.py`

1. Added a new method `Governor.route_task_async()` (async twin of the
   existing, **unmodified** `route_task()`): keyword/exact `DISTRICT_TASK_MAP`
   matching stays inline and synchronous (cheap, no I/O); only the LLM
   fallback is moved off the event-loop thread via a genuine
   `return await asyncio.to_thread(self._llm_classify, task_type)`.
2. Changed `dispatch()`'s one call site:
   `district = task.get("district") or self.route_task(task_type)` →
   `district = task.get("district") or await self.route_task_async(task_type)`.

`route_task()` and `_llm_classify()` themselves are **byte-for-byte
unchanged** — confirmed by reverting an earlier draft that *did* modify
`_llm_classify()`'s body and diffing back to a clean state before the final
edit (see rationale below). Their ~10 other sync call sites are unaffected.

**Why `asyncio.to_thread` and not a bounded synchronous thread-hop (the
pattern already used by `Governor._cloud_classify()`):** an earlier draft of
this fix kept `_llm_classify()` synchronous and wrapped its internal
`ollama_safe.chat()` call in the same `ThreadPoolExecutor` +
`future.result(timeout=...)` + `shutdown(wait=False)` pattern
`_cloud_classify()` already uses (chosen initially because it requires no
signature changes at all). **This was reverted after direct empirical
measurement showed it does not solve the stated problem:** `future.result(timeout=...)`
is itself a *synchronous, blocking* call on whatever thread invokes it. When
that thread is the event-loop thread (because the caller never awaited
anything), the loop is blocked for the same duration as before — the pattern
only bounds the *maximum* wait and avoids the double-block-on-`__exit__` bug
class (`fccdeb91f`); it does not stop ordinary multi-second latency from
freezing the loop. This is proven, not asserted — see the timing evidence in
§4. `route_task_async()`'s `await asyncio.to_thread(...)` is genuinely
different: it actually yields control back to the loop's scheduler while the
worker thread runs, letting other coroutines make real progress.

**Why `AgentBase.vchat()` was left unchanged (production code, reverted to
original):** the same reasoning applies with one critical difference —
`_llm_classify()` has exactly **one** call site that runs inside an event
loop (`dispatch()`), so a small async twin plus a one-line change at that
single call site fully solves the problem with zero blast radius elsewhere.
`vchat()` has **no such single seam**: all ~15 known production call sites
(`kiit_scraper.py`, `malware_hunter.py`, `project_planner.py`, `doc_writer.py`,
`zk_steward.py`, `feedback_synthesizer.py`, `venture_pipeline.py`,
`problem_clusterer.py`, `federation_agent.py`, `credential_manager.py`,
`autopilot.py`, `performance_benchmarker.py`, `video_pipeline.py`,
`comfyui_adapter.py`) call `result = self.vchat(...)` directly, unawaited,
from inside their own `async def` methods. There is no way to make the
*internal* `ollama_safe.chat()` call inside `vchat()` genuinely non-blocking
(`await asyncio.to_thread(...)`) without making `vchat()` itself `async def`
— and doing that breaks every one of those ~15 call sites (a coroutine object
would be returned instead of a string; `(result or "").strip()`-style code
downstream would raise or silently misbehave) unless each is also migrated to
`await self.vchat(...)`. That is not a "small, per-call-site change" — it is
a ~15-file change I was explicitly told not to make in a single unattended
session, and a signature-preserving bounded-wait alternative was already
shown (previous paragraph) not to actually solve the described problem. Per
the task's own instruction — "If you conclude no additional production fix
is safely justified in this single session, DO NOT MODIFY PRODUCTION CODE —
report your reasoning instead" — `vchat()` was left unmodified. This is a
**recommendation for a separately-scoped follow-up task**, not a fix.

None of the scope-boundary files (`core/event_bus/*`, `core/brain/goal_system.py`,
`core/memory/policy.py`, `core/loop/autonomous_loop.py`,
`core/loop/decision_engine.py`, `hands/runner.py`, `core/loop/trust_ladder.py`,
`core/config.py`, `PermissionGateway`, any database file, any experiment
file, `GOAL_ACTION_MAP`) were touched. `autonomous_loop.py` was only read
(grep for `_supervised`/`asyncio.timeout`, §1) for context.

VECTOR was never started in any mode. No `.env`/experiment/config file was
touched. No live process was touched.

---

## 4. Tests added and results

New file: `tests/unit/test_governor_dispatch_thread_hop.py` (4 tests,
house-style modeled on `tests/unit/test_ollama_semaphore_timeout.py`: real
`asyncio` event loop via `pytest.ini`'s `asyncio_mode = auto`, real timing
assertions, only `Governor._llm_classify`/`ollama_safe.chat` stubbed — no
real Ollama, network, cloud provider, or subprocess anywhere).

1. `test_route_task_async_llm_fallback_does_not_block_event_loop` — stubs
   `Governor._llm_classify` with a real `time.sleep(0.3)`, runs an
   independent `ticker()` coroutine concurrently via `asyncio.create_task`,
   and asserts the ticker advances ≥15 times **strictly during** the
   `route_task_async()` call. Empirically verified (ad-hoc script, not
   shipped, output captured below) that the pre-fix call pattern
   (`gov.route_task()` called directly/unawaited from inside a coroutine,
   under an identical harness) scores **exactly 0 ticks** — proving this
   assertion actually discriminates blocking from non-blocking, not just
   "mock was called":
   ```
   route_task (sync, old pattern)      district='research'   elapsed=0.300s ticks_during_call=0
   route_task_async                    district='research'   elapsed=0.302s ticks_during_call=20
   ```
2. `test_route_task_async_keyword_match_is_synchronous_and_fast` — confirms
   the cheap keyword-match path returns in <0.2s with no thread-hop cost.
3. `test_route_task_sync_unchanged` — confirms `route_task()`/`_llm_classify()`
   are unaffected for their existing synchronous callers (mirrors the
   pre-existing `tests/test_governor.py::test_route_unknown_defaults_to_research`
   pattern).
4. `test_dispatch_routes_unknown_task_via_async_llm_fallback` — end-to-end:
   `dispatch()` still correctly resolves an LLM-fallback task_type to a real
   district via the new `route_task_async()` path, with `ollama_safe.chat`
   mocked to return `""` (no real network).

**Results** (`pytest tests/unit/test_governor_dispatch_thread_hop.py
tests/test_governor.py tests/unit/test_ollama_semaphore_timeout.py -v`):

```
tests\unit\test_governor_dispatch_thread_hop.py ....                     [ 22%]
tests\test_governor.py .........                                         [ 72%]
tests\unit\test_ollama_semaphore_timeout.py .....                        [100%]
======================= 18 passed, 1 warning in 21.92s ========================
```

18/18 passed, 0 failed. `tests/unit/test_ollama_multi_backend_fallback_timeout.py`
was not run because it does not exist (§0). No other test files were run,
per the task's instruction to avoid the full suite and specifically avoid
`tests/test_intent_matcher.py`.

---

## 5. Disproven hypotheses

- **"Task 88 already bounded `ollama_safe._multi_backend_fallback()`'s
  wait."** Disproven — see §0. The real, correct fix for this bug *class*
  exists, but in `vectorcode_llm.py::chat()`, not here.
- **An earlier draft of this fix (bounded synchronous `ThreadPoolExecutor` +
  `future.result(timeout=)` inside `_llm_classify()`, no signature change)
  "fixes" the event-loop-blocking problem.** Disproven by direct
  measurement — see §3/§4. It bounds the *maximum* wait and avoids the
  `fccdeb91f` double-block class of bug, but does not stop the loop from
  being blocked for the duration of an *ordinary* (within-bound) call. Not
  shipped; the timing evidence that disproved it is preserved here so the
  next person doesn't repeat the attempt believing it works.

---

## 6. Remaining likely mechanisms (labeled)

- **PROVEN:** `core/inference/ollama_safe.py::_multi_backend_fallback()`
  still has an unbounded blocking defect on its `timeout` parameter (never
  used) — directly read, directly confirmed, matches the exact defect shape
  Task 88 was meant to close.
- **PROVEN:** pre-this-session, `Governor.dispatch()` (VECTOR's
  highest-volume routing path) blocked its own event loop for the full
  duration of any LLM/cloud classification call whenever a task_type needed
  the LLM fallback — directly measured (0 ticks during a 0.3s call, §4),
  not inferred.
  Post-this-session, this specific path is fixed.
- **PROVEN:** `AgentBase.vchat()` and at least 6 other `async def` call
  sites (`web_chat()`, `web_chat_ws()`, `_default_agent()`, `_default_llm()`,
  `inference_run()`, the three `TaskQueue`-submitted `_work()`/`_deep_work()`
  coroutines) still call `ollama_safe.chat()`/`chat_stream()` directly with
  no thread hop, and remain live, confirmed, unfixed blocking-risk paths as
  of this report.
- **LIKELY:** `model_router.py::TaskClassifier._classify_with_llm()` and
  `missions.py::MissionPlanAdvisor._call_model()` are reached from async
  code with the same pattern, but this session did not fully trace their
  own callers to the same evidence bar as the confirmed list — flagged as
  likely, not proven.
- **PLAUSIBLE, unchanged from prior classification:** the historical
  69.9-hour `hypothesis_engine` hang (`data/telemetry.db`, `inference_calls`,
  `latency_ms=251520681`) remains a PLAUSIBLE/LIKELY contributing-mechanism
  candidate given the breadth of confirmed-live blocking paths found this
  session (more than previously documented), but this session found **no
  new direct evidence** tying that specific historical incident to any one
  named call site, and it is not being reclassified as proven.
- **UNKNOWN:** whether `GemmaCppEngine`'s binary is actually installed/live
  on this machine, and therefore whether `_multi_backend_fallback()`'s
  unbounded-wait defect (§0) is currently reachable in practice or only in
  theory — not investigated this session (out of scope for point 1's
  re-verification mandate).

---

## 7. Residual uncertainty

- The `model_router.py`/`missions.py` call sites (§2, marked "probable,
  unverified") deserve a full caller trace before being either fixed or
  ruled out.
- `_multi_backend_fallback()` (§0) needs its own properly-scoped
  remediation task — this session deliberately did not attempt it, since it
  is not a small fix and re-implementing it correctly (including deciding
  where/how to add observability, since no `_record_observability` or
  `inference_calls` table exists under any name) is Task 88's full original
  scope, not a narrow follow-up.
- `AgentBase.vchat()` and the other confirmed-live `async def` call sites in
  §1/§2 remain real, currently-blocking paths. A genuine fix for `vchat()`
  requires either (a) migrating all ~15 call sites to `await self.vchat(...)`
  after converting it to `async def` (verified, mechanically uniform shape
  across all 15 sites — `result = self.vchat([...])` inside a `try/except`
  — but still a real multi-file change needing per-agent testing), or (b) a
  different architectural approach not evaluated in this session.
