# Task 75 — Command Center: Phase 1 Navigation Audit

Read-only frontend source audit (no backend touched — this task is frontend-only end to end).

## 1. How a User Currently Reaches Any of the ~50 Panels

Three independent, already-working mechanisms, confirmed by direct source read:

1. **Command bar / voice** — `PANEL_MATCHERS` (`widgets.js`, ~30 regex→id entries) is scanned by
   `localReply()` whenever the text contains an open-intent word (`requestedOpen()`: "open, show,
   bring up, pull up, launch, summon, display"). First regex match wins; calls `V.openWidget(id)`.
2. **Terminal** (`Ctrl+Shift+H`) — `terminal.js`'s `WIDGETS` array (a flat id list, currently ~44
   entries after Tasks 73-74) is printed by the `ls`/`panels` command. Typing a bare id opens it
   (traced in Task 73's audit).
3. **Dock → PANELS button** — `hud-controls.js`'s lean 6-button dock; `PANELS` calls
   `V.toggleWorkspace()` only (show/hide the `#workspace` canvas), it does **not** open any specific
   panel or provide a picker. Once the workspace is visible, the user still needs mechanism 1 or 2 to
   actually open something into it. **This is the exact gap Task 75 is closing** — there is currently
   no visual browsing path from "workspace is open" to "a specific panel is open."

## 2. Panel Open/Close Mechanics (confirmed, re-traced from Task 73's own reading of `widgets.js`)

- `openWidget(id, opts)` (`widgets.js:1598-1615`): if already open, flashes it; else calls the
  factory `F[id](opts)`, positions it from `POS[id]` (or `opts.pos`, or `[30,30]`), appends to
  `#workspace`, tracks it in a module-local `live` object (`id → element`), fires `widget:lock` then
  adds `.show` after a short delay. **`F` and `live` are both in the same closure this task's new
  code will run in** — a Command Center panel can read `live`'s current keys directly for a genuinely
  real "currently open panels" list, with zero new tracking code.
- `closeWidget(id)` (`widgets.js:1616-1620`): fades out, removes from DOM, deletes from `live`,
  restores focus to whatever had it before the panel opened (`_returnFocus`).
- `V.openWidget` (`vector-core.js:104`) wraps this: calls `wakeIfNeeded()`, auto-opens the workspace
  if closed, then delegates. So opening any panel — including a future `commandcenter` — always
  brings the workspace up first, satisfying the task's "opened through the existing PANELS mechanism"
  requirement automatically, without new code.
- `shell(id, title, bodyEl, extraClass)` (`widgets.js:40-56`) already sets `role="dialog"`,
  `aria-label`, `tabindex="-1"`, and its own `Escape` handler that calls `e.stopPropagation()` before
  `V.closeWidget(id)` — meaning **Escape inside any shell-built panel already closes only that panel**,
  never bubbling up to the separate, pre-existing global Escape handler in `demo.js` (`hotkeys()`,
  line 220-227) that closes the whole workspace or locks VECTOR. This distinction matters directly
  for Task 75's own accessibility requirements (§6 below) — the Command Center inherits correct Escape
  scoping for free by using `shell()`, and must not add a second, competing Escape handler.

## 3. Existing Keyboard Shortcuts (full inventory — traced to avoid any collision)

| Shortcut | Handler | File |
|---|---|---|
| `Ctrl+Shift+H` | Toggle terminal | `terminal.js:163` |
| `` ` `` (backtick) | Toggle dev "director" panel | `demo.js:222` |
| `Ctrl+Shift+V` | Toggle workspace | `demo.js:223` |
| `Space` (when not focused in an input/textarea) | Toggle voice listen state | `demo.js:224` |
| `Escape` (global) | Close workspace if open, else lock VECTOR | `demo.js:225` |
| `Escape` (inside any `shell()`-built panel) | Close that one panel only, `stopPropagation()` | `widgets.js:51-53` |
| `Enter` (lock screen only) | Wake VECTOR | `VECTOR.html:203-205` |

**`Ctrl+K` / `Cmd+K` are confirmed unused anywhere in the codebase** (checked via a repo-wide grep for
`ctrlKey`/`metaKey` — the table above is the complete list of what currently exists). Safe to bind for
a command palette, per the task's own "trace before intercepting" requirement.

## 4. `VECTOR_DATA` (`D`) — What's Already Loaded, Reusable Without a New Fetch

Confirmed live-populated fields (from Task 73's audit of `backend.js`'s poll handlers, re-verified
still accurate): `D.agents` (health/district/tier), `D.GOALS` (LONG/MID/SHORT), `D.MEMORY`,
`D.APPROVALS`, `D.COUNCIL`, `D.DECISIONS`, `D.PERSONS`, `D.INFERENCE`, `D.STOCKS_LIVE`, plus ~16
background-only fields (`D.TASKS`, `D.CHANNELS`, `D.JOBS`, `D.AUDIT`, `D.PEERS`, `D.METERING`,
`D.SANDBOX`, `D.MCP`, `D.RESEARCH`, `D.EMAIL`, `D.PROVIDERS`, `D.TOOLS`, `D.MINING`, `D.MIGRATION`,
`D.OAUTH`). The Command Center's domain summary chips (§ design) read from these directly — no new
polling is introduced anywhere in this task.

## 5. No Existing Panel Categorization

No `category`/`domain`/`group` field exists on any panel definition anywhere in the codebase — `F`
(the factory map), `POS` (positions), `PANEL_MATCHERS` (routing), and `WIDGETS` (terminal listing)
are each a flat, uncategorized structure. **Domain taxonomy is genuinely new frontend-only metadata**,
built this task, layered on top of these without modifying any of them.

## 6. Accessibility Baseline (why this task is stricter than Task 74)

Every existing rich panel factory (`F.goals`, `F.districts`, `F.council`, `F.security`, `F.memory`,
and Task 73's three additions) renders its interactive elements as plain `<div>`s with `click`
listeners — **not** keyboard-accessible beyond the panel shell itself. Task 74's Agent Atlas followed
this same pre-existing (if imperfect) convention and disclosed the gap explicitly. Task 75's own
instructions are stricter and explicit: new interactive navigation controls in the Command Center
must be real `<button>`/`<a>` elements. This task's implementation follows that stricter bar for
everything it adds, without retrofitting the pre-existing panels (out of scope, per "do not modify
existing panels unnecessarily").
