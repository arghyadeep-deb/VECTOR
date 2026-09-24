# VECTOR — HUD Frontend

A faithful, *living* JARVIS-style HUD for VECTOR. Self-contained HTML/CSS/JS —
no build step. Drop it in as FastAPI's `dist/index.html` (spec §1) and point it
at your backend.

> Owner: Arghyadeep Deb · KIIT CSE 2023-27. Brand tokens, FSM, districts and data
> models follow the VECTOR backend spec you provided.

---

## Run it

Just open `VECTOR.html` in any browser, or serve the folder:

```bash
python -m http.server 8080      # then visit http://localhost:8080/VECTOR.html
```

To use as the FastAPI-served dashboard, copy these into `core/ui/dashboard/dist/`
keeping the structure, and serve `VECTOR.html` as `index.html`.

```
VECTOR.html
styles/  core.css  widgets.css
js/      config.js  data.js  orb.js  ambient.js  vector-core.js  voice_stream.js  widgets.js
         audio.js  gestures.js  face.js  speech.js  cinematic.js  terminal.js  demo.js
```

`js/demo.js` builds the **subsystem dock** (the icon row that opens the map, camera, 3D city, music and the other
panels), the hotkeys and the backend-connect form, and it also carries the Director dev panel, the scripted demo and
the offline seed data. The HUD needs it: do not delete it. (There used to be a separate lean "production" page that
left it out; it was removed 2026-09-25 and there is now one HUD.)

---

## Driving it from code

One global object, `VECTOR`:

```js
VECTOR.wake();                 // lock screen → idle (awake: grid + tickers)
VECTOR.listen();               // INPUT: frame border glows cyan
VECTOR.process();              // rings spin
VECTOR.say('Good evening, sir.');   // OUTPUT: orb glows + waveform + caption + chat
VECTOR.lock();                 // back to standby (orb on black, clock)
VECTOR.fortress();             // security lockdown (red frame, palm to unlock)

VECTOR.openWorkspace();        // reveal the SECRET heavy-work HUD (panel rings)
VECTOR.closeWorkspace();
VECTOR.openWidget('map', { label:'GREATER LONDON · UK' });
VECTOR.openWidget('music', { track:{ title:'Still Into You', artist:'Paramore', dur:216, pos:124 } });
VECTOR.chat.push({ role:'user', text:'show me my goals' });
```

**Glow rule (faithful to the reels):** the frame glows on **input** (`listening`),
the orb glows on **output** (`speaking`) — never both.

Widgets: `chat · music · map · webcam · telemetry · market · goals · districts ·
council · security · memory`. All draggable (mouse head-drag or pinch with the
hand cursor).

---

## Wiring your FastAPI backend

Edit **`js/config.js`** (frontend file — FastAPI just serves it statically):

```js
window.VECTOR_CONFIG = { base:'http://127.0.0.1:8000', ws:'', apiKey:'', autoConnect:true };
```

The HUD auto-connects on load (or stays on demo data if the backend is
unreachable). You can also override per-session via the URL:
`VECTOR.html?base=http://127.0.0.1:8000&key=YOUR_KEY`. Don't commit a real key.

Under the hood this calls:

```js
VECTOR.connect({ base:'http://127.0.0.1:8000', apiKey:'YOUR_VECTOR_API_KEY' });
```

This fetches `/csrf-token` and opens every channel from spec §7, mapping messages
straight to the UI:

| Channel | Message → UI |
|---|---|
| `/ws` | `orb_state` → FSM state · `response` → `say()` · `status` → event |
| `/ws/state` | `state_event` (DECISION_MADE, AGENT_HP_CHANGED…) → `VECTOR.on('state_event')` |
| `/ws/voice/stream` | `transcript` → chat + listen · `response` → say · `audio` → event — `voice_stream.js` streams raw mic audio (getUserMedia + MediaRecorder, webm/opus chunks) here so VECTOR's own Whisper/Kokoro pipeline handles voice instead of the browser's cloud SpeechRecognition; `speech.js` falls back to SpeechRecognition only when this socket is unavailable |
| `/gesture/ws` | `{x,y,gesture}` → hand cursor (point/pinch/open_palm/fist/swipe) |
| `/camera/ws` | `{frame,detections}` → vision widget (`VECTOR.on('camera')`) |
| `/notifications/ws` | hypotheses (`VECTOR.on('notify')`) |

HTTP helpers honour your auth headers (`Authorization: Bearer`, `X-CSRF-Token`):

```js
await VECTOR.command('what is on my calendar?');   // POST /command
await VECTOR.http('/brain/goals');                  // GET, Bearer attached
```

Subscribe to anything:

```js
VECTOR.on('say',   ({text}) => myTTS(text));
VECTOR.on('state', ({from,to}) => console.log(from,'→',to));
VECTOR.on('chat:submit', ({text}) => sendToBackend(text));
```

Offline (no `connect`), the HUD runs on the seed data in `js/data.js` and the
chat does simple local intent replies so you can demo without the backend.

---

## The "secret" heavy-work HUD

The default awake screen is intentionally sparse — just the orb, grid and tickers.
The full panel workspace is revealed three ways (all → `toggleWorkspace`):

- **Hotkey** `Ctrl + Shift + V`
- **Gesture** open palm to the camera (`open_palm`), or a horizontal swipe
- **Command** say / type *"engage workspace"*

`Esc` closes it (or locks if already closed).

---

## Hand tracking

Click the **POINTER** glyph in the dock (or Director → CURSOR):

- **POINTER** — cyan cursor follows the mouse (pinch = mouse-down) for the prototype
- **HAND CAM** — live in-browser MediaPipe tracking via your webcam
  (index fingertip = cursor, thumb-pinch = grab, open palm = wake, fist = close, swipe = workspace)
- Or feed real coordinates from your `/gesture/ws` backend — it takes over automatically.

---

## Dev controls

- **`` ` ``** — toggle the Director panel (state buttons, widget launcher, backend connect, ▶ AUTO DEMO)
- **Ctrl + Shift + H** — **command terminal** (type `help`; e.g. `open map`, `vision`, `engage`, `say hello`)
- **Ctrl + Shift + V** — toggle the secret workspace HUD
- **Space** — listen/idle · **Esc** — close terminal / workspace, or lock
- Dock buttons: **VOICE** (say “Hey VECTOR”) · **WORKSPACE** · **VISION** · **SITUATION ROOM** · **MUSIC** · **POINTER** · **SOUND** (mute)

---

## Brand

`--accent #00CFFF` on black · JetBrains Mono / Chakra Petch · frame idle
`rgba(0,207,255,.18)` → listening `.65`. One fixed design — no live theming.
