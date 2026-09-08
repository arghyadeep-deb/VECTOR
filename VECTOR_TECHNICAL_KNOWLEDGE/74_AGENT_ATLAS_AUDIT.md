# Task 74 — Agent Atlas: Phase 1 Audit

Read-only backend tracing (Python source only — no execution, no DB, no experiment interaction) plus
a re-read of the relevant frontend files already cataloged in Task 73's own audit. This document is
the evidence base for `74_AGENT_ATLAS.md`'s design; every claim below is either a direct source
quote/citation or explicitly marked as unconfirmed.

## 1. Two Separate, Non-Identical Agent Registries (the central finding)

**`GET /agents`** (`core/api/routers/agents.py` → `core/api/crud.py::get_agents()` →
`core.city.agent_registry.get_registry().list_all()`) — the **live, HP-driven city registry**.
`AgentBase.to_dict()` (`core/city/agent_base.py:411-425`) returns exactly:
```
id, name, district, generation, health_points, model, ghost_memory, lessons,
best_decisions, personality_traits, created_at, last_active
```
`AgentRegistry.list_all()` (`core/city/agent_registry.py:285-311`) adds two more fields on top:
`agent_id` (duplicate of `id`), `status` (via `_lifecycle_status()`, lines 313-326 — **a pure
HP-tier label**: `elite ≥800`, `strong ≥600`, `healthy ≥400`, `weakened ≥200`, `critical ≥1`,
`dead =0`), and `is_alive` (boolean, `health_points > 0`).

**Confirmed absent from this record, source-verified, not assumed:** no `capabilities` field, no
`current_task` field, no `provider` field (only `model`), no `permission_tier` field. `status` is
explicitly an HP lifecycle label, **not** an execution-state label — it cannot honestly be rendered
as "ACTIVE" or "EXECUTING."

**`GET /a2a/agents`** (`core/api/routers/a2a.py:135-154`) — a **completely different registry**,
`vectorcode.src.agents.registry.get_registry()` (note the different import path — this is not the
same object as `core.city.agent_registry`). Each entry:
```
name, class_name, district, description, model, capabilities
```
**This is where real, declared `capabilities` data actually lives** — confirmed via direct source
read of the handler (`getattr(defn, "capabilities", [])`). `GET /a2a/districts/{name}` (line 157-181)
returns the same shape for a single agent, plus an `endpoints.invoke` URL.

**Consequence for the Atlas design:** a truthful agent representation must merge these two sources by
`name` (best-effort — no shared ID was found linking them) and clearly attribute each field to its
real source. Neither source alone answers "what can this agent do AND is it alive/healthy" —
`core.city.agent_registry` answers the second, `vectorcode.src.agents.registry` answers the first.

## 2. Task / Execution Data — Traced, Found Structurally Empty in Practice

`POST /a2a/districts/{name}/invoke` (a2a.py:187-213) is the **only** writer of the module-level
`_TASKS` dict; `GET /a2a/districts/{name}/tasks/{task_id}` (line 216-221) is its only reader.
`_TASKS` is a plain in-process Python dict, not persisted. **No call site anywhere in
`autonomous_loop.py`, `governor.py`, or the A2A router itself was found that routes VECTOR's own
internal dispatch through this specific HTTP endpoint** — consistent with Task 60's own established
finding that `Governor.dispatch()` calls `agent.run(task)` directly, in-process, never via this A2A
HTTP surface. **Conclusion: `_TASKS` is, in practice, populated only by an external A2A-protocol
client actually calling `/invoke` — which the Atlas will never do (read-only) — so per-agent task
data via this path is NO LIVE SOURCE for the Atlas's purposes**, not merely unconfirmed.

`GET /scheduler/jobs` (`SchedulerJobsResponse{total, active, jobs}`, `core/api/schemas.py:194-197`)
is real but represents **APScheduler-style scheduled jobs** (the cron jobs cataloged in Task 61's own
protocol doc — `job_subconscious_loop`, `job_daily_review`, etc.), a different concept from
"an agent is currently executing a capability." Not conflated with agent activity in the Atlas.

## 3. District Data

`GET /city/districts` (`core/api/routers/city.py:22-31`) is real and read-only (a `GET`, not
mutating despite going through `GovernorCouncil.dispatch({"type": "list_districts", ...})`
internally). **Its exact response shape was not traced further this task** (would require reading
`GovernorCouncil`'s internal `"list_districts"` handler, out of this audit's time budget) — the
Atlas frontend must treat its shape as **unconfirmed** and defensively fall back to a client-computed
district grouping from the already-real `/agents` list (grouping by the confirmed-real `district`
field), exactly matching the existing defensive-fallback pattern already used by `F.council`
(Task 73's audit, §1).

`POST /city/dispatch` exists and is a real, consequential, arbitrary-Governor-dispatch endpoint —
**never called by the Atlas**, confirmed by design (this task's implementation contains zero POST
calls, see §6 of the companion document).

## 4. Tools / Capability-Adjacent Data

`GET /tools/registry` (`ToolsRegistryResponse{total_tools, scopes, permission_levels}`,
`core/api/schemas.py:219-222`) is real. `permission_levels: dict[str, int]` is a genuinely
interesting real signal, but its key/value semantics (does `int` map to GREEN/YELLOW/RED/FORBIDDEN,
and by what convention?) were **not traced this task** — the handler body itself was not read.
**Not used to render a per-agent/per-capability permission tier this task**, since doing so without
confirming the mapping would risk exactly the kind of implied-but-unverified classification Task 74
explicitly warns against. Documented as a future contract item instead.

## 5. Existing Frontend (re-confirmed from Task 73, not re-derived)

- `F.districts` (`widgets.js:323-365`) — already fetches `/agents`, renders up to 18 as flat HP-bar
  cards, no district grouping, no drill-down, no capability data. This is the panel the Atlas
  supplements, not replaces (task's own "do not modify existing panels" instruction).
- `backend.js`'s `adaptAgent()` (line 56-67) already normalizes `/agents`/`/world/snapshot` agent
  records into `{id, name, district, health_points, generation, tier, model, last_active}` — the
  Atlas's own normalization layer follows this exact same shape for consistency, extending it rather
  than inventing a parallel convention.
- `V.on('state_event', ...)` in `backend.js` (line 567-612) already handles real WS event types
  `AGENT_HP_CHANGED`, `DECISION_MADE`, `TASK_ROUTED`, `ANOMALY_DETECTED`, `HYPOTHESIS_SURFACED`,
  `CITY_UPDATE` — these are the **only** confirmed-real event types flowing over the WS channel. The
  Atlas's activity stream (§9 of the companion doc) listens to these same events via `V.on`, adding
  no new WS surface, and renders only these types — never a fabricated event.
- `POS`, `PANEL_MATCHERS`, `WIDGETS` (Task 73's own additions already established the exact wiring
  pattern) — reused identically for `agentatlas`.

## 6. What This Confirms For Task 74's Explicit Requirements

| Requirement | Real source? | Verdict |
|---|---|---|
| District hierarchy | `/agents`'s `district` field (real) + `/city/districts` (real, shape unconfirmed) | Client-side grouping from `/agents` is the reliable baseline; `/city/districts` attempted first, defensively |
| Agent list per district | `/agents` filtered by `district` | Real |
| Agent health/status | `/agents`'s `health_points`/`status` | Real, but `status` is HP-tier, not execution-state — labeled precisely |
| Declared capabilities | `/a2a/agents`'s `capabilities` | Real, separate source, merged by name |
| Reachable capability | — | **No real signal found** — "declared" ≠ "reachable" cannot be honestly distinguished without invoking, which the Atlas will never do. Rendered as "UNKNOWN — not distinguishable from declared without invocation" |
| Currently-executing capability | — | **No real signal found anywhere traced** — always "NOT OBSERVED" |
| Current/recent task | `_TASKS` (a2a.py) | **Structurally empty in practice** (§2) — "NO LIVE SOURCE" |
| Permission tier (per agent/capability) | `/tools/registry`'s `permission_levels` | Real field exists; semantics unconfirmed this task — not rendered as a classified tier; documented as a future contract |
| Activity stream | WS `state_event` types (§5) | Real, capped, passive — no new polling |
