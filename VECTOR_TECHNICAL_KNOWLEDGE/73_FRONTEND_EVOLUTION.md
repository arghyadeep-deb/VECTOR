# Task 73 — VECTOR Frontend / JARVIS HUD Evolution

Frontend-only work. **Segment 2 was not interacted with.** No `.py` file was touched (git diff on
`*.py` is 64 files before and after — the same pre-existing set from every prior task in this
series). Only three files were modified, all under `frontend/`; no backend endpoint was added,
removed, or changed. See §14 for the full disclosure.

---

## 1. Existing Frontend Architecture (Phase 1 findings)

**Framework: none — vanilla HTML/CSS/JS.** No React, Vue, Next.js, or build-time framework. Fonts
and three.js/MediaPipe are vendored locally (`frontend/vendor/`) for an offline-first design —
confirmed via `VECTOR.html`'s own inline comments ("offline-first, no Google leak").

- **Entry points:** `frontend/VECTOR.html` (dev — loads 27 individual `<script src="js/...">` tags
  in a specific dependency order) and `frontend/VECTOR.prod.html` (production — loads exactly two
  scripts: `js/config.js`, `js/webauthn.js`, then a **single pre-built bundle**
  `dist/vector-hud.prod.js`). `frontend/login.html` is a separate auth entry point, not touched
  this task.
- **Routing:** none in the SPA-framework sense — a single-page HUD with widget panels opened/closed
  by ID (`V.openWidget(id)` / `V.closeWidget(id)`), not URL-routed pages.
- **Served by:** `core/api/app.py` at `/hud/` and `/hud/{filepath}` (auth-gated), which selects
  between `VECTOR.prod.html` and `VECTOR.html` based on `_is_production_env()`. **This task's HUD
  process (PID 36996, started plainly via `python run_vector.py api`, no `VECTOR_ENV=production` set)
  is, with high confidence, serving the dev entry point (`VECTOR.html`)** — meaning the changes made
  this task are live immediately, without a rebuild. Not independently re-verified by probing the
  running process (avoided per the task's own caution about not interacting with anything tied to
  the experiment host); stated as an inference, not a confirmed fact — see §17 open items.
- **Build system:** `tools/build_frontend.py` (referenced in a `terminal.js` comment — "not part of
  the lean [prod] bundle") produces `dist/vector-hud.prod.js` from the individual `js/*.js` files.
  **Not run this task** — the three files changed are the *source* files; a production deployment
  would need this build re-run to pick up the new panels (documented, not performed).
- **Package manager:** none observed (no `package.json` found under `frontend/`) — this is a
  hand-vendored, buildless-by-default frontend; `tools/build_frontend.py` is a bespoke bundler, not
  an npm/webpack pipeline.
- **Components:** a single large IIFE-per-file module pattern. Each `js/*.js` file attaches to
  `window` (`window.VECTOR`, `window.VECTOR_DATA`, `window.VectorOrb`, `window.VectorCity`, etc.).
  Widgets are built by **factory functions** (`js/widgets.js`'s `F.<id> = function(){ ...; return
  shell(id, title, bodyEl, extraClass); }`) — confirmed by direct read of `F.goals`, `F.districts`,
  `F.council`, `F.security`, `F.memory`, and now this task's three additions.
- **Styling system:** two hand-written CSS files, no preprocessor — `styles/core.css` (388 lines —
  the HUD chrome: grid backdrop, orb, frame, tickers, boot sequence, CSS custom-property design
  tokens) and `styles/widgets.css` (1083 lines before this task, 1122 after — every widget panel's
  own styling, using the tokens defined in `core.css`).
- **State management:** a hand-rolled event bus on `window.VECTOR` (`V.on(event, handler)` /
  `V.emit(event, payload)`), plus a single shared mutable data object `window.VECTOR_DATA` (`D`) that
  polling and WS handlers write into and widget-refresh functions read from. No Redux/MobX/signals
  library.
- **API layer:** `V.http(path, opts)` (defined in `js/vector-core.js`, not read in full this task —
  used as-is) with a fallback pattern in `js/widgets.js` (`apiGet`/`apiPost`) that uses `V.http` when
  available and falls back to a raw `fetch()` otherwise.
- **WebSocket:** `V.on('status', ...)`, `V.on('state_event', ...)`, `V.on('decision_made', ...)`,
  `V.on('hypothesis_surfaced', ...)` — confirmed live handlers in `js/backend.js`, fed by a `/ws`
  connection managed in `vector-core.js` (not modified, not re-read in full this task).
- **Polling:** `js/backend.js`'s `startPolling()` — **confirmed 16 actively-refreshing named polls**
  (`/status` 5s, `/world/snapshot` 5s, `/agents` 8s, `/memory/recent` 6s, `/brain/goals` 10s,
  `/brain/reasoning/chains` 15s, `/brain/persons` 30s, `/security/status` 12s, `/gateway/pending` 5s,
  `/memory/council/history` 20s, `/sensing/status` 15s, `/loop/status` 8s, `/inference/stats` 12s,
  `/finance/ticker` 30s, `/notifications/hypotheses` 25s, `/nudge/latest` 25s) **plus 16 further
  background-only polls** feeding `D.*` for future widgets (`/tasks/`, `/channels/status`,
  `/scheduler/jobs`, `/audit/recent`, `/network/peers`, `/metering/status`, `/sandbox/status`,
  `/mcp/status`, `/research/status`, `/email/recent`, `/providers/routes`, `/tools/registry`,
  `/mining/status`, `/migration/sources`, `/oauth/integrations`). This is a genuinely large,
  already-built real-data surface — not something this task needed to invent.
- **Existing HUD screens/panels (confirmed by direct source read, not assumed):** a rich, populated
  live set — `chat`, `music`, `map`, `webcam`, `telemetry`, `market`, `goals`, `goalplanner`,
  `districts`, `council`, `security`, `memory`, `approvals`, `finance`, `contentscheduler`,
  `answerengine`, `voicestudio`, `codegraph`, `city3d` — **plus roughly 30 more "capability card"
  panels** (`brainpanel`, `corepanel`, `agentspanel`, `knowledgepanel`, `trading`, `intelligencepanel`,
  `mediastudio`, `healthpanel`, `learningpanel`, `platformpanel`, and others) that render a
  summary/health/endpoint-list card rather than a fully live dashboard — a distinct, lighter-weight
  pattern from the rich panels above. Task 73's new panels (§4) follow the **rich, live pattern**,
  not the capability-card pattern, since they need genuine per-subsystem visual distinctions the
  card pattern doesn't support.
- **Existing visual effects:** a central "orb" (`js/orb.js`, 194 lines — the cognitive core), a
  face-recognition "auth scan" overlay wired to a live `<video id="herocam">` feed, MediaPipe
  hand-gesture tracking (`js/gestures.js`) and face detection (`js/face.js`), a boot sequence with a
  scripted log, animated news/stock tickers, a scanline/vignette/dust-canvas backdrop, and a draggable
  widget system with a "targeting scan-lock" open animation (`openWidget()`'s
  `requestAnimationFrame` + `widget:lock` event).
- **Responsive behavior:** one `@media (max-width: 640px)` block found in `widgets.css`, collapsing
  several multi-column grids to `1fr` — narrow, targeted mobile handling, not a full responsive
  system. Primary target is clearly a large desktop viewport (consistent with Task 73's own stated
  priority).
- **Tests:** none found under `frontend/` (no `*.test.js`, no test runner config). Frontend
  correctness has historically relied on manual/visual verification, per the repository's own
  conventions elsewhere.

## 2. Existing Visual System (Phase 2 forensics)

No reference screenshot was attached to this task's context — Phase 2's analysis below is derived
entirely from reading `VECTOR.html`, `core.css`'s token definitions, and the widget CSS patterns
already cataloged in `widgets.css`, not from a supplied image. This is disclosed explicitly rather
than silently assumed.

**Design tokens confirmed in `core.css`:** `--accent:#00CFFF` (cyan), `--accent-deep:#0a84ff`,
`--accent-soft:#7fe6ff`, `--warn:#F59E0B`, `--danger:#EF4444`, `--ok:#10B981`,
`--txt-mute:rgba(226,232,240,.5)`, `--txt-faint:rgba(226,232,240,.28)` — a small, disciplined palette,
already exactly matching Task 73's own stated "dark technical environment, cyan/blue accents,
restrained glow" brief. **This confirms the brief is describing the actual, already-built system, not
an aspiration** — the central task here is genuinely evolution, not a stylistic departure.

**What already looks excellent / should remain unchanged (assessed from source):** the orb as the
literal visual and DOM anchor of the page (`#orb-wrap`, built once at boot, never rebuilt), the
restrained, small (8-11px) uppercase-letter-spaced label typography used consistently across every
existing panel (`.row-kv .k`, `.mevt .et`, `.badge2`), the dashed hairline dividers
(`rgba(0,207,255,.1)`) instead of solid borders, and the "targeting scan-lock" widget-open animation.
**None of these were touched this task.**

**What lacked information hierarchy (the gap this task's panels address):** the existing `memory`
panel (`refreshMemory()`/`F.memory`) renders every memory event — episodic, reasoning, hypothesis,
nudge — into one undifferentiated scrolling list with an `importance` heuristic
(`inferImportance()`'s regex on `event_type`) as the only structure. There was no panel anywhere in
the existing system that separated VECTOR's distinct memory *subsystems* (policy, counterfactual,
epistemic, reasoning-bank, semantic) from each other, and none that distinguished "this subsystem
stores data" from "this subsystem's stored data has been shown to influence a decision" — exactly the
distinction this session's own Task 71/72 audits established as critical and frequently conflated.
**This was the single clearest, most load-bearing gap found in Phase 2**, and is what Memory Explorer
(§4) exists to close.

**What was decorative with little functional value, left untouched (out of respect for "preserve
working functionality"):** the tickers, boot sequence, and ambient visual effects were not assessed
as "low value" — they establish tone and were explicitly protected by the task's own "do not destroy
the existing UI" instruction. No judgment is offered on removing any of them.

## 3. Existing HUD Architecture Map

```
VECTOR.html (dev) ──┬── styles/core.css   (chrome, orb, tickers, boot, design tokens)
                     ├── styles/widgets.css (all panel styling)
                     └── js/*.js (27 files, load order matters):
                            config.js → webauthn.js → data.js → orb.js → ambient.js
                            → vector-core.js (event bus, V.http, WS) → voice_stream.js
                            → audio.js → voice_duplex.js → approvals.js → ventures.js
                            → widgets.js (panel factories + POS + PANEL_MATCHERS)
                            → gestures.js → face.js → speech.js → cinematic.js
                            → terminal.js (Ctrl+Shift+H command console + WIDGETS list)
                            → canvas-pan.js → command-box.js → hud-controls.js (dock)
                            → provider-keys.js → demo.js (legacy dock builder) → city3d.js
                            → backend.js (polling + WS→DOM wiring — loaded LAST)

VECTOR.prod.html ──── dist/vector-hud.prod.js (pre-built bundle of the above,
                       via tools/build_frontend.py — NOT regenerated this task)
```

**Panel reachability (confirmed, not assumed):** the visible dock (`hud-controls.js`, 6 buttons:
VOICE/CHAT/GOALS/APPROVALS/PANELS/SOUND) is deliberately "lean" per its own comment — `PANELS` only
calls `V.toggleWorkspace()` (show/hide the panel canvas), not a picker. The *actual* mechanism for
opening any of the ~50 other panels is the **command bar / voice input**, routed through
`PANEL_MATCHERS` (a regex-to-widget-id table in `widgets.js`) and the **terminal** (Ctrl+Shift+H,
`ls`/`panels` lists every entry in `terminal.js`'s `WIDGETS` array). This task's three new panels
were wired into both mechanisms (§4), matching the existing extensibility pattern exactly rather than
adding new dock buttons — the dock's own "lean" design intent was treated as something to preserve,
not override.

## 4. What Was Added (implementation)

Three new rich, live panels, following the exact `F.<id> = function(){...}` / `shell()` pattern
already used by `F.goals`/`F.districts`/`F.security`/`F.memory`:

### 4.1 Memory Explorer (`memoryexplorer`)
Directly implements Task 73's own required STORED/RETRIEVED/INFLUENCING/LEARNING/ADAPTING
distinction, per subsystem: EPISODIC, SEMANTIC, POLICY, COUNTERFACTUAL, REASONING, EPISTEMIC, SKILL.
**Design discipline, stated explicitly in the panel's own UI copy:** STORED/RETRIEVED are live where
a real endpoint exists (episodic via `/memory/recent`, reasoning via `/brain/reasoning/chains`,
epistemic via `/brain/epistemic/summary`); INFLUENCING/LEARNING/ADAPTING are rendered as a **static,
clearly-labeled architecture assessment sourced from the Task 71/72 source-code audits**, never
inferred from a live row count. Semantic, Policy, Counterfactual, and Skill show "NO LIVE SOURCE" for
their stored/retrieved columns, honestly, rather than a fabricated number. This is the panel's whole
point: it is *impossible* for this specific panel to accidentally claim "learning" merely because a
database row changed, because the two kinds of evidence are visually and structurally separated.

### 4.2 Cognition Panel (`cognition`)
Renders the 11-stage pipeline order (OBSERVATION → CONTEXT → MEMORY → GOALS → CANDIDATES → SCORING
→ DECISION → PERMISSION → ACTION → OUTCOME → LEARNING) as a vertical rail of chips. Every chip
defaults to `UNKNOWN` and only changes state when a real backend call supports it: GOALS turns
`active` from a real `/brain/goals` count; DECISION turns `recent` and shows the real latest decision
+ score from `/brain/reasoning/chains`; PERMISSION turns `waiting`/`idle` from the real
`/gateway/pending` count. The other seven stages (OBSERVATION, CONTEXT, MEMORY, CANDIDATES, SCORING,
ACTION, OUTCOME, LEARNING) have **no dedicated per-stage backend signal today** and are left at
`UNKNOWN` deliberately — see §10 for the exact future endpoints that would be needed to light them up
truthfully.

### 4.3 Experiment Observatory (`experiment`)
**Strictly read-only** — never issues a POST/PUT/DELETE of any kind (confirmed by direct code
inspection: only `apiGet` calls appear in this factory). Shows uptime (`/status`), loop ticks
(`/loop/status`), a best-effort inference-call count (`/inference/stats`), and a best-effort
gateway-event count for the current audit window (`/security/status`'s `audit_log` length) — all real,
already-polled-elsewhere endpoints. Explicitly keeps **"TELEMETRY-LABELLED AUTONOMOUS"** and
**"BEHAVIORALLY-INFERRED UNATTENDED"** as two separate rows, both currently reading "requires backend
aggregation — not yet exposed" rather than a fabricated number — this is the direct implementation of
the task's own instruction not to conflate these two, which Tasks 65-66 already demonstrated are not
the same thing for VECTOR specifically.

### 4.4 Wiring (minimal, additive, matching existing conventions)
- `POS` (layout position table, `widgets.js`): three new entries.
- `PANEL_MATCHERS` (command/voice routing, `widgets.js`): three new regex entries, placed before the
  existing broad `memory` matcher so more specific phrases ("memory levels", "cognition",
  "experiment observatory") are not swallowed by it.
- `WIDGETS` (terminal `ls`/`panels` listing, `terminal.js`): three new entries.
- `styles/widgets.css`: one new block (~45 lines) reusing existing tokens exclusively — no new colors,
  no new font sizes outside the established 8-11px range, no new animation.

## 5. What Was Preserved

Everything not listed in §4. No existing widget factory, dock button, poll, WS handler, CSS rule, or
HTML structure was modified, removed, or renamed. The central orb, the auth-scan overlay, the boot
sequence, the tickers, the existing ~50 panels, the dock's lean 6-button design, and the command-bar/
terminal discovery mechanism are all untouched. `VECTOR.prod.html`'s bundle was not regenerated — the
production HUD's current behavior is unchanged by this task until that build step is run (§10).

## 6. What Was Improved

Nothing in the *existing* panels was altered — per the task's own priority ordering (preserve first),
and given the scope of new panel work already required, no existing-panel refinement was attempted
this task. This is disclosed as a scope choice, not an oversight: Phase 2 found the existing visual
system already coherent and internally consistent (§2), so the highest-value use of this task's
effort was new, correctly-scoped panels rather than polish passes on working code.

## 7. What Was Newly Implemented

See §4. Three panels, ~230 lines of new JS, ~45 lines of new CSS, 3 wiring edits (2 in `widgets.js`,
1 in `terminal.js`).

## 8. Exact Files Changed

- `frontend/js/widgets.js` — added `MEMORY_SUBSYSTEMS`, `F.memoryexplorer`, `COGNITION_STAGES`,
  `F.cognition`, `F.experiment`; added 3 entries to `POS`; added 3 entries to `PANEL_MATCHERS`.
- `frontend/js/terminal.js` — added `memoryexplorer`, `cognition`, `experiment` to the `WIDGETS`
  array (the `ls`/`panels` terminal command's listing).
- `frontend/styles/widgets.css` — appended one new CSS block for the three panels' own classes.

**No other file was modified.** No `.html` file was touched. No `.py` file was touched. No file
outside `frontend/` was touched.

## 9. Exact Files Created

None — this task modified existing frontend files rather than creating new ones (the widget-factory
pattern keeps every panel in the shared `widgets.js`, matching the existing codebase's own
organization; splitting the three new panels into separate files would have been a structural change
beyond this task's "evolve, don't restructure" mandate).

Documentation created: `VECTOR_TECHNICAL_KNOWLEDGE/73_FRONTEND_EVOLUTION.md` (this file) and
`VECTOR_TECHNICAL_KNOWLEDGE/73_FRONTEND_DATA_CONTRACTS.md`.

## 10. Real Backend Integrations (used, not created)

`/memory/recent`, `/brain/reasoning/chains`, `/brain/epistemic/summary`, `/brain/goals`,
`/gateway/pending`, `/status`, `/loop/status`, `/inference/stats`, `/security/status` — all
**pre-existing, already-integrated-elsewhere** endpoints, confirmed via direct source read of
`backend.js`'s own poll list and other panels' own `apiGet` calls before this task reused them. **No
new backend endpoint was created, and none of these calls were modified from their existing,
already-working shape** — the new panels are new *consumers* of existing data, not new producers.

## 11. Mock/Demo Integrations

**None introduced.** Every data point in the three new panels either (a) comes from a real,
pre-existing endpoint (§10), rendered honestly with a "—"/"offline" fallback on failure (matching
every existing panel's own `.catch()` pattern), or (b) is explicitly labeled in the UI itself as
having no live source (`"NO LIVE SOURCE"`, `"UNKNOWN"`, `"requires backend aggregation — not yet
exposed"`) — never a fabricated number standing in for a missing one. This satisfies the task's own
explicit instruction: "If a backend endpoint doesn't exist: DO NOT invent it and pretend it exists."

## 12. Required Future Backend APIs (deferred until after Segment 2)

See `73_FRONTEND_DATA_CONTRACTS.md` for the full typed-interface treatment. Summary list:
- Per-subsystem memory endpoints for Semantic, Policy, Counterfactual, and Skill memory (Memory
  Explorer currently shows "NO LIVE SOURCE" for all four).
- Per-stage cognition signals for Observation, Context, Memory(-retrieval-event), Candidates,
  Scoring, Action, Outcome, and Learning (7 of the Cognition Panel's 11 stages have no live signal
  today).
- A dedicated experiment-segment aggregation endpoint (segment ID, start time, cycle count, gateway
  deltas, action-repertoire diversity, candidate diversity, policy/epistemic change summary,
  telemetry-labeled-vs-behaviorally-inferred autonomy split) — the Experiment Observatory's biggest
  gap.

**None of these were implemented, stubbed with fake data, or partially faked this task** — per the
task's explicit "no backend runtime changes" rule, and because Segment 2 is running on the exact
backend process family these endpoints would need to live in.

## 13. Performance Considerations

- All three new panels reuse the existing `apiGet`/`shell()` machinery — no new polling *mechanism*
  was introduced, only additional calls to already-hit-elsewhere endpoints (e.g. `/brain/goals` is
  already polled every 10s by `backend.js`; Cognition Panel's own 12s interval is a second,
  independent call to the same endpoint while open — a minor, bounded duplication, not a new load
  pattern, and only occurs while that specific panel is open).
- Every new panel's refresh interval (`memoryexplorer`: on-open only, no interval; `cognition`: 12s;
  `experiment`: 15s) is in the same range as existing panels (8-30s) — no faster/more aggressive
  polling was introduced.
- No new animation loop, canvas, or WebGL context was added — the three panels are plain DOM/CSS,
  consistent with the existing `goals`/`security`/`memory` panels' own footprint, not the heavier
  `city3d`/`webcam` panels.
- No unbounded data structure was introduced — Memory Explorer's per-subsystem "count" is a single
  number per poll, not a growing list; Cognition Panel keeps only the single most recent decision;
  Experiment Observatory keeps only the latest scalar values, no history array.

## 14. Accessibility

No new accessibility regressions were introduced: the three new panels use the existing `shell()`
wrapper, which already sets `role="dialog"`, `aria-label`, and `tabindex="-1"` with focus management
on open/close (confirmed by reading `shell()`'s own implementation, §1) — this is inherited
automatically by every `F.<id>` factory, including the three added this task. No new interactive
control was added inside the new panels beyond plain read-only text — no new keyboard trap risk, no
new custom widget requiring its own ARIA role. `prefers-reduced-motion` was not newly addressed (no
new animation was added that would need it).

## 15. Screens/Pages/Components Map (as of this task)

```
VECTOR (single HUD "screen")
├── Lock/boot layer: #boot, #globe, #clock, #hint, #auth-scan
├── Backdrop: #grid, #dust, #sweep, #scanlines, #vignette, #herocam, #hero-hud
├── Tickers: .ticker.top (#stockTrack), .ticker.bot (#newsTrack)
├── Core: #orb-wrap (js/orb.js)
├── Frame chrome: #frame (.edge, .corner, .glyph × 4, .ticks)
├── Dock: #dock (6 lean buttons: VOICE/CHAT/GOALS/APPROVALS/PANELS/SOUND)
├── #workspace (the "secret workspace" — toggled by PANELS)
│   ├── Rich live panels: chat, music, map, webcam, telemetry, market, goals,
│   │   districts, council, security, memory, approvals, finance, ...
│   ├── Capability-card panels (~30): brainpanel, corepanel, agentspanel, ...
│   └── NEW (Task 73): memoryexplorer, cognition, experiment
├── #director (dev-panel mount, not modified)
└── #cursor (hand/pinch cursor for gesture control)
```

## 16. Post-Experiment Frontend Roadmap

1. **Immediate, safe, no-backend-dependency:** rebuild `dist/vector-hud.prod.js` via
   `tools/build_frontend.py` so the three new panels reach the production HUD (`VECTOR.prod.html`),
   not just the dev entry point.
2. **Requires new backend read-only endpoints (§12 / `73_FRONTEND_DATA_CONTRACTS.md`):** light up
   Memory Explorer's four currently-dark subsystems and Cognition Panel's seven currently-`UNKNOWN`
   stages.
3. **Requires the experiment-segment aggregation endpoint:** make Experiment Observatory's two
   autonomy-labeling rows real.
4. **Once Learning Architecture V2 (Task 72) is implemented (explicitly gated on the experiment
   concluding):** Memory Explorer's static architecture-assessment column should be re-derived from
   the actual post-V2 behavior rather than the pre-V2 audit findings baked in today — this file's own
   assessments should be treated as a snapshot of the current architecture, not a permanent
   description.
5. **Cognition Panel's ADAPTING/LEARNING stage visualization** could eventually surface the same
   Level 0-7 ladder defined in Task 72 §5, once a state-change log (Task 72 §7) exists to query
   against — explicitly not attempted this task, since that log does not exist yet.

---

## 17. Open Items / Not Independently Re-Verified This Task

- Whether the currently-running HUD API process (PID 36996) is genuinely serving `VECTOR.html` (dev)
  rather than `VECTOR.prod.html` — inferred from how it was launched, not directly probed.
- `js/vector-core.js`'s exact `V.http`/WS implementation was not re-read in full this task — used
  as-is via the already-established `apiGet`/`apiPost` wrapper pattern in `widgets.js`.
- Whether `/brain/epistemic/summary` returns a shape matching this task's `countPath` assumption —
  not independently verified against a live response (per the strict "do not touch anything tied to
  the experiment host" posture); the panel degrades gracefully to "NO LIVE SOURCE" styling on any
  fetch failure or shape mismatch, so an incorrect assumption here fails safely, not silently wrong.

---

## STATUS

```
Running experiment process touched: NO
Experiment database touched: NO
Experiment logs touched: NO
Experiment configuration touched: NO
Synthetic stimulus introduced: NO
Autonomous behavior changed: NO
Decision behavior changed: NO
Memory behavior changed: NO
Policy behavior changed: NO
Epistemic behavior changed: NO
Scheduler changed: NO
Permission system changed: NO
```

- **Existing frontend stack:** vanilla HTML/CSS/JS, no framework, vendored three.js + MediaPipe,
  hand-built event bus + polling layer, ~50 existing panels across two patterns (rich-live and
  capability-card), served via FastAPI's `/hud/` route with a dev/prod HTML split.
- **Existing HUD architecture:** documented in full in §3.
- **Preserved:** everything except the three files listed in §8 — verified via `git status` showing
  exactly those three files changed, `.py` diff count unchanged at 64, git HEAD unchanged.
- **Improved:** nothing in the existing panel set (a deliberate scope choice, §6).
- **Newly implemented:** Memory Explorer, Cognition Panel, Experiment Observatory (§4).
- **Files changed:** `frontend/js/widgets.js`, `frontend/js/terminal.js`, `frontend/styles/widgets.css`.
- **Files created:** none (code); two documentation files under `VECTOR_TECHNICAL_KNOWLEDGE/`.
- **Real vs. mock integrations:** 100% real, pre-existing endpoints reused; zero mock/fabricated data
  introduced (§11).
- **Backend work deferred until after Segment 2:** listed in full in §12 and in
  `73_FRONTEND_DATA_CONTRACTS.md`.
- **Performance concerns:** none identified beyond the noted minor, bounded polling duplication while
  a new panel happens to be open at the same time as an existing one (§13) — not considered a real
  risk given the existing system already runs 16+ concurrent named polls.
