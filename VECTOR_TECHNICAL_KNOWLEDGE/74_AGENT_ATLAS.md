# Task 74 — Agent / District Civilization Atlas

Frontend-only. Segment 2 was not interacted with. See STATUS at the end for full disclosure. Phase-1
evidence is in the companion `74_AGENT_ATLAS_AUDIT.md` — this document is the design/implementation
record built on that evidence.

---

## 1. Existing Agent/District Architecture (summary — full evidence in the audit doc)

VECTOR exposes agent data through **two genuinely different backend registries**, not one:
`core.city.agent_registry` (the live, Darwinian HP-based city registry — `GET /agents`) and
`vectorcode.src.agents.registry` (a declarative agent-definition registry — `GET /a2a/agents`,
`GET /a2a/districts/{name}`). Neither alone answers both "is this agent alive/healthy" and "what can
this agent do." The existing frontend (`F.districts` in `widgets.js`) only ever used the first, as a
flat 18-item HP-bar list with no drill-down and no capability data. The Atlas is the first place in
this codebase that merges both sources honestly.

## 2. Real Data Sources (confirmed by direct source read, not assumed)

| Source | Endpoint | Real? | Provides |
|---|---|---|---|
| Live city registry | `GET /agents` | Yes | `id, name, district, generation, health_points, model, last_active, status(HP-tier), is_alive` |
| Declarative registry | `GET /a2a/agents` | Yes | `name, class_name, district, description, model, capabilities` |
| Single declared agent | `GET /a2a/districts/{name}` | Yes | Same shape, single record |
| Districts (Governor-derived) | `GET /city/districts` | Yes, shape unconfirmed | Attempted, defensively; falls back to client-side grouping of `/agents` by its real `district` field |
| Per-agent task | `GET /a2a/districts/{name}/tasks/{task_id}` | Real endpoint, but backing store (`_TASKS`) has no confirmed writer under normal VECTOR operation | Not used — see audit §2 |
| Activity | WS `state_event` (`AGENT_HP_CHANGED`, `TASK_ROUTED`, `DECISION_MADE`, `ANOMALY_DETECTED`) + `decision_made` | Yes, already wired in `backend.js` | Passive, capped activity stream |
| Tool permission levels | `GET /tools/registry`'s `permission_levels` | Real field, semantics unconfirmed | Not rendered as a classified tier this task (§9) |

**Never called:** `POST /city/dispatch`, `POST /a2a/districts/{name}/invoke` — both are real but
consequential (they dispatch actual work through the Governor). The Atlas issues **zero** POST/PUT/
DELETE calls anywhere in its implementation — verified by direct code review: every network call in
`F.agentatlas` is `apiGet(...)`.

## 3. Atlas Information Model

```
VECTOR (implicit — the whole HUD)
  └─ GOVERNOR (implicit — the routing layer; no separate "governor" data exists to display beyond this label)
      └─ DISTRICT  (client-computed group of /agents by real `district` field, or /city/districts if its shape matches)
          └─ AGENT  (merged: live registry record ⊕ declared-registry record, joined by name)
              ├─ CAPABILITIES (declared only — from /a2a/agents; "reachable" and "currently used"
              │                are NOT rendered as distinct states — see §6)
              └─ TASK (always "NOT OBSERVED" — no real per-agent execution signal exists, audit §2)
```

GOVERNOR is rendered as a breadcrumb label only (`VECTOR › GOVERNOR › <district> › <agent>`) — there
is no dedicated Governor status endpoint to show real data for, so it is not given its own data
panel, only its structural place in the hierarchy.

## 4. District Hierarchy (implementation)

`districtGroups()` groups the merged agent list by each agent's real `district` field — the same
approach `F.districts`/`refreshDistricts()` already implicitly use (grouping is new; the field itself
is not). `/city/districts` is fetched and stored (`S.districtsShape`) but **not currently rendered
directly**, since its shape was not traced this task (audit §3) — it is fetched defensively so a
future pass can start using it once its shape is confirmed, without needing a new network call added
later. The Macro Map's per-district card shows `N agent(s)` (a real count) and `X / Y alive` (a real,
client-computed count from each agent's real `status` field) or `HEALTH UNKNOWN` if no agent in that
group has a `status` at all (e.g., a declared-only district with no live registry entries).

## 5. Agent Representation

Every agent record shown is the literal merge described in §2 — `mergeAgents()` in `widgets.js`. Three
honest distinctions are made explicit in the UI itself, not just in this document:
- **`status` is always labeled as an HP-tier** (`ELITE`/`STRONG`/`HEALTHY`/`WEAKENED`/`CRITICAL`/
  `DEAD`/`UNKNOWN`), colored via the same `hpColor()` mapping used elsewhere in the codebase for HP
  tiers — never re-labeled as "ACTIVE."
- **`declaredOnly` agents** (present in `/a2a/agents` but not found in the live `/agents` list) are
  flagged in the inspector: `"(declared only — not in live registry)"`.
- **CURRENT TASK is always literally the string `"NOT OBSERVED"`** — never inferred, never left blank
  (a blank field could be misread as "loading"; the explicit string cannot be).

## 6. Capability Representation

Capabilities come exclusively from the declared registry (`/a2a/agents`). Each capability row shows
two badges: `DECLARED` (always true if it's in the list — this is definitionally what "declared"
means) and `USAGE: UNKNOWN` (with a tooltip explaining why: *"cannot be distinguished from declared
without invocation"*). **Per Task 74's own explicit instruction, "reachable" and "currently used" are
NOT rendered as separate, more-confident states than "declared"** — the audit (§6 table) found no
real signal that would let this frontend honestly claim a capability is reachable or in-use without
actually invoking it, which the Atlas will never do. If an agent has no entry in `/a2a/agents` at
all, the capabilities section says exactly that (`"no declared-capability source found for this
agent"`) rather than showing an empty list indistinguishable from "zero capabilities."

## 7. Task Representation

Always `"NOT OBSERVED"`, for the reason established in the audit (§2): the one real per-agent task
store (`_TASKS` in `a2a.py`) has no confirmed writer under VECTOR's actual internal dispatch path.
This is a deliberate, permanent design choice for this data source, not a temporary placeholder — it
would only change if a future backend endpoint genuinely exposing live task state were built (§13).

## 8. Permission Representation

**Not rendered as a classified tier anywhere in the Atlas.** The inspector explicitly states:
`"NOT CLASSIFIED AT AGENT LEVEL — VECTOR classifies by action_type, not by agent"` — this is not a
missing-data placeholder, it is an architecturally accurate statement (confirmed across this entire
session's own security work, Tasks 57-60: `PermissionConfig`'s RED/YELLOW/GREEN lists are keyed by
`action_type`, never by agent). Showing a per-agent "permission tier" would have been a fabrication of
a distinction that does not exist in VECTOR's actual security model, not merely an unavailable data
point — the task's own warning against implying an unclassified capability's tier is known is honored
by *not inventing the concept*, not just by leaving a field blank.

## 9. Activity Representation

A capped (30-entry) in-memory ring buffer, populated **only** by the same real WS event handlers
`backend.js` already listens for (`state_event` with `AGENT_HP_CHANGED`/`TASK_ROUTED`/
`DECISION_MADE`/`ANOMALY_DETECTED`, plus `decision_made`) — the Atlas adds its own `V.on()` listeners
(read-only observation of the existing event bus, not a new WS connection) and filters the buffer to
whatever entity is currently selected (by `agent_id` for the agent view, by `district` for the
district view). **No event type is rendered that wasn't confirmed real in the audit.** The buffer is
cleared implicitly on panel close (it's panel-local state, not global) and capped so it cannot grow
unbounded even across a long session.

## 10. Real vs. Unavailable Data — Summary Table

| Field | Real? | Rendered as |
|---|---|---|
| District name, agent count | Real | Plain value |
| Agent alive/HP-tier count per district | Real (computed) | `"X / Y alive"` or `"HEALTH UNKNOWN"` |
| Agent name, district, generation, HP, model, last_active | Real | Plain value or `UNKNOWN` |
| Agent status | Real, HP-tier only | Explicit tier label, never "active" |
| Declared capabilities | Real | List, or explicit "no source found" |
| Capability reachability/usage | **No real signal** | `USAGE: UNKNOWN` |
| Current task | **No real signal** | `"NOT OBSERVED"` (literal) |
| Provider | **No field exists** | `UNKNOWN` |
| Permission tier | **Not an agent-level concept** | Explicit architectural statement, §8 |
| Activity events | Real (WS, capped) | Timestamped list or "no observed events yet" |

## 11. Files Changed

- `frontend/js/widgets.js` — added `F.agentatlas` (macro map / district view / agent inspector /
  capability list / activity stream / text filter, ~200 lines), one `POS` entry, one
  `PANEL_MATCHERS` entry (placed before the existing broad `district|districts|agent|agents` matcher
  so more specific phrases aren't swallowed by it).
- `frontend/js/terminal.js` — added `agentatlas` to the `WIDGETS` listing (`ls`/`panels`).
- `frontend/styles/widgets.css` — appended one new CSS block (~50 lines) for the Atlas's own classes,
  reusing the existing token set exclusively (no new colors, no font sizes outside the established
  7-10px range for this density of panel).

**No other file was modified.** `F.districts` (the existing panel) was **not** touched — per the
task's explicit "prefer new atlas + existing panels over rewriting existing panels" instruction.

## 12. Files Created

None (code — same reasoning as Task 73: the widget-factory pattern keeps all panels in the shared
`widgets.js`). Documentation: this file and `74_AGENT_ATLAS_AUDIT.md`.

## 13. Future Backend Contracts (NOT implemented — typed interfaces only)

```ts
// Confirm the real shape of GET /city/districts before building anything
// against it further — this task fetched it defensively but does not yet
// render it, since its shape is unconfirmed (audit §3).
interface DistrictSummary {
  name: string;
  agent_count?: number;
  // Exact additional fields UNKNOWN — GovernorCouncil.dispatch({"type":"list_districts"})'s
  // internal handler was not traced this task.
}

// Would resolve §7's permanent "NOT OBSERVED" task state — does not exist today.
interface AgentTaskProvider {
  getCurrentTask(agentId: string): Promise<{
    task_id: string; status: 'queued'|'running'|'completed'|'failed'|'blocked'|'deferred';
    started_at: string; updated_at: string; result?: unknown;
  } | null>;
  // Must be backed by VECTOR's OWN internal dispatch path (autonomous_loop /
  // Governor.dispatch()), not the a2a.py _TASKS dict, which this audit
  // confirmed has no real writer under normal operation.
}

// Would resolve §6's permanent "USAGE: UNKNOWN" — does not exist today, and
// per the task's own instruction, should NEVER be inferred from mere
// declaration; it must reflect actual observed invocations.
interface CapabilityUsageProvider {
  getRecentInvocations(agentId: string, capability: string): Promise<Array<{
    at: string; outcome: 'ok'|'error'; via: string; // e.g. "governor.dispatch" | "a2a.invoke"
  }>>;
}

// Would let §8 show a genuine per-action-type tier instead of the current
// (accurate) "not an agent-level concept" statement, by resolving
// /tools/registry's permission_levels semantics.
interface ToolPermissionMapProvider {
  getPermissionLevelMeaning(): Promise<Record<number, 'GREEN'|'YELLOW'|'RED'|'FORBIDDEN'|'UNKNOWN'>>;
}
```

All four are explicitly deferred until after Segment 2 concludes, per the task's absolute rule
against backend changes during the running experiment.

## 14. Performance

- One `/agents` + one `/a2a/agents` + one `/city/districts` fetch per 20s while the panel is open
  (matching `F.districts`' own 10s / `F.council`'s own 15s convention — not more aggressive than the
  existing panels).
- No per-agent, per-district, or per-capability polling — the merge happens client-side, once, from
  the two list-level fetches.
- Activity buffer is hard-capped at 30 entries (`ACTIVITY_CAP`), enforced on every push — cannot grow
  unbounded even across a very long session.
- No new WebSocket connection — reuses the existing `V.on()` event bus subscriptions.
- District/agent lists are not virtualized — acceptable given VECTOR's own agent count (170, per
  Task 66's `smoke` output) rendered as short per-district lists, not one 170-row table; revisit if a
  single district ever grows into the hundreds.

## 15. Accessibility

Inherits `shell()`'s existing `role="dialog"`, `aria-label`, `tabindex="-1"` + focus-on-open/close
management, identical to every other panel (Task 73 §14 established this is automatic for any
`F.<id>` factory). Navigation (district card → agent row → back via breadcrumb) is implemented with
real `<div>` click handlers with visible hover/focus styling via the existing `--accent` border
convention — **not yet keyboard-navigable via Tab/Enter on the cards/rows themselves** (they are
`click`-bound `div`s, not `button`/`a` elements) — this is a genuine gap, disclosed rather than
silently left, and listed in §16 as a near-term follow-up rather than fixed under this task's already
large scope.

## 16. Post-Experiment Improvements

1. Make district/agent/capability rows genuine `<button>` elements (or add `tabindex`+`keydown`
   handling) so the drill-down navigation is keyboard-accessible, closing the gap noted in §15.
2. Once `/city/districts`'s shape is confirmed, render its real per-district fields directly instead
   of the current client-side grouping fallback.
3. Implement the four backend contracts in §13, in priority order: `AgentTaskProvider` first (closes
   the single most-asked-about gap — "what is this agent actually doing right now"), then
   `CapabilityUsageProvider`, then `ToolPermissionMapProvider`, then the `DistrictSummary` shape
   confirmation.
4. Once Task 72's Learning Architecture V2 work begins (itself gated on the experiment concluding),
   consider whether the Atlas's Agent Inspector should surface any of that work's proposed
   provenance/state-change log (Task 72 §7) as a per-agent "recent learning events" section — not
   attempted this task, since that log does not exist yet.

---

## STATUS

```
git HEAD unchanged: YES (5964a331678ac648c8289f4c38fd0e5430e1ee9d, before and after)
Experiment process untouched: YES
Experiment DB untouched: YES
Experiment logs untouched: YES
Experiment configuration untouched: YES
Production cognitive/runtime Python changed: NO (0 .py files — diff count unchanged at 64, the
  same pre-existing set from every prior task in this series)
Scheduler changes: NO
Permission changes: NO
Memory changes: NO
Decision changes: NO
Synthetic stimulus: NO
```

- **Files changed:** `frontend/js/widgets.js`, `frontend/js/terminal.js`, `frontend/styles/widgets.css`.
- **Files created:** `VECTOR_TECHNICAL_KNOWLEDGE/74_AGENT_ATLAS_AUDIT.md`,
  `VECTOR_TECHNICAL_KNOWLEDGE/74_AGENT_ATLAS.md`.
- **Frontend functionality added:** `F.agentatlas` — a navigable Macro Map → District View → Agent
  Inspector → Capability list, plus a passive real-event activity stream and a client-side text
  filter, wired into `POS`, `PANEL_MATCHERS`, and the terminal `WIDGETS` list exactly like every
  existing panel. No new dock button (the dock's lean 6-button design was preserved, per instruction).
- **Real endpoints/data sources used:** `/agents`, `/a2a/agents`, `/city/districts` (fetched, not yet
  rendered), plus the existing WS `state_event`/`decision_made` event bus.
- **Unavailable data, honestly represented:** per-agent current task (`"NOT OBSERVED"`), capability
  reachability/usage (`"UNKNOWN"`), provider (`"UNKNOWN"`), agent-level permission tier (explicit
  architectural statement, not a blank).
- **Mock data:** none, anywhere in this implementation.
- **Future backend contracts:** four typed interfaces, §13 — none implemented.
- **Tests performed:** `node --check` syntax validation on both modified JS files (pass); CSS
  brace-balance check (478/478, pass); `git status`/`git diff --name-only -- '*.py'` before-and-after
  comparison confirming zero backend files touched and the pre-existing 64-file `.py` diff set
  unchanged; direct source read confirming zero POST/PUT/DELETE calls anywhere in the new code.
  Interactive browser verification (panel open/close, click-through navigation, empty/offline states,
  responsive layout, keyboard nav) was **not** performed this task — no working browser connection
  was available in this session (confirmed via a failed `tabs_context_mcp` call) — disclosed
  explicitly rather than claimed. §15 already discloses the one known gap (row-level keyboard
  navigation) this would most likely have caught first.
