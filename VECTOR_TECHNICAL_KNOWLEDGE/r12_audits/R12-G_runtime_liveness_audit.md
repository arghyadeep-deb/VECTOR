# R12-G — Runtime / Liveness Audit

**HEAD audited:** `81b53b1175aede4ed05d1b9d086af91dda64c8a6` (verified via `git rev-parse HEAD`, clean tree)
**Scope:** read-only. No file written except this report. VECTOR was never launched.

## Objective

Determine whether `core/loop/autonomous_loop.py`'s runtime architecture is healthy
enough to eventually support a bounded L5 experiment, and specifically whether R11's
change (a goal can now emit up to 3 native candidates instead of 1) introduced any
event-fanout, execution-multiplication, or liveness risk.

## Method

Direct source read of `core/loop/autonomous_loop.py` (3,243 lines) and
`core/loop/decision_engine.py::evaluate()`, tracing the exact path candidates take
from `_think_tick()` through `DecisionEngine.evaluate()` to `_act_on()` and the event
bus. Cross-checked event-type fanout via `core/event_bus/wiring.py`. No trust placed
in `phase_status.md`'s claims — each was independently re-verified against current
source.

## Findings

### 1. Tick-loop crash protection — confirmed intact

| Loop | Timeout | Exception handling | Evidence |
|---|---|---|---|
| `observe_loop` | `asyncio.timeout(15)` per tick | `except asyncio.TimeoutError` (warn+skip) + `except Exception` → `_capture_loop_error` + `_emit_crash_signal`, loop continues | `autonomous_loop.py:715-730` |
| `think_loop` | `asyncio.timeout(60)` per tick | same pattern, `except Exception` → `_capture_loop_error`, 5s backoff | `autonomous_loop.py:804-814` |
| `reflect_loop` | `asyncio.timeout(CONFIG["loop"]["reflect_tick_timeout_sec"])` per tick | `except asyncio.TimeoutError` (warn+skip); outer `except Exception` → chunked 300×1s backoff, `_running`-responsive | `autonomous_loop.py:1717-1759` |

`_act_on()` is called synchronously inside `_think_tick()`, so it inherits the 60s
`think_loop` timeout umbrella — it has no independent timeout, but cannot escape the
outer one. Not a new gap; unchanged by R11.

The `reflect_loop` timeout is dated 2026-08-06 in an inline comment describing a real
prior incident ("any one hanging froze the loop thread with literally no bound") —
this is a genuine historical fix, not a stale claim; still present and correct at
current HEAD.

**No loop found that can propagate an unhandled exception out of its `while
self._running:` body.** All three ticks are fully isolated.

### 2. No new synchronous/blocking hot-path call found

`_think_tick()`'s only expensive call is `await asyncio.to_thread(self._get_context().get_world_state)`
(line 880) — deliberately off-loaded because `get_world_state()` invokes
`ScreenObserver.observe()` (blocking OCR). No raw `requests`/blocking `httpx` call was
found newly introduced in the candidate-generation path R11 touched
(`goal_system.py::generate_immediate_actions()` and the `_think_tick()` candidate loop
at lines 913-926) — both are pure in-memory dict/dataclass construction, zero I/O.

### 3. R11 fanout analysis — the core question

Traced exactly what happens to N candidates between generation and execution:

```
_think_tick():
  actions = generate_immediate_actions(limit=4)      # <=4 goals, each now up to
                                                       # 3 tag-derived action_types
                                                       # (_MAX_STRATEGIES_PER_GOAL=3)
  candidates = [Candidate(...) for a in actions]      # pure in-memory construction,
                                                       # zero I/O, zero side effects
  candidates.extend(plan_candidates)                  # same — in-memory
  decision = await DecisionEngine.evaluate(candidates)  # <- the only place all
                                                          #    candidates are touched
  if decision.winner.total_score > 0.3:
      await self._publish_event(EventType.DECISION_MADE, {...})  # ONE event,
                                                                    # winner only
      await self._act_on(decision.winner)              # ONE execution, winner only
```

Inside `DecisionEngine.evaluate()` (`decision_engine.py:650-768`), every candidate in
the list IS individually touched by three operations:

1. `c.context_snapshot = world_state` — dict assignment, no I/O (line 669)
2. `bank.inject_past_reasoning(query, top_k=3)` — confirmed **local, in-memory**
   similarity retrieval over `ReasoningBank._entries` (`vectorcode/src/reasoning_bank.py:209-308`);
   zero network/LLM calls (verified by reading `retrieve()`'s implementation)
3. `mem.store(event_type="decision_candidate", ...)` — one `EpisodicMemory.store()`
   SQLite write per candidate, **including rejected ones** (line 743) — this existed
   before R11 and logs every candidate regardless of origin

**Conclusion: R11 does NOT introduce execution fanout, event fanout, or any new
external side effect per candidate.** The only real effect of "up to 3x more
candidates per goal" is a bounded increase in (a) local `ReasoningBank.retrieve()`
lookups and (b) local `EpisodicMemory.store()` SQLite writes per think_tick — both
in-process, non-authoritative, already-existing operations that scale with candidate
count regardless of where the candidates came from. This was already true before R11
(a tick with 4 goals firing already produced 4 candidates and 4 `mem.store()` calls);
R11 raises the worst-case ceiling from 4 to a bounded ~12 tag-derived + N plan
candidates per tick, not from 1 to unbounded.

Exactly one `EventType.DECISION_MADE` publish and exactly one `_act_on()` call happen
per tick regardless of candidate count — confirmed by reading the `if
decision.winner.total_score > 0.3:` block (lines 950-991): both calls are outside any
per-candidate loop and reference `decision.winner` only.

### 4. `DECISION_MADE` has zero downstream_tasks mapping

Checked `core/event_bus/wiring.py` for `DECISION_MADE` / `decision_made` —
**zero matches**. This event type has no entry in `get_downstream_tasks()`, so even
the real fanout mechanism that exists in the codebase (`_fanout_handler()` at
`autonomous_loop.py:201-236`, which does dispatch new district tasks via
`governor.dispatch()` gated by `_fanout_edge_should_fire()` per-edge cooldown) never
fires for this event. Its only confirmed subscriber is
`core/api/routers/websocket.py:312-324`, a passive relay to connected dashboard
clients — no further action triggered.

### 5. Task lifecycle / shutdown

`_tracked_task()` (line 183-199) wraps every `asyncio.create_task()` call, stores the
handle in `self._background_tasks` (a `set`), and prunes it via a `done_callback` —
so tasks are not garbage-collected mid-flight and failures are logged rather than
silently swallowed. `stop()` (line 3194+) iterates `_background_tasks` and calls
`.cancel()` on every unfinished task, then clears the set. No leak found.

### 6. Scheduler

`AsyncIOScheduler` (APScheduler) is instantiated once (line 411-413) with
`EVENT_JOB_EXECUTED`/`EVENT_JOB_ERROR` listeners registered — did not find evidence of
overlap protection (e.g. `max_instances`) in the excerpt read; flagged as an open
question below, not a confirmed defect (out of R11's scope, pre-existing).

### 7. Unrelated observation (not a defect, noted for the record)

`_act_on()` also has a second real call site outside `_think_tick()`:
`anticipation_engine`'s tick (~line 3186) calls `await self._act_on(candidate)`
directly for proactive predictions. This is a pre-existing, independent candidate
source unrelated to and unaffected by R11 — noted only so R12 synthesis doesn't
mistake it for a new R11 path.

## Risk Table

| Risk | Severity | Evidence |
|---|---|---|
| R11 candidate-count increase causing event/execution fanout | **None found** — ruled out | §3, §4 above |
| Uncaught exception killing observe/think/reflect loop | **None found** | §1 |
| Blocking call in R11's own new code path | **None found** | §2 |
| Per-candidate local I/O (SQLite writes, reasoning-bank lookups) scaling with R11's higher candidate ceiling | **Low** — bounded, local, pre-existing pattern, not authoritative | §3 |
| Background task leak on shutdown | **None found** | §5 |
| Scheduler overlap protection unverified | **Open / Low** — pre-existing, out of R11 scope | §6 |

## Current capability level

Runtime liveness: **PRODUCTION_VERIFIED** for crash-isolation (all three ticks
independently timeout- and exception-protected, confirmed by direct source read, not
by trusting prior documentation).

Fanout safety under R11: **PRODUCTION_VERIFIED** — traced through actual source, not
inferred.

## What's broken vs. working

**Working:** tick isolation, task tracking/cancellation, R11 candidate generation is
side-effect-free until exactly one winner is selected, `DECISION_MADE` has no fanout
wiring.

**Not verified in this audit (out of scope / needs separate check):** APScheduler
`max_instances`/overlap configuration; whether `_fanout_edge_should_fire()`'s cooldown
window is correctly tuned for other event types that DO have downstream_tasks
mappings (unrelated to R11, a pre-existing R2 concern per the R11 report's own
citation of "R2's existing per-edge cooldown").

## Recommended next milestone

None required specifically because of R11 — the runtime architecture already
tolerates R11's higher candidate ceiling with no code change needed. If R12 synthesis
decides to pursue L5 (repeated real autonomous cycles), the one open item worth a
dedicated, narrow follow-up check is APScheduler overlap protection (`max_instances`),
since a bounded L5 experiment would run the scheduler for longer than any test so far
has.

## Open questions

1. Does `AsyncIOScheduler` have `max_instances=1` (or equivalent) set anywhere in
   config, preventing overlapping scheduled jobs during a longer-running L5 experiment?
2. `_fanout_edge_should_fire()`'s cooldown parameters were not re-audited here (out of
   R11's scope) — worth a targeted look before any bounded L5 experiment that would
   exercise events with real downstream_tasks mappings.
