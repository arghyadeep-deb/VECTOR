# Task 76 — HUD Visual System Audit (Phase 1, read-only)

Frontend-only, read-only. No file was modified during this phase. Segment 2 (experiment)
was never touched, queried, or inspected — this audit reads only static `.html`/`.css`/`.js`
source files on disk.

---

## 1. Existing Structure (DOM order, `frontend/VECTOR.html`)

```
#stage
 ├─ #grid, #dust, #sweep, #scanlines      (Level 0 — background identity)
 ├─ #herocam, #hero-hud                   (vision mode overlay)
 ├─ #vignette
 ├─ #workspace                            (Level 2/3 — panel canvas, empty until populated)
 ├─ #orb-wrap → .orb                      (Level 0 — VECTOR identity)
 ├─ #globe, #clock, #hint                 (locked-screen state)
 ├─ .ticker.top / .ticker.bot             (Level 1 — stock/news tickers)
 ├─ #caption                              (Level 1 — spoken-text captions)
 ├─ #dock                                 (Level 1 — 6-button control dock)
 └─ #frame                                (Level 1 — HUD corner/edge chrome)
```

`#cmd-bar` (the persistent command input) is injected by `command-box.js` and appended
directly to `#stage`. This DOM order already matches the task's intended Level 0→1 hierarchy
reasonably well — background/orb underneath, chrome/controls on top — no structural
reordering is needed.

## 2. Design Tokens (`frontend/styles/core.css` `:root`)

A single, already-coherent token set exists and is used consistently:

```
--accent:#00CFFF  --accent-deep:#0a84ff  --accent-soft:#7fe6ff
--bg:#000000  --bg-2:#050608  --surface:#0b0d10  --surface-2:#111419
--line:rgba(0,207,255,.18)  --line-hot:rgba(0,207,255,.65)
--warn:#F59E0B  --danger:#EF4444  --ok:#10B981
--txt:#E2E8F0  --txt-mute:rgba(226,232,240,.5)  --txt-faint:rgba(226,232,240,.28)
--mono:'JetBrains Mono','Space Mono',ui-monospace,monospace
--font:'Chakra Petch','JetBrains Mono',monospace
--orb-size:300px  --frame-pad:18px
```

Tasks 73–75 all reused this exact set — verified by grepping every new CSS block added in
those tasks for raw hex/rgb literals outside `var(--…)`; none were found except the
pre-existing, sanctioned status colors (`--ok`/`--warn`/`--danger`) applied via the same
variables. **No second token system exists. None should be introduced.**

## 3. Central Orb — State Vocabulary (already truthful)

`vector-core.js`'s finite state machine (`STATES`, line 25):

```
boot · locked · idle · listening · processing · speaking · fortress
```

Each transition sets a real sub-label via `api.orb.setSub(...)`: `STANDBY`, `ONLINE`,
`LISTENING`, `PROCESSING`, `SPEAKING`. **No "THINKING" or invented cognitive label exists
anywhere in the orb's own code.** `core.css` styles each state distinctly (`#stage.idle`
breathing animation, `#stage.processing` faster ring spin + bloom, `#stage.speaking` ripple
pulses, `#stage.locked`/`#stage.boot` hide the mechanical ring and show only the plasma
core). This is already exactly the restrained, truthful state design Task 76 asks for —
**no change needed to the orb itself.**

One real inconsistency **was** found in orbit of this area — not in the orb's own code, but
in the command bar's toast text: see §7 finding F1.

## 4. Panel Shell (`frontend/js/widgets.js` `shell()`, `frontend/styles/widgets.css` `.widget`)

Every panel — old and new — shares one shell: `.widget` (gradient background, `--line`
border, blur backdrop, materialize sweep animation), `.w-head` (drag handle, `.dotled` status
dot, `.w-title` at 11px/`.22em`/uppercase/accent-soft, real `<button class="w-x">` close),
`.w-body` (10px padding), `.w-corner` tick decorations. `shell()` also sets `role="dialog"`,
`aria-label`, and a scoped Escape handler. **All five Task 73–75 panels use this shell
correctly, unmodified** — the inconsistency that exists is entirely in the panel-specific
CSS layered inside `.w-body`, not in the shared shell.

## 5. Findings — Visual/Structural Inconsistency Across Tasks 73–75 Panels

### F1 — "thinking…" toast contradicts the orb's own truthful state language
`frontend/js/command-box.js:70` shows `showToast('thinking…', true)` while a command is in
flight. The orb itself never uses this word (§3) — it uses `PROCESSING`. Task 76 explicitly
states: *"Do NOT claim THINKING merely because an animation is running... Use existing
truthful state labels."* The command bar is a first-class Level 1 HUD control and its wording
should match the orb's own vocabulary, not introduce a second, cognitively-loaded term.
**Fix candidate:** change the toast text to `'processing…'` (§ Phase 2).

### F2 — Duplicated breadcrumb CSS between Agent Atlas and Command Center
`.atlas-crumb`/`.atlas-cr`/`.atlas-cr.cur`/`.atlas-sep` (widgets.css:1136-1140) and
`.cc-crumb`/`.cc-cr`/`.cc-cr.cur` (widgets.css:1200-1203) define **near-identical rules**
(9px, `.08em` letter-spacing, `--txt-mute`, hover → `--accent-soft`, `.cur` → `--accent-soft`
+ `cursor:default`) under two separate class prefixes. This is the clearest sign these two
panels are not yet visually "one system" — they independently reinvented the same breadcrumb
component. Additionally, Agent Atlas's breadcrumb is built from `<span class="atlas-cr">`
with a manual click listener (widgets.js:790-797) — not a real `<button>` — while Command
Center's is a real `<button>` (Task 75's own stricter accessibility bar). This is Task 74's
already-disclosed `<div>/<span> onclick` gap, concretely visible in the one place these two
panels sit side by side conceptually. **Fix candidate:** merge the CSS into shared selectors
and convert Atlas's breadcrumb to real `<button>` elements — a small, self-contained change
(§ Phase 2), not a rewrite of the Atlas's card/row grid.

### F3 — Three different "section label" idioms across five panels
- Memory Explorer / Cognition / Experiment Observatory share `.memx-hint,.cog-hint,.xobs-hint`
  — an *intro* hint styled with a dashed **bottom** border (before the content it introduces).
- Agent Atlas's `.atlas-sep-lbl` — a *section* divider styled with a dashed **top** border
  (after the content above it).
- Command Center's `.cc-sec-lbl` — visually the same role as `.atlas-sep-lbl` (ACTIVE /
  PINNED / RECENT / DOMAINS headers) but has **no border at all**, only a top margin.

Three panels solve the same "here's a new subsection" problem three different ways. The
hint-vs-separator distinction (F3a vs F3b/F3c) is legitimate — an intro hint and a section
divider are different roles — but `.atlas-sep-lbl` and `.cc-sec-lbl` are the *same* role
(section divider) with inconsistent treatment. **Fix candidate:** give `.cc-sec-lbl` the same
dashed-top-border treatment `.atlas-sep-lbl` already uses (§ Phase 2).

### F4 — Mobile/narrow-window overflow bug across all five Task 73-75 panels
`frontend/styles/widgets.css`'s pre-existing mobile rule (line 510, `@media(max-width:640px)`)
caps every `.widget`'s outer container to `width:min(calc(100vw - 48px), 400px)`, relying on
`.w-body` defaulting to `width:auto` (100% of its parent) — this is how every pre-Task-73
panel already degrades correctly on narrow screens.

Tasks 73–75 broke that convention: `.memx-panel .w-body{width:380px}`,
`.cog-panel .w-body{width:340px}`, `.xobs-panel .w-body{width:340px}`,
`.atlas-panel .w-body{width:420px}`, and `.cc-panel .w-body{width:460px}` are all
**unconditional, fixed pixel widths** that apply at *every* viewport size, not just desktop.
On a narrow viewport these widths exceed the outer `.widget` container's own mobile-clamped
width, and since `.widget{overflow:hidden}` (widgets.css:58), the excess content is **clipped**,
not scrolled. Command Center's own Task-75 attempt at a fix
(`.cc-panel .w-body{width:calc(100vw - 28px)}` inside its own `@media(max-width:640px)` block)
is *itself* still wider than the outer `.widget`'s `calc(100vw - 48px)` clamp by 20px on the
same viewport — the fix didn't fully solve its own problem. Agent Atlas's 2-column
`.atlas-grid` also never collapses to one column on narrow screens, unlike Command Center's
own `.cc-grid` (which does) and the pre-existing `.mc-grid` (Mission Control, which also
does). **Fix candidate:** collapse all five panels' `.w-body` to `width:100%` and
`.atlas-grid` to one column under the existing mobile media query (§ Phase 2) — this is a
real, demonstrable bug, not a stylistic preference.

### F5 — Command Center's dock entry point is a dead end
The dock's `PANELS` button (`hud-controls.js:79`) calls `V.toggleWorkspace()`, which — per
Task 75's own audit (`75_COMMAND_CENTER_AUDIT.md` §1) — reveals an **empty canvas** with
nothing open in it when clicked from a state with zero live widgets. This is the exact gap
the Command Center was built to close, but the dock was never wired to it: a user who has
never used the command bar, Ctrl+K, or the terminal has no way to discover the Command Center
from the dock at all. This is the single largest remaining "does this feel like one coherent
system" gap. **Fix candidate:** when `PANELS` is pressed with zero currently-open widgets,
open the Command Center instead of an empty workspace; when panels are already open, preserve
the existing toggle-visibility behavior exactly as-is (§ Phase 2) — no new dock button, no
functional change to the terminal/command-bar/Ctrl+K paths.

## 6. What Is Already Correct (no change needed)

- Orb state vocabulary (§3) — fully truthful, restrained, already matches Task 76's own
  "Central Orb" section almost verbatim.
- Design tokens (§2) — single source, fully reused by every new panel, no drift.
- Panel shell (`shell()`/`.widget`/`.w-head`/`.w-title`/`.w-x`) — identical across all ~50
  panels including all five new ones.
- Status-color language — `.badge2.proceed/defer/reject` (ok/warn/danger),
  `.ve-source[data-mode="live"/"simulated"]` (ok/warn), `cog-chip` state colors
  (active/recent→ok, waiting→warn, blocked/failed→danger) all consistently reuse the same
  three semantic colors for the same three semantic meanings project-wide.
- `.ve-offline` — already the one shared "no data / offline" idiom, reused by Command Center,
  Agent Atlas, and every pre-existing panel that has an empty state.
- The lean 6-button dock (`hud-controls.js`) — already uses real `<button>`s with
  `aria-label`s; Task 76 explicitly says not to grow it, and it doesn't need to.
- Command Center's own accessibility work (real buttons, `:focus-visible`, Tab order,
  scoped Escape) — nothing here regresses any of it.
- Grid background, scanlines, frame chrome, tickers, boot sequence — untouched by Tasks
  73–75 and not visually inconsistent with anything; no findings here.

## 7. Scope Decision for Phase 2

Given the findings above, Phase 2 makes exactly five small, targeted changes — no new
subsystem, no rewritten panel, no new backend:

1. F1 — `command-box.js`: `'thinking…'` → `'processing…'`.
2. F2 — `widgets.js` + `widgets.css`: Agent Atlas breadcrumb → real `<button>`s; merge
   duplicate breadcrumb CSS into shared selectors.
3. F3 — `widgets.css`: give `.cc-sec-lbl` the same dashed-top-border treatment as
   `.atlas-sep-lbl`.
4. F4 — `widgets.css`: fix the five panels' mobile `.w-body` overflow, collapse
   `.atlas-grid` to one column under 640px.
5. F5 — `hud-controls.js`: dock's `PANELS` button opens the Command Center instead of an
   empty workspace, only when zero widgets are currently open.

Everything else audited above is already correct and is intentionally left untouched, per
the task's own "evolve, don't rebuild" instruction and "prefer the smallest number of files
and smallest changes necessary" rule.
