# Task 89B — Event Fan-Out Remediation (R2): Cooldown / Dedup

**Agent:** Agent B — Event Fanout Remediation (R2), Task 89 overnight remediation
**Scope:** `AutonomousLoop._fanout_handler` cooldown/dedup only, plus one confirmed-dead
wiring edge. No other section of `core/loop/autonomous_loop.py` touched. No live process
started or interacted with; VECTOR's 7-day experiment (PID 37588) was not touched.

---

## 1. Background re-verified from source

`core/event_bus/wiring.py` defines:
- `PUBLISH_EVENTS: dict[str, EventType]` — keyed by **district name only**, not
  `(district, task_type)`. Confirmed unchanged; this is the known architectural gap this
  task explicitly does NOT fix.
- `EVENT_TRIGGER_MAP: dict[EventType, list[tuple[str, str, dict]]]` — event type ->
  `[(district, task_type, params_template), ...]`.
- `get_downstream_tasks(event_type)` — thin `.get(event_type, [])` accessor over the map.

The actual fan-out mechanism is `AutonomousLoop._fanout_handler`, at
**`core/loop/autonomous_loop.py:127-166`** (after this change; was 127-159 before). It is
subscribed to all events at **`core/loop/autonomous_loop.py:2054`**
(`self._fanout_sub = bus.subscribe(None, self._fanout_handler)` — line number shifted
from the prior-research estimate of ~2422 because this file has grown/shrunk since;
content and behavior match exactly what was described).

**Correction to prior research:** the handler does **not** use a `_tracked_task()`
helper — there is no such method anywhere in this file (verified via full-file grep). The
original dispatch loop used plain `asyncio.create_task(governor.dispatch(task))`,
fire-and-forget, with zero tracking, zero dedup, zero cooldown. That is the exact gap this
task closes.

Before this change, the relevant loop (original lines 154-157) was:

```python
for district, task_type, params_template in get_downstream_tasks(event.event_type):
    params = {k: (v.format(event_type=et, event_data=str(getattr(event, 'data', {})))) for k, v in params_template.items()}
    task = {"type": task_type, "district": district, "params": params, "source_event": et}
    asyncio.create_task(governor.dispatch(task))
```

Both cycles described in the task brief (marketing <-> data_analytics/intelligence <->
strategy/content/marketing via `ANALYTICS_READY`, and content <-> qa via
`CONTENT_REVIEWED`) are confirmed present in `EVENT_TRIGGER_MAP` exactly as described,
with zero cycle-breaking of any kind before this change.

---

## 2. Edge identity (B1)

`edge = (source_event_type, target_district, target_task_type)` — a plain 3-tuple, e.g.
`("marketing_published", "data_analytics", "analyze_campaign_metrics")`. This matches the
`(district, task_type, params_template)` shape `get_downstream_tasks()` already returns,
with the triggering event type prepended. `params_template` is intentionally excluded
from the identity — it is a fixed template per wiring entry, not per-event data, so it
carries no extra distinguishing information for this purpose.

## 3. Cooldown value and storage (B2, B5)

- **Default: 120.0 seconds**, as the explicit named constant `_FANOUT_EDGE_COOLDOWN_SEC`
  in `core/loop/autonomous_loop.py`. Chosen because it comfortably exceeds a single
  district dispatch's typical processing window (permission gateway + agent run) while
  still being short enough that a genuinely new burst of the same edge (not a same-cycle
  echo) gets through within about a minute of quiet — appropriate for a first-pass noise
  filter, not a hard rate limiter.
- **Storage:** a **module-level** plain dict, `_fanout_edge_last_fired: dict[tuple[str,
  str, str], float]`, declared just above the `AutonomousLoop` class (not
  instance-level). This file already follows a module-level-helper-functions-above-the-
  class pattern (`_scan_incoming`, `_get_loop_guard`, `_capture_loop_error`,
  `_record_job_run`) so this fits existing structure more naturally than adding a new
  `self._fanout_cooldowns = {}` line inside `__init__` — which would have required
  editing `__init__`, a part of the class other Task 89 agents are working on in parallel
  in the same file. Module-level state resets identically to instance-level state on
  process restart (B5) since `AutonomousLoop` runs one per process; there is no
  persistence, no DB table, no file — a bare dict, as required.
- **CONFIG override:** `core/config.py` gained one `Field(120.0, ge=0.0, le=3600.0)` on
  `VectorSettings` (`FANOUT_EDGE_COOLDOWN_SEC`, next to the existing
  `VC_LLM_LOOP_GUARD_COOLDOWN_SEC` which follows the identical pattern) and one `CONFIG`
  dict entry (`"fanout_edge_cooldown_sec"`). `autonomous_loop.py` reads it via
  `CONFIG.get("fanout_edge_cooldown_sec", 120.0)` — the constant works correctly with the
  in-code default even if `CONFIG` never carried the key, per the task's requirement that
  a config change never be required for correct operation.

## 4. Duplicate suppression + cooldown semantics (B3, B4)

New helper, module-level, directly above `class AutonomousLoop`:

```python
def _fanout_edge_should_fire(edge: tuple[str, str, str]) -> bool:
    now = time.monotonic()
    last_fired = _fanout_edge_last_fired.get(edge)
    if last_fired is not None and (now - last_fired) < _FANOUT_EDGE_COOLDOWN_SEC:
        logger.debug(...)  # DEBUG, not WARNING — expected, frequent traffic shaping
        return False
    _fanout_edge_last_fired[edge] = now   # timestamp recorded on ACCEPT, before dispatch
    return True
```

`_fanout_handler`'s downstream-dispatch loop (`core/loop/autonomous_loop.py`, inside
`_fanout_handler`) now reads:

```python
for district, task_type, params_template in get_downstream_tasks(event.event_type):
    edge = (et, district, task_type)
    if not _fanout_edge_should_fire(edge):
        continue
    params = {k: (v.format(event_type=et, event_data=str(getattr(event, 'data', {})))) for k, v in params_template.items()}
    task = {"type": task_type, "district": district, "params": params, "source_event": et}
    asyncio.create_task(governor.dispatch(task))
```

The cooldown timestamp is written inside `_fanout_edge_should_fire` **before** `continue`
is ever reached and before `governor.dispatch()` is invoked — i.e. on acceptance, not on
result. Because `asyncio.create_task(governor.dispatch(task))` is fire-and-forget, the
call always "succeeds" from the loop's point of view regardless of what happens inside
`dispatch()` — success, an exception, or a `{"status": "no_agents", ...}` result all
consume the cooldown identically, since none of them can un-write a timestamp that was
already written before the task was even created. Verified by tests (see below).

## 5. Strategy edge retirement (B6)

**Retired.** Verification performed independently from source (not from the task
prompt's claim):

1. `config/agent_manifest.yaml` — the file's `districts:` map has 39 top-level district
   keys (`coding`, `research`, ... `growth`); **no `strategy:` key exists**. Grepped for
   "strategy" anywhere in the file: it appears only inside unrelated agent names/
   capabilities (`strategy_recommender` under `predictive_analytics`, `deal_strategy`,
   `win_strategy`, `social_media_strategy`, etc.) — never as a district.
2. `districts/` directory listing has 38 subdirectories; **no `districts/strategy/`**.
3. `run_vector.py:bootstrap_agents()` only creates a baseline agent for districts that
   appear as a manifest entry (`districts = sorted({entry.get("district", "") for entry
   in definitions ...})`); since `strategy` never appears in any manifest entry's
   `district` field, it never gets even a baseline agent.
4. `core/city/agent_registry.py::AgentRegistry.get_by_district()` does exact string
   equality (`a.district == district`), not fuzzy matching — so no other district's
   agents could accidentally satisfy a `"strategy"` lookup either.
5. `core/city/governor.py:2082-2083` confirms the resulting behavior on any dispatch to a
   district with zero agents: `logger.warning("no agents in {district}")` +
   `{"status": "no_agents", "district": district}` — this is exactly what every dispatch
   to `strategy::review_analytics_insights` would produce, forever, with zero possible
   effect.

Removed **only** the one entry `("strategy", "review_analytics_insights",
{"analytics_source": "{event_type}"})` from `EVENT_TRIGGER_MAP[EventType.ANALYTICS_READY]`
in `core/event_bus/wiring.py`. The other two entries in that same list
(`content::optimize_from_analytics`, `marketing::adjust_campaign_from_analytics`) are
untouched, as is every other `EVENT_TRIGGER_MAP` key, `DISTRICT_SUBSCRIPTIONS`, and
`PUBLISH_EVENTS` (district-only keying left exactly as-is, per explicit instruction).

## 6. Files changed

| File | Change |
|---|---|
| `core/loop/autonomous_loop.py` | Added `import time`; added module-level `_FANOUT_EDGE_COOLDOWN_SEC`, `_fanout_edge_last_fired` dict, and `_fanout_edge_should_fire()` helper directly above `class AutonomousLoop`; added a 2-line cooldown gate (`edge = ...`, `if not _fanout_edge_should_fire(edge): continue`) inside `_fanout_handler`'s existing downstream-dispatch loop. No other line in the file touched — `__init__`, the Goal feedback loop, and any PolicyMemory/reward-writing code are all untouched. |
| `core/event_bus/wiring.py` | Removed one entry (`"strategy", "review_analytics_insights"`) from `EVENT_TRIGGER_MAP[EventType.ANALYTICS_READY]`, with a comment explaining why and pointing at this doc. Nothing else in the file changed. |
| `core/config.py` | Added `FANOUT_EDGE_COOLDOWN_SEC: float = Field(120.0, ge=0.0, le=3600.0)` to `VectorSettings` (next to `VC_LLM_LOOP_GUARD_COOLDOWN_SEC`) and `"fanout_edge_cooldown_sec": _s.FANOUT_EDGE_COOLDOWN_SEC` to the `CONFIG` dict. |
| `tests/loop/test_fanout_cooldown.py` | New file, 15 tests (see below). |

## 7. Test results

```
python -m pytest tests/loop/test_fanout_cooldown.py -v
======================== 15 passed, 1 warning in 3.25s ========================

python -m pytest tests/event_bus/ tests/loop/ -v
======================== 81 passed, 1 warning in 8.72s ========================
```

No pre-existing test in `tests/event_bus/` or `tests/loop/` (including
`tests/loop/test_autonomous_loop.py`) regressed. `python -c "from core.config import
CONFIG; print(CONFIG.get('fanout_edge_cooldown_sec'))"` prints `120.0`, confirming
`core/config.py` still loads and validates cleanly with the new field.

All governor interaction in every test is a `MagicMock`/`AsyncMock` — no real
`Governor.dispatch`, `PermissionGateway`, agent, or district code executes. No network,
subprocess, or live-process interaction anywhere in the test file.

Mapping to the 10 required proof points:

1. **First event fires** — `TestFanoutHandlerCooldown::test_first_dispatch_fires`
2. **Duplicate inside window dropped** — `test_duplicate_event_inside_window_dropped`
3. **Fires again after cooldown elapses** — `test_fires_again_after_cooldown_elapses`
   (both the unit-level `TestFanoutEdgeShouldFire` version with a mocked
   `time.monotonic`, and the handler-level integration version)
4. **Failed dispatch still consumes cooldown** —
   `test_failed_dispatch_still_consumes_cooldown` (`governor.dispatch` raises
   `RuntimeError`; second attempt inside the window still dropped)
5. **`no_agents` result still consumes cooldown identically** —
   `test_no_agents_result_still_consumes_cooldown`
6. **Two different edges, independent cooldowns** —
   `TestFanoutEdgeShouldFire::test_different_edges_have_independent_cooldowns` (unit) and
   `TestFanoutHandlerCooldown::test_two_different_edges_from_same_event_are_independent`
   (integration, via a real `MARKETING_PUBLISHED` event fanning to two districts)
7. **Restart resets cooldowns** — `test_restart_resets_cooldowns` (unit, clears the dict)
   and `test_restart_via_fresh_instance_resets_cooldown` (integration, fresh dict + fresh
   `AutonomousLoop()` instance, edge fires immediately)
8. **Event type not in `EVENT_TRIGGER_MAP` -> zero dispatches** —
   `test_event_type_not_in_trigger_map_dispatches_nothing`, using `EventType.
   TASK_SCHEDULED` and asserting `get_downstream_tasks(...) == []` directly as well as
   `governor.dispatch.call_count == 0` through the handler
9. **Edge set unchanged except the one retired edge** —
   `test_event_trigger_map_edges_unchanged_except_retired_strategy_edge`, module-level
   test comparing a hardcoded pre-change snapshot of every `(event_type, district,
   task_type)` triple (recorded by reading `wiring.py` before editing it) against the
   live `EVENT_TRIGGER_MAP`; asserts zero new edges and that any missing edge is a subset
   of `{(ANALYTICS_READY, "strategy", "review_analytics_insights")}`
10. **`Governor.dispatch`'s own behavior untouched** —
    `test_cooldown_gate_does_not_alter_governor_dispatch_call`: reconstructs the exact
    task dict `get_downstream_tasks()` + the same param-formatting logic would produce
    with **no** cooldown gate involved at all, and asserts it is byte-for-byte identical
    to what the cooldown-gated handler actually passed to `governor.dispatch()` — showing
    the gate is a pure "call or don't call" filter that never touches the call's shape,
    routing, or arguments.

## 8. Residual concerns

- **The `PUBLISH_EVENTS` district-only-keying gap is still open**, as explicitly scoped
  out of this task. A district publishing under one task type is indistinguishable from
  the same district publishing under a different task type for cooldown purposes, because
  the *source* event itself doesn't carry task-type granularity going in — this R2 change
  only dedups the *downstream* edge, which is already as fine-grained as the wiring data
  model allows without the re-keying task explicitly deferred to a later remediation pass.
- **120s is a first-pass constant, not tuned against real traffic.** It was not measured
  against the (now-closed) 7-day experiment's actual event-arrival cadence; if a future
  experiment shows genuine bursts of legitimately-different work landing on the same edge
  within 120s, the fix is a `CONFIG` override (`fanout_edge_cooldown_sec`), not a code
  change.
- **Module-level state means a single process only.** If VECTOR is ever run with multiple
  `AutonomousLoop`-hosting processes sharing one event bus, each process gets its own
  independent cooldown table — by design for this task (B5 requires plain in-memory, no
  persistence), but worth flagging if multi-process fan-out is ever built.
- **The `strategy` district retirement is wiring-only.** `DISTRICT_SUBSCRIPTIONS["strategy"]`
  (used by `auto_subscribe_all()`/`get_subscriptions_for()`, a separate mechanism from
  `EVENT_TRIGGER_MAP`) was deliberately left untouched per the explicit instruction to
  remove only the one `EVENT_TRIGGER_MAP` entry — if a real `strategy` district agent is
  ever registered in the future, its event *subscriptions* are unaffected by tonight's
  change; only this one fan-out *trigger* edge was retired.
