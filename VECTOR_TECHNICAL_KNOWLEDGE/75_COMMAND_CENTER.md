# Task 75 — VECTOR Command Center / Workspace Evolution

Frontend-only. No backend, no Python, no running experiment process touched at any point
in this task. See `75_COMMAND_CENTER_AUDIT.md` for the full Phase-1 read-only source audit
this build is based on — this document covers the Phase-2 implementation.

---

## 1. Existing Navigation Architecture (summary — full detail in the audit)

Before this task, a user reached any of the ~50 existing panels through three independent,
already-working mechanisms: the command bar / voice (`PANEL_MATCHERS` regex list scanned by
`localReply()`), the hidden terminal (`Ctrl+Shift+H`, `WIDGETS` flat id list), and the dock's
`PANELS` button (which only toggled `#workspace` visibility, with no picker of its own). There
was no visual, browsable path from "workspace is open" to "a specific panel is open" — that
gap is what the Command Center closes. Full shortcut inventory, `openWidget`/`closeWidget`/
`shell()` mechanics, and the Escape-scoping behavior are documented in `75_COMMAND_CENTER_AUDIT.md`
§2–3 and were re-verified, not re-derived, for this build.

## 2. Command Center Architecture

`F.commandcenter` is a new widget factory in `frontend/js/widgets.js`, built with the same
`F.<id> = function(){...; return shell(...)}` pattern every other panel uses — it is **a panel
that browses panels**, not a second routing system. It renders one of three views inside a
single `shell()`-built dialog:

- **Home** — Active / Pinned / Recent chip rows, then a domain-card grid.
- **Domain** — the panel list for one domain, reached by clicking a domain card.
- **Search** — a flat filtered panel list, reached by typing in the search box.

Every "open" action anywhere in the Command Center — a domain-list row, a chip, a search
result — calls the exact same `V.openWidget(id)` that `PANEL_MATCHERS` and the terminal already
call (`openPanel(id)` at widgets.js:1064 is a one-line wrapper, not a new mechanism). Opening
the Command Center itself goes through the same path, so it inherits `V.openWidget`'s existing
auto-wake / auto-open-workspace behavior for free.

## 3. Domain Taxonomy

14 domains, defined as frontend-only metadata (`DOMAINS`, widgets.js:986-1001) layered on top
of the existing flat `F`/`POS`/`PANEL_MATCHERS`/`WIDGETS` registries — none of those registries
were restructured. Every panel id in `DOMAINS` is filtered through `panelExists(id)`
(`typeof F[id]==='function'`) at render time via `domainPanels(dom)`, so a domain silently
shrinks rather than ever showing a dead entry if a panel is later renamed or removed.

| Domain | Panels (declared, verified against `F` at render) |
|---|---|
| COGNITION | cognition, brainpanel (2) |
| MEMORY | memory, memoryexplorer, knowledgepanel (3) |
| GOALS | goals, goalplanner (2) |
| PLANNING | missioncontrol, workpanel (2) |
| CIVILIZATION | agentatlas, districts, agentspanel (3) |
| SECURITY | security, approvals, council, privacypanel (4) |
| INFERENCE | telemetry, corepanel (2) |
| SENSING | camerapanel, pccontrol, healthpanel, webcam (4) |
| COMMUNICATION | chat, voicestudio (2) |
| FINANCE | finance, trading, backtest, hedgebot, market (5) |
| KNOWLEDGE | codeintel, codegraph, researchpanel, answerengine, vectorcodepanel (5) |
| MEDIA | mediastudio, comfyui, hyperframes, contentpanel, designpanel, music (6) |
| SYSTEM | features, platformpanel, analyticspanel (3) |
| EXPERIMENT | experiment (1) |

44 panel references across 14 domains (each checked live against `F[id]` — a domain with zero
currently-existing panels would simply not render its card; none currently hit that case).
The taxonomy was derived by reading every existing `F.<id>` factory and its subject matter
(during the audit), not invented independently of the code — this satisfies the task's "derive
from actual panels" requirement. `PANEL_META` (widgets.js:934-979) supplies a human label and a
search-alias string per panel id; both are optional metadata that degrade to the raw id if
missing (`panelLabel()`, widgets.js:980).

## 4. Panel Registry Integration

No new panel registry was created. `DOMAINS[].panels` references ids from the same `F` map
every other mechanism uses. `panelExists(id)` is the only new predicate, and it is a direct
`typeof` check against `F`, not a maintained list — so it can never claim a panel exists that
doesn't. `POS.commandcenter:[14,6]` (widgets.js:38) and a `PANEL_MATCHERS` entry
(widgets.js:2450, placed before the `agentatlas` entry) wire the Command Center itself into the
existing position and command-bar/voice mechanisms exactly like every prior panel. `terminal.js`'s
`WIDGETS` array gained `'commandcenter'` (inserted after `'experiment','agentatlas'`), so `ls`,
`panels`, and typing `commandcenter`/`open commandcenter` in the terminal all work identically
to any pre-existing panel — no special-casing.

## 5. Search Implementation

Client-side only, no new fetch. `searchInput`'s `input` event (widgets.js:1050) sets
`S.q`/`S.view='search'` and re-renders; `renderSearch()` (widgets.js:1139-1155) builds a
haystack per panel from `id + label + alias + domain label` (reusing `PANEL_META`, not a new
search index) and does a plain case-insensitive substring match, deduped via `Set`. This
deliberately reuses `PANEL_META`'s alias strings — the same kind of free-text association
`PANEL_MATCHERS`' regexes encode — rather than building a second, parallel keyword table.
Escape while the search box has content clears the query and returns to Home
(widgets.js:1051), scoped with `stopPropagation()` so it doesn't bubble to the global Escape
handler.

## 6. Keyboard Navigation

- **Tab** — every interactive element (search input, breadcrumb buttons, domain-card buttons,
  panel-row open/pin buttons) is a real focusable `<input>`/`<button>`, so native Tab order
  works with no custom handling needed.
- **Enter / Space** — native `<button>` activation; no keydown re-implementation was written
  for activation, since real buttons already do this correctly.
- **Escape** — inherited for free from `shell()` (closes only the Command Center panel,
  `stopPropagation()`'d, per the audit's §2 finding) plus a local Escape-in-search-box case
  (clears the query, does not close the panel) — no second competing global handler was added.
- **Ctrl/Cmd+K** — global `keydown` listener (widgets.js:1183-1188), confirmed unbound anywhere
  else in the codebase before binding (audit §3); opens/focuses the Command Center from
  anywhere via `V.openWidget('commandcenter')`.
- **Arrow-key roving focus across the domain grid or search results was NOT implemented.**
  Disclosing this explicitly per the task's honesty requirement: Tab-order navigation through
  the grid works, but there is no left/right/up/down grid-cell arrow navigation layered on top
  of it. This is a reasonable follow-up (see §14) but was not built in this pass.
- No keyboard traps: every view's interactive elements are reachable and leavable via Tab
  alone; the search input's own keydown handler only intercepts Escape (when there's a query)
  and otherwise lets Tab/Shift+Tab pass through untouched.

## 7. Recent / Pinned / Active Behavior

All three are session-local, in-memory only — no backend call, no `localStorage`, no
persistence across a page reload, exactly as required:

- **Active** — reads `Object.keys(live)` (widgets.js's own pre-existing open-widget tracking
  object), filtered to exclude `commandcenter` itself. Zero new tracking code.
- **Pinned** — a plain `Set` (`pinned`, widgets.js:1030) scoped to the `F.commandcenter` closure;
  toggled by the pin button per row/chip (widgets.js:1084-1088).
- **Recent** — a capped array (`recent`, cap 8) fed only by a real `V.on('widget:open', ...)`
  event listener (widgets.js:1170-1175), deduped (`[id].concat(recent.filter(x=>x!==id))`).
  The listener is registered *after* `shell()` builds the panel and is guarded with
  `if(!w.isConnected) return;` — matching the codebase's own existing convention for cleaning
  up interval callbacks on closed panels — so repeatedly closing and reopening the Command
  Center across a session does not accumulate duplicate listeners.

All three reset to empty on a full page reload; this is intentional per the task's own
requirement, not an oversight, and is stated here rather than left implicit.

## 8. Real Data Used

`domainSummary(domId)` (widgets.js:1007-1023) and the context strip `renderCtx()`
(widgets.js:1034-1045) read only already-loaded `VECTOR_DATA` (`D`) fields, populated by
`backend.js`'s existing polling — no new endpoint, no new poll interval:

- `D.agents` → CIVILIZATION domain summary ("N / M alive", using the same HP>0 alive check
  established in Task 74's Atlas — not re-derived, reused).
- `D.APPROVALS` → SECURITY domain summary and the context strip's `APPROVALS` chip.
- `D.GOALS` (LONG/MID/SHORT) → GOALS domain summary and the context strip's `GOAL` chip
  (first available goal title across the three horizons).
- `D.INFERENCE` → INFERENCE domain summary and the context strip's `MODEL` chip.
- `D.STOCKS_LIVE` → FINANCE domain summary ("N quotes live").
- `D.DECISIONS` → the context strip's `DECISION` chip (most recent decision's action/summary).

Every other domain (COGNITION, MEMORY, PLANNING, SENSING, COMMUNICATION, KNOWLEDGE, MEDIA,
SYSTEM, EXPERIMENT) has **no real aggregate source** and `domainSummary()` returns `null` for
them, rendered as `STATUS UNKNOWN` on the card — never a fabricated number. Same rule for the
context strip: any chip whose source value is missing renders literally `UNKNOWN`, per the
truthfulness convention established across Tasks 71-75.

## 9. Mock Data

None. Every value the Command Center displays is either (a) read live from `D.*`, (b) derived
from the `F`/`live` registries already maintained by widgets.js itself, or (c) `UNKNOWN` when
no real source exists. No placeholder numbers, no synthetic activity feed, no fabricated
domain health score.

## 10. Files Changed

| File | Change |
|---|---|
| `frontend/js/widgets.js` | Added `PANEL_META`, `panelLabel()`, `panelExists()`, `DOMAINS`, `domainPanels()`, `domainSummary()`, `F.commandcenter` (search/breadcrumb/context-strip/home-domain-search views, Active/Pinned/Recent), the global Ctrl/Cmd+K listener, `POS.commandcenter` entry, `PANEL_MATCHERS` entry for `commandcenter`. |
| `frontend/js/terminal.js` | Added `'commandcenter'` to the `WIDGETS` array. |
| `frontend/styles/widgets.css` | Added the `.cc*` rule block (panel body sizing, search, breadcrumb, context chips, section labels, chip rows, domain grid/cards, panel list rows, open/pin buttons, `:focus-visible` states, small-window degradation). |

## 11. Files Created

| File | Purpose |
|---|---|
| `VECTOR_TECHNICAL_KNOWLEDGE/75_COMMAND_CENTER_AUDIT.md` | Phase-1 read-only navigation/keyboard/data audit. |
| `VECTOR_TECHNICAL_KNOWLEDGE/75_COMMAND_CENTER.md` | This file. |

No panel, script, or style file was deleted or replaced — this is additive to the existing HUD,
per the task's explicit "evolve, don't rebuild" instruction.

## 12. Performance

- **Zero new network polling.** All data reads are synchronous property access on the already-
  polled `D` object; the Command Center adds no `setInterval`/`fetch` of its own.
- **Bounded memory.** `recent` is capped at 8 entries; `pinned` is a `Set` bounded by the number
  of panels that exist (≤ ~50); `live` is the pre-existing registry, not duplicated.
- **Render cost.** `render()` rebuilds only `body`'s innerHTML for the active view (home/domain/
  search) plus the small `ctx`/`crumb` strips — no virtual-DOM diffing, consistent with every
  other panel in this codebase, and cheap given the panel counts involved (≤6 panels per
  domain, ≤44 total across search).
- **Event listeners.** One `widget:open` listener per Command Center instance, guarded against
  firing after close (§7); one page-level `keydown` listener for Ctrl/Cmd+K, registered once at
  module load (not per-open), matching how the terminal's own `Ctrl+Shift+H` listener is wired.

## 13. Accessibility

Every interactive navigation control introduced by this task is a real `<button>` or `<input>`
element — the search box, every breadcrumb segment, every domain card, every panel-list open/pin
action, every Active/Pinned/Recent chip. This is a deliberate improvement over Task 74's Agent
Atlas, which the Task 75 prompt explicitly named as a pattern not to repeat: the Atlas's
macro→district→agent navigation used `<div onclick="...">` throughout (disclosed in
`74_AGENT_ATLAS_AUDIT.md`/`74_AGENT_ATLAS.md`), meaning none of its clickable surfaces were
keyboard-reachable beyond the panel shell itself. The Command Center's controls are all
natively Tab-reachable, natively activate on Enter/Space with no custom keydown re-implementation,
and carry explicit `aria-label`s on buttons whose visible text alone would be ambiguous (pin/unpin
state, "open <panel>"). `:focus-visible` styling was added in `widgets.css` for every new
interactive class, since the pre-existing panels in this codebase do not consistently provide a
visible focus ring — this is called out explicitly in the CSS's own comment rather than silently
copying that gap forward. The one disclosed gap is arrow-key roving focus within the domain grid
(§6) — Tab-order access works, dedicated grid arrow-navigation does not yet exist.

**Testing performed:** static syntax verification only (`node --check js/widgets.js`,
`node --check js/terminal.js` — both OK; CSS brace-balance checked programmatically, 509/509).
**Interactive browser verification was NOT performed** — the Chrome extension remains
unconnected in this session, consistent with Task 73/74's own disclosed limitation. No visual
or live-keyboard-navigation confirmation exists yet; this should be verified in a real browser
session before relying on the accessibility claims above as fully proven rather than
implementation-level-correct.

## 14. Future Improvements

- Arrow-key roving focus (Up/Down/Left/Right) across the domain-card grid and search-result
  list, per typical listbox/grid ARIA patterns — the one keyboard gap disclosed in §6.
- A `domainSummary()` entry for the remaining domains once a real backend aggregate exists for
  them (e.g., a MEMORY domain summary once `73_FRONTEND_DATA_CONTRACTS.md`'s proposed
  `SemanticMemoryStatusProvider` is real) — currently correctly `UNKNOWN`, not a bug.
- Fuzzy/ranked search (current match is a plain substring test with no ranking) if the panel
  count grows enough that exact-substring search becomes a limiting factor.
- Optional: surface the same domain taxonomy as a `district`/`domain` field directly on
  panel definitions themselves (rather than as a separate `DOMAINS` layer) if a future task
  needs it in more than one place — deliberately not done now, to avoid touching the existing
  flat registries per this task's own scope limits.

---

## Final Integrity Check

- `git rev-parse HEAD` → `5964a331678ac648c8289f4c38fd0e5430e1ee9d` — **unchanged** from the
  value recorded before this task began.
- `git diff --name-only -- '*.py' | wc -l` → **64** — **unchanged**. No Python file was
  modified at any point in this task.
- `git status --short frontend/` → exactly three modified files:
  `frontend/js/terminal.js`, `frontend/js/widgets.js`, `frontend/styles/widgets.css`.
- `git status --short VECTOR_TECHNICAL_KNOWLEDGE/` → the directory shows as untracked (`??`),
  containing this file and `75_COMMAND_CENTER_AUDIT.md` alongside the prior tasks' reports —
  consistent with that directory not being tracked in this repository at all (pre-existing
  state, not something this task changed).
- No experiment-related file, process, database, or watermark was read, polled, or touched at
  any point in this task — this task never opened a DB connection, never called any VECTOR API
  endpoint, and never inspected the running Segment-2 process. Isolation is total, same as
  Tasks 73 and 74.
