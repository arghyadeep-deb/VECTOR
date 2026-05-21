# VECTOR JARVIS Dashboard — Architecture

> Canonical dashboard for VECTOR. Match the huwprosser-style JARVIS reference
> (locked → idle → listening → thinking → speaking, freeform widget canvas,
> hand-tracked cursor, multi-intent voice, MapLibre/Leaflet map with shadowbroker
> live geospatial layers).

## Why this folder is canonical

Three React/Vite dashboards exist in the repo; this one (`core/ui/dashboard/`)
is the most advanced and the one we extend going forward:

| Folder | State | Decision |
|---|---|---|
| `core/ui/dashboard/` | 60+ components incl. VectorOrb, BootSequence, GestureOverlay, MapView, FortressMode, InfiniteCanvas, vectorStore (Zustand) | **Canonical** — extend here |
| `dashboard/` | Static 3-column grid (ChatPanel/AgentPanel/SystemMetrics/DistrictMap) | Legacy — do not extend |
| `dashboard/mirofish/` | Vue 3 frontend for `/simulation` | Standalone — leave alone |
| `dashboard/ml_intern/` | React/MUI frontend for the ML-intern smolagents UI | Standalone — leave alone |
| `dashboard/vibe_trading/` | React/ECharts frontend for trading | Standalone — leave alone |

All three sibling frontends contain zero `.py` files; they ship with their own
`package.json` and `vite.config` and run independently.

## Orb finite-state machine

`vectorStore.ts → voiceState: 'idle' | 'listening' | 'processing' | 'speaking'`
plus `mode: 'JARVIS_MODE' | 'DASHBOARD_MODE' | 'FORTRESS_MODE'` and
`bootDone: boolean`.

```
boot   → BootSequence (3.6s scan-in)        bootDone=true
locked → mode=FORTRESS_MODE                 wake_word | open_palm → idle
idle   → orb visible, no input              wake_word → listening
listen → frame border glows blue            transcript_end → processing
proc   → orb spins faster                   tts_start → speaking
speak  → orb breathes/glows                 tts_end → idle
inactive(60s) → locked
```

**Frame-glow rule (from reference):** the screen border glows on *input*
(`voiceState === 'listening'`), never on *output* (`voiceState === 'speaking'`).
The orb itself glows on `speaking`.

## Data sources

| Stream | Backend | Frontend consumer |
|---|---|---|
| `/ws` | `core/api/routers/websocket.py` | `vectorStore` (status, events) |
| `/voice_ws` | `core/api/routers/voice_ws.py` | `voiceState` updates, transcript |
| `/gesture/ws` | `core/api/routers/gesture.py` (MediaPipe) | `GestureOverlay` (cursor + widget control) |
| `/camera/ws` | `core/api/routers/camera.py` (YOLO) | `CameraView` widget |
| `/location/current` | `core/api/routers/location.py` (IP geo) | Default centering |
| `/sb/*` | `core/api/routers/sb.py` (proxy → shadowbroker_server :8765) | `MapView` flyTo + live OSINT layers |
| `/news/headlines` | `core/api/routers/news.py` | NewsTicker (bottom marquee) |
| `/finance/ticker` | `core/api/routers/finance.py` | StockTicker (top marquee) |
| `/research/search` | `core/api/routers/research.py` | SchematicSearchWidget |

## Widget registry

A widget = `{ id, title, component, defaultPos, defaultSize, voiceOpen[], voiceClose[] }`.
Voice phrases are matched in `core/voice/ambient_listener._classify_intents()`
which now returns a list of intents per utterance ("close Spotify and show me
London" → `[widget.close('music'), widget.show_location('London')]`).

The freeform canvas is `InfiniteCanvas.tsx` (already exists, supports drag and
zoom). New widgets register in `widgets/registry.ts`.

## Hand cursor

`GestureOverlay` already consumes `/gesture/ws`, renders the fingertip dot, and
maps gestures:

| Gesture | Action |
|---|---|
| `point` | Cursor hover |
| `pinch` | Drag widget (synth mousedown/mouseup) |
| `open_palm` | Wake from locked / dismiss FortressMode |
| `fist` | Close active widget |
| `swipe_left` | Dismiss most-recent widget |
| `swipe_right` | Restore last-dismissed widget |

## Shadowbroker integration

Shadowbroker_server runs on **port 8765** (env `SHADOWBROKER_PORT=8765`) so it
does not collide with VECTOR's main API on 8000. Main API proxies it under
`/sb/*` so the dashboard sees a single origin.

- `/sb/geocode?q=London` → SB Nominatim proxy → `{lat, lon, display_name}`
- `/sb/layer/{name}` → SB live data layer (flights/ships/satellites/datacenters/military_bases/...)
- `/sb/sse` → relays SB layer-changed events; map widget subscribes once

## Tests

- Backend: `pytest` (existing).
- Frontend: Vitest + @testing-library/react + jsdom (added in Task 1).
  Smoke test: `<App />` renders without throwing.
  Run with `npm test` from `core/ui/dashboard/`.

## Out of scope (per `KNOWN_ISSUES.md`)

- Custom LLM training, OpenMythos, FlashAttention, ReasoningBank
- Production deployment (Fly.io, Cloudflare, Supabase)
- Rebuilding the three standalone sibling frontends
