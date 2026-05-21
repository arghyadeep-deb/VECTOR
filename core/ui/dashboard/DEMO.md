# VECTOR JARVIS Dashboard — End-to-End Demo

> Walkthrough that exercises every state and widget from the reference. Each
> step is tagged with the task number from the implementation plan. This
> file is the source of truth for the demo script in Task 15.

---

## 0. Prerequisites

```bash
# Backend (port 8000)
python -m core.api.app
# or:
.\START_VECTOR.bat

# Shadowbroker (port 8765, optional — map will use IP geolocation otherwise)
cd districts/intelligence/shadowbroker_server
$env:SHADOWBROKER_PORT="8765"
python main.py

# Dashboard (Vite, port 5173)
cd core/ui/dashboard
npm install
npm run dev
# Browse to http://localhost:5173 (or http://localhost:8000 once npm run build is run)
```

Optional: open as a borderless transparent fullscreen via Tauri:

```bash
cd desktop
cargo tauri dev
```

---

## 1. Boot — `BootSequence` (Task 1, 2)

Open the dashboard. You should see:

- 200 ms black overlay → faint cyan border → bright cyan border → top-down
  scan line → orb fades in → boot complete (~3.6 s)
- After boot the orb sits centred. The screen border is a thin cyan glow.

Verifies: `BootSequence`, the existing `VectorOrb`, and the new `JarvisFrame`
chrome (Task 3) sitting on top.

## 2. Idle — `JarvisFrame` ambient (Task 3)

The 4-corner brackets are dim cyan. The frame is **not** glowing because no
voice input is active. The orb pulses slowly. Stock ticker is scrolling at
the top, news ticker at the bottom (Task 12 frontend).

Verifies: `<StockTicker />`, `<NewsTicker />`, `JarvisFrame intensity=0.18`.

## 3. Locked — 60 s of inactivity (Task 4)

Walk away for 60 s without speaking, moving the mouse, or opening any widget.

- Screen fades to the **LockedScreen** overlay: black grid background, big
  centred orb, large `HH:MM` clock, day/date underneath, "SAY 'HEY VECTOR' ·
  WAVE TO WAKE · CLICK / ENTER" hint.
- Verifies: `useInactivityLock()` and `<LockedScreen />`.

Wake by either:
- saying **"Hey VECTOR"** (real wake-word path)
- showing an **open palm** to the webcam (gesture path → `vector:wake`)
- clicking the screen / pressing Enter / Space (manual path).

## 4. Listening — frame glow on input (Task 2 + 3)

Say: **"Hey VECTOR ... what time is it"**. As soon as the wake word fires:

- `voice_ws.py` emits `{type:"orb_state", state:"listening"}` over `/ws`
- `useVectorWS()` hook updates `voiceState='listening'` in the store
- `<JarvisFrame />` snaps to glow intensity 1.0 — bright cyan border + thin
  pulsing inner outline ("frame glows blue while you talk")

VECTOR transcribes → switches to `processing` (orb spins faster) → then to
`speaking` (orb glows/breathes; frame returns to neutral).

Verifies: orb FSM end-to-end, frame-glow only on input.

## 5. Multi-intent voice (Task 6)

Say: **"Open the music widget and show me London."**

- `core/voice/ambient_listener._classify_intents()` returns:
  ```json
  {"intents":[
    {"action_type":"widget_open","params":{"id":"music"},"confidence":0.92},
    {"action_type":"widget_show_location","params":{"query":"London"},"confidence":0.9}
  ]}
  ```
- The permission gateway loops both, executing each as GREEN (config.py).
- For each, `_execute_action()` broadcasts a `ui_event` over `/ws`.
- `useVectorWS()` consumes both:
  - `widget_open(music)` → `addContentWindow({id:'music',type:'text',title:'Music'})`
    → `<MusicWidget />` appears (registry resolves `music` → `MusicWidget`).
  - `widget_show_location({query:'London'})` → opens map widget if not open,
    then dispatches `vector:show-location` event. `MapView` listens, calls
    `/sb/geocode?q=London`, gets `{lat:51.5074,lng:-0.1278}`, and `flyTo`'s
    the dark-tile Leaflet map there with a pulsing cyan marker.
- VECTOR speaks: "Opening the music widget. Showing London on the map."

Verifies: multi-intent parser, gateway loop, `/ws` `ui_event` channel,
`/sb/geocode` proxy, registry, MapView extension.

## 6. Hand cursor + pinch-drag (Task 7)

Hold an open hand to the webcam. The cyan dot in `GestureOverlay` follows
your fingertip.

- **Pinch** (thumb + index together): `GestureOverlay` synthesizes a
  `pointerdown` at the cursor position. Any draggable widget under that
  point begins dragging. Releasing the pinch synthesizes `pointerup`.
- **Fist**: closes the topmost widget (most-recently-opened).
- **Open palm**: dispatches `vector:wake` (also wakes from locked).
- **Swipe left**: dismisses last widget. **Swipe right**: restores it.
- **Point**: hover only.

Verifies: pinch-drag, `vector:wake`, the new gesture mapping.

## 7. Music widget voice control (Task 10)

With `<MusicWidget />` open, say:
- **"Pause"** → `music_pause` → voice flow → `vector:music` CustomEvent →
  widget pauses local mock playback.
- **"Next track"** → `music_next` → widget advances.

Verifies: `MusicWidget` mock player + voice event listener.

## 8. Camera widget (Task 11)

Say **"Open camera"**. The existing `CameraView` consumes `/camera/ws`, shows
the live JPEG frame full-screen with YOLO bounding-box detections. Click the
top-right invisible zone to close.

## 9. Schematic search + 3D building (Task 13)

Say **"Open schematic search"**. `<SchematicSearchWidget />` opens. Type a
query, hit Enter — results stream from `/research/search`.

Say **"Open data analysis"**. `<BuildingWidget />` opens — wireframe
city-block geometry slowly rotating (matches reference panel #6).

## 10. Tickers (Task 12)

Top strip: stock quotes (red ▼ / green ▲). Refreshes every 30 s via
`/finance/ticker?symbols=AAPL,MSFT,...`.

Bottom strip: news headlines preceded by red **BREAKING** badge. Refreshes
every 120 s via `/news/headlines`.

Verifies: `StockTicker`, `NewsTicker`, the new ticker REST endpoints.

## 11. Tauri shell (Task 14)

```bash
cd desktop
cargo tauri dev
```

The dashboard opens as a **borderless transparent fullscreen** window
(`decorations: false`, `transparent: true`, `fullscreen: true`). The system
tray icon shows the running state. The locked screen now actually overlays
your desktop wallpaper through the transparent window.

## 12. Sleep — 60 s of inactivity → back to locked

Verifies: the inactivity timer reverses everything; we're back at step 3.

---

## Test commands

```bash
# Backend
pytest -q

# Frontend
cd core/ui/dashboard
npm test
```

Both should pass before considering the demo complete.

## Voice phrase cheat sheet

| Phrase | Action |
|---|---|
| "Hey VECTOR" | Wake word — start listening |
| "show me <place>" | `widget_show_location` — open map + geocode + flyTo |
| "open music" / "open the music widget" | Open `MusicWidget` |
| "close music" | Close `MusicWidget` |
| "play" / "pause" / "next track" / "previous track" | Control music |
| "open camera" / "close camera" | Toggle `CameraView` |
| "open schematic search" / "open research" | Open `SchematicSearchWidget` |
| "open data analysis" / "show city block" | Open `BuildingWidget` |
| "close all widgets" | `widget_close` with `id="all"` |
| "That's all VECTOR" / "stop VECTOR" | End voice session |

## Gesture cheat sheet

| Gesture | Action |
|---|---|
| Open palm | Wake from locked |
| Point | Hover (cursor only) |
| Pinch (thumb+index) | Drag widget under cursor |
| Fist | Close topmost widget |
| Swipe left | Dismiss last widget |
| Swipe right | Restore last-dismissed widget |
| Swipe up/down | Pan canvas |

---

## Failure modes & fallbacks

- If `shadowbroker_server` isn't running, `/sb/geocode` returns
  `{error:"sb_unreachable"}`. The map will not flyTo but the rest of the
  dashboard keeps working.
- If `yfinance` isn't installed, `/finance/ticker` returns hard-coded
  fallback quotes so the marquee still demos.
- If `news_aggregator.py` isn't importable, `/news/headlines` returns 6
  fallback headlines.
- If `mediapipe` isn't installed, `/gesture/ws` closes with an error and the
  hand-cursor simply never appears — voice still works.
- If `Kokoro` ONNX TTS fails, the voice pipeline falls back to `pyttsx3`.

These fallbacks are intentional so the demo always has something to show.
