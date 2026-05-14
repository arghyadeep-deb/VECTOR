# VECTOR Dashboard — Fix Prompts

Copy-paste these into Claude Code sessions. Each is self-contained and scoped to one concern.

---

## Priority 1 — Kill Fake Data

### P1.1 — Wire system metrics to real API

```
In the Holographic HUD React dashboard at core/ui/dashboard/src/:

1. Fix CornerHUD.tsx — Replace the hardcoded MetricBars values (PROC 0.62, NET 0.35, DISK 0.78, GPU 0.45 at line 100-104) with real data from the Zustand store's `status` field. The `/status` API already returns system metrics via psutil. Fetch: `status.system?.cpu_percent`, `status.system?.memory_percent`, `status.system?.disk_percent`, `status.system?.gpu_percent`. Also remove the `Math.floor(Math.random() * 360)` heading (line 173) — either wire to real data or remove it.

2. Fix LowerHUD.tsx — Replace the VerticalBarGraph's `useMemo(() => Array.from({length:6}, () => Math.random()), [])` at line 7 with real CPU/RAM/NET/GPU/I/O/TMP data from the status store. Poll and animate smoothly.

3. Fix CoreStatusPanel.tsx — Replace the local `useState(0)` uptime counter (line 12) with `status.uptime_seconds` from the Zustand store. Replace the hardcoded `useState(42)` cycles counter with real data. The /status endpoint already returns these fields.

4. Fix Sparkline.tsx — Replace `Math.random() * height` at line 13 with real trend data. The sparkline should show actual HP history or memory usage over time, fetched from the backend. If no history API exists yet, use a rolling buffer of the last N values from the polling endpoint.

5. Fix api.ts hpColor function (lines 80-85) — The conditions for hp >= 800, >= 600, and >= 400 all return the same '#00CFFF'. Make them distinct: hp >= 800 → '#00FF88' (emerald, elite), hp >= 600 → '#00CFFF' (cyan, strong), hp >= 400 → '#39d353' (green, okay), hp >= 200 → '#ffaa00' (yellow, weak), < 200 → '#ff4444' (red, critical).

Make every change minimal and surgical. Only touch the lines listed above.
```

### P1.2 — Kill fake events in EventFeed

```
In the Holographic HUD React dashboard at core/ui/dashboard/src/components/EventFeed.tsx:

1. Remove the SIM_TEMPLATES array (lines 74-87) and the generateSimEvents() function (lines 89-102).

2. Fix the useMemo at lines 138-144: instead of padding with simulated events when real events < 22, just show whatever real events exist. Remove the MIN_ENTRIES threshold entirely.

3. When there are zero events, show a single dimmed line: "AWAITING TELEMETRY..." instead of fabricating activity.

4. Ensure the loading state (line 194) shows "CONNECTING..." initially and transitions to "AWAITING EVENTS..." only after the first poll attempt fails or returns empty.

The dashboard should NEVER display events that didn't actually happen. Empty state is honest and acceptable.
```

---

## Priority 2 — Error Handling & Resilience

### P2.1 — Add error handling to every API call

```
In the Holographic HUD React dashboard at core/ui/dashboard/src/:

1. Create a new file lib/poller.ts with a generic polling utility:
   - Takes a key, fetch function, interval, and callbacks (onSuccess, onError)
   - Tracks health state per key: 'ok' | 'retrying' | 'dead'
   - On failure: retries 3 times with 2s/4s/8s exponential backoff
   - On 3 consecutive failures: marks endpoint as 'dead', fires onError
   - On success after retry: resets to 'ok', fires onRecovered callback
   - Returns a cleanup function (clearInterval)
   - Exports a React hook usePoll(key, fetcher, intervalMs, callbacks)

2. Refactor EventFeed.tsx (lines 120-132):
   - Replace the raw setInterval with the new usePoll hook
   - On error: set an error state, show an orange "CONNECTION LOST — retrying..." bar above the feed
   - On recovery: show a brief green "RECONNECTED" toast, then resume normal display

3. Refactor TelemetryPanel.tsx:
   - If status is null for >10s (no data from /status), show a red overlay: "TELEMETRY OFFLINE"
   - If agents array is empty, show dimmed zeros instead of the scrambling animation

4. Refactor TopBar.tsx (line 141):
   - Add a third status state: ONLINE (green), OFFLINE (red), CONNECTING (yellow pulse)
   - Show CONNECTING for the first 5 seconds before marking ONLINE or OFFLINE

5. Add a global error state to the Zustand store (vectorStore.ts):
   - `connectionErrors: Record<string, { failed: boolean, lastError: string, retryCount: number }>`
   - Expose a `reportError(endpoint: string, error: string)` action
   - Any component can push errors here; a StatusBar-like component can display them

Keep the utility file lean (<100 lines). No external dependencies beyond React hooks.
```

### P2.2 — Add error boundary + WebGL fallback

```
In the Holographic HUD React dashboard at core/ui/dashboard/src/:

1. Create components/ErrorBoundary.tsx:
   - Standard React error boundary with componentDidCatch
   - Renders a dark overlay with cyan border, "SYSTEM ERROR" header in Orbitron font
   - Shows the error message in JetBrains Mono
   - Has a "REBOOT DASHBOARD" button that reloads the page

2. Wrap the <App /> in main.tsx with the ErrorBoundary.

3. In three/VectorScene.tsx:
   - Wrap all Three.js initialization in try/catch
   - If WebGL context creation fails (no GPU, headless browser, etc.):
     - Export a `hasWebGL` boolean
     - In App.tsx, render a 2D fallback scene (CSS-only rotating rings instead of Three.js sphere) when hasWebGL is false
   - Add a canvas error event listener: canvas.addEventListener('webglcontextlost', handler)
   - Attempt context restoration once: canvas.addEventListener('webglcontextrestored', handler)

4. In styles.css, add a CSS-only fallback animation for the background (pulsing radial gradient) that activates if the Three.js canvas fails to render.
```

### P2.3 — Fix api.ts hardcoded URL

```
In core/ui/dashboard/src/lib/api.ts:

1. Remove the hardcoded `const STATUS_API = 'http://127.0.0.1:8000'` at line 60.

2. Replace fetchStatus() with a version that uses relative URLs:
   - In development (import.meta.env.DEV): use the Vite proxy (empty prefix, same as the existing `BASE = ''`)
   - In production (import.meta.env.PROD): use the same origin as the page is served from

3. Add a configurable base URL via an environment variable:
   - `VITE_API_BASE` — if set, prepend to all API calls
   - Default to empty string (same-origin)

4. Remove the duplicate fetch pattern — `api.status()` already fetches `/status` correctly via the proxy. The standalone `fetchStatus()` function at line 61 is redundant. Refactor all callers to use `api.status()` instead.
```

---

## Priority 3 — Bug Fixes

### P3.1 — Fix z-index scale

```
In the Holographic HUD React dashboard at core/ui/dashboard/src/:

Create lib/zIndex.ts with a single source of truth:
```ts
export const Z = {
  SCENE:          0,    // Three.js 3D scene
  BACKGROUND:     2,    // Grid + hex overlay
  DECORATIONS:    10,   // Rings, scanlines, vignette
  HOLOGRAM:       20,   // CentralHologram
  ARC_REACTOR:    25,   // ArcReactor
  LOWER_HUD:      35,   // Bar graph + EKG + mini radar
  EVENT_FEED:     40,   // Center event feed
  CORNER_HUD:     45,   // Compass + metric bars
  CORE_STATUS:    46,   // Draggable status panel
  TELEMETRY:      50,   // Telemetry + Districts panels
  VOICE:          55,   // VoiceWaveform
  ALERTS:         80,   // AlertSystem toasts
  TOP_BAR:        100,  // TopBar + QuickActions
  FLOATING:       9999, // FloatingPanelManager portals
}
```

Then update every component that uses a literal z-index number to import and use `Z.COMPONENT_NAME` instead. Affected files:
- App.tsx (all `zIndex` values in layout comments)
- TopBar.tsx (zIndex: 100)
- CornerHUD.tsx (zIndex: 45, 101)
- CoreStatusPanel.tsx (zIndex: 46)
- TelemetryPanel.tsx (zIndex: 50)
- DistrictsPanel.tsx (zIndex: 50, actually says 100 on line 49)
- LowerHUD.tsx (zIndex: 35)
- VoiceWaveform.tsx (zIndex: 55)
- EventFeed.tsx (ticker zIndex: 90)
- AlertSystem.tsx (zIndex: 80)
- QuickActions.tsx (zIndex: 100)

After the refactor, run the dashboard and verify no component is hidden behind another.
```

### P3.2 — Fix legacy dashboard XSS + error handling

```
In core/ui/web_ui.py:

1. Fix the XSS vector at line 581: Replace `row.innerHTML` with safe DOM construction (createElement, textContent, appendChild), consistent with the rest of the file that uses the `el()` helper. The row elements for task name, status, elapsed, district should all be created via document.createElement, not innerHTML string interpolation.

2. Fix pollStatus() at line 548: Remove the bare `catch(e){}`. Instead:
   - Set badge classes to "badge red" with text "Ollama: LOST" and "Loop: UNKNOWN" on failure
   - Set right-panel values to "—" with red color
   - After 3 consecutive failures, show a persistent banner at the top: "⚠ Connection to VECTOR backend lost"

3. Add a textarea maxlength: Add `maxlength="2000"` to the chat input (line 150)

4. Store chatHistory in sessionStorage instead of a JS array (line 291):
   - On each new message, persist to sessionStorage.setItem('vector-chat', JSON.stringify(history))
   - On page load, restore from sessionStorage
   - Keep the 20-message cap

5. Replace all `alert()` calls in quick actions (lines 562-564) with inline rendering inside a dedicated quick-result div below the quick action buttons.

Make changes surgical — do not refactor the overall structure of the file.
```

### P3.3 — Fix DistrictsPanel live-status check

```
In core/ui/dashboard/src/components/DistrictsPanel.tsx:

The district status dots (line 73) use `liveDistricts.includes(name)` but `liveDistricts` comes from `status?.agents.districts` which is always undefined/empty because the /status API response doesn't include a `districts` field in the expected path.

Fix: Remove the dynamic live-district check entirely. Instead:
- Show all districts with the same cyan dot (no "live/dead" distinction)
- Or, if you want real status, read it from the agents array: a district is "live" if any agent in the store has that district name AND is_alive === true

Implementation:
```tsx
const liveDistricts = useVectorStore((s) => {
  const districtSet = new Set<string>()
  s.agents.forEach((a) => {
    if (a.is_alive && a.district) districtSet.add(a.district.toLowerCase())
  })
  return districtSet
})
// Then: status dot is cyan if liveDistricts.has(name), dim otherwise
```

Also remove the debug console.log at lines 30-31 and the stray useEffect that logs the parent element.
```

---

## Priority 4 — UX Improvements

### P4.1 — Add streaming chat via WebSocket

```
In the Holographic HUD React dashboard at core/ui/dashboard/src/:

1. Create lib/websocket.ts:
   - connectWebSocket(): connects to `ws://${window.location.hostname}:8000/ws/chat`
   - Returns an object with send(message), onToken(callback), onDone(callback), close()
   - Handles reconnection with 3s/5s/10s backoff (3 retries max)
   - Parses incoming messages as JSON: { type: 'token', text: string } | { type: 'done', full: string } | { type: 'error', message: string }

2. Refactor components/CommandInput.tsx:
   - Replace the HTTP POST fetch (lines 62-73) with WebSocket connection
   - On send: show the ⚡ prompt as active (pulsing), clear any previous response
   - On each 'token' message: append to the response area character by character (streaming)
   - On 'done': stop the pulsing animation, enable input
   - On 'error': show the error in red in the response area, re-enable input after 2s
   - On WebSocket close/crash: fall back to HTTP POST silently (degradation, no user-visible error)

3. In the response area (line 39-49), add an animated cursor effect during streaming:
   - A blinking cyan block cursor at the end of the text while tokens are arriving
   - Removes the cursor when streaming completes

4. Add the WebSocket route to the FastAPI server (core/main.py or core/ui/web_ui.py) if it doesn't exist:
   - Accept connection at /ws/chat
   - On message: call the same chat logic as POST /ui/chat
   - Stream tokens back via WebSocket send() as they arrive from Ollama

This enables token-by-token display matching the terminal TUI experience.
```

### P4.2 — Add Zustand persist middleware

```
In the Holographic HUD React dashboard at core/ui/dashboard/src/store/vectorStore.ts:

1. Install zustand/middleware persist:
   - Import `persist` and `createJSONStorage` from 'zustand/middleware'
   - Wrap the store creator with persist()
   - Store key: 'vector-dashboard-state'
   - Storage: localStorage (via createJSONStorage(() => localStorage))
   - Partialize: only persist 'status', 'agents' (not 'events' which is high-volume, not 'error')

2. Add a `lastUpdated: number` field to the store, set on every status/agents update.

3. In components/TopBar.tsx:
   - Show a small dim indicator if the displayed data is >60s old (stale)
   - Color: dim cyan when fresh, orange when stale, red when >5min old

4. Add 'zustand/devtools' middleware in development mode only:
   ```ts
   import { devtools } from 'zustand/middleware'
   // Only in VITE_DEV===true:
   const store = create<VectorState>()(devtools(persist(/*...*/), { name: 'vector-dashboard' }))
   ```
   This enables debugging via Redux DevTools browser extension.

Keep the migrate function versioned — add version: 1 to persist config.
```

### P4.3 — Add a11y basics

```
In the Holographic HUD React dashboard at core/ui/dashboard/src/:

1. Add aria-labels to all interactive elements:
   - TopBar status dots: `<span role="status" aria-label="System status: ONLINE" />`
   - CommandInput send button: `<button aria-label="Send command to VECTOR">`
   - QuickActions buttons: `<button aria-label="Refresh dashboard status">`
   - FloatingPanel close buttons: `<button aria-label="Close panel">`
   - MortalityFeed items: `<div role="alert" aria-live="polite">` for new deaths

2. Add role attributes to panels:
   - TelemetryPanel: `role="region" aria-label="System telemetry"`
   - EventFeed: `role="log" aria-live="polite" aria-label="Event feed"`
   - DistrictsPanel: `role="navigation" aria-label="Districts"`

3. Canvas elements need fallback text:
   - Compass canvas: `<canvas aria-label="System heading compass">`
   - EKG canvas: `<canvas aria-label="System activity heartbeat">`
   - Radar canvas: `<canvas aria-label="System radar">`
   - ArcReactor canvas: `<canvas aria-label="System power core">`

4. Add a `prefers-reduced-motion` check to disable animations:
   ```ts
   const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
   ```
   - When true: disable all CSS keyframe animations, canvas rAF loops, and Three.js auto-rotation
   - Apply via a CSS class on body or a Zustand store field
   - In VectorScene.tsx: set autoRotate to false when reduced motion is preferred

5. In index.html: add `<meta name="description" content="VECTOR — Autonomous AI System Dashboard">` and set `<html lang="en">`.

Do NOT add any external a11y libraries — keep it to native HTML attributes only.
```

---

## Priority 5 — Production Build Pipeline

### P5.1 — Serve dashboard from FastAPI in production

```
In the VECTOR codebase:

1. In core/ui/dashboard/vite.config.ts:
   - Set `base: '/dashboard/'` — so the built assets are served from /dashboard/
   - Keep the dev proxy to FastAPI at localhost:8000 for API calls

2. In core/ui/web_ui.py:
   - Add a new route: `@router.get("/dashboard/{rest:path}")` that serves static files from `core/ui/dashboard/dist/`
   - Use `fastapi.staticfiles.StaticFiles` to serve the entire dist directory
   - If dist/ doesn't exist (dev mode), return a redirect or a simple message saying to run `npm run dev`

3. Add a build script to the project root:
   - In scripts/build-dashboard.sh (or .ps1 for Windows):
     ```powershell
     Set-Location core/ui/dashboard
     npm ci
     npm run build
     ```
   - The output goes to `core/ui/dashboard/dist/`
   - FastAPI picks it up automatically

4. Test: after building, start the FastAPI server and visit http://localhost:8000/dashboard/ — the Holographic HUD should load with all API calls working via same-origin.

This eliminates the need for the Vite dev proxy in production.
```

### P5.2 — Add CI step to build dashboard

```
In the VECTOR codebase at .github/workflows/:

Add a build step to the existing lint.yml or build.yml workflow:

```yaml
jobs:
  build-dashboard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: core/ui/dashboard/package-lock.json
      - name: Install dependencies
        run: npm ci
        working-directory: core/ui/dashboard
      - name: Build dashboard
        run: npm run build
        working-directory: core/ui/dashboard
      - name: Upload dist artifact
        uses: actions/upload-artifact@v4
        with:
          name: dashboard-dist
          path: core/ui/dashboard/dist/
```

This runs on every push and PR, ensuring the dashboard builds without errors.
```

---

## Post-Cleanup — Remaining Issues Found in Re-Verification

### R1 — Replace alert() calls in QuickActions.tsx (Holographic HUD)

```
In core/ui/dashboard/src/components/QuickActions.tsx:

Replace the two `alert()` calls with inline rendering inside the CommandInput's response area.

1. Remove lines 29-33 (HN TOP action) and 39-43 (GOALS action). Replace them with versions that
   write results to a shared state instead of calling alert().

2. Add a `quickResult: { title: string; lines: string[] } | null` field to the Zustand store
   (vectorStore.ts), plus a `setQuickResult()` action.

3. In QuickActions.tsx, wire the HN TOP and GOALS buttons to call setQuickResult instead of alert():
   ```tsx
   ['HN TOP', async () => {
     const r = await fetch('/ui/hn')
     const d = await r.json()
     const titles = (d.results || []).slice(0, 5).map((x: any) => x.title)
     useVectorStore.getState().setQuickResult({ title: 'HN TOP 5', lines: titles })
   }],
   ['GOALS', async () => {
     const r = await fetchStatus('/ui/goals')
     const goals = (r.goals || []).slice(0, 5)
     const lines = goals.map((g: any, i: number) =>
       `${i + 1}. ${typeof g === 'object' ? (g.action || JSON.stringify(g)) : g}`
     )
     useVectorStore.getState().setQuickResult({ title: 'ACTIVE GOALS', lines })
   }],
   ```

4. In CommandInput.tsx, read `quickResult` from the store and render it below the response area
   when present:
   ```tsx
   const quickResult = useVectorStore((s) => s.quickResult)
   const setQuickResult = useVectorStore((s) => s.setQuickResult)
   // In JSX, after the response div:
   {quickResult && (
     <div style={{ borderTop: '1px solid rgba(0,207,255,0.05)', padding: '6px 12px' }}>
       <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#3388aa', letterSpacing: '0.1em', marginBottom: 4 }}>
         {quickResult.title}
       </div>
       {quickResult.lines.map((line, i) => (
         <div key={i} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff', padding: '2px 0' }}>
           {line}
         </div>
       ))}
     </div>
   )}
   ```

5. Add a dismiss button (✕) that calls setQuickResult(null), so the result card can be closed.

Remove all `alert()` calls from the codebase. Verify with grep that no `alert(` remains in any
.tsx or .ts file under core/ui/dashboard/src/.
```

### R2 — Replace hardcoded zIndex in App.tsx

```
In core/ui/dashboard/src/App.tsx at line 25:

Replace the hardcoded `zIndex: 40` in the centerArea style object with `zIndex: Z.EVENT_FEED`.

Add the import at the top:
```tsx
import { Z } from './lib/zIndex'
```

Then verify: `grep -n 'zIndex: [0-9]' src/App.tsx` should return zero results after the fix.
```

### R3 — Replace hardcoded zIndex in FloatingPanelManager.tsx

```
In core/ui/dashboard/src/components/FloatingPanelManager.tsx at line 66:

Replace `zIndex: 9999` with `Z.FLOATING`.

Add the import:
```tsx
import { Z } from '../lib/zIndex'
```
```

### R4 — Replace innerHTML with textContent in web_ui.py

```
In core/ui/web_ui.py at lines 593-594:

Replace:
```js
runEl.innerHTML="";
recEl.innerHTML="";
```
With:
```js
runEl.textContent="";
recEl.textContent="";
```

`textContent` is faster, safer, and consistent with the createElement pattern used everywhere else
in this file (lines 599-631).
```

### R5 — Make WebSocket stream tokens in real time

```
In core/ui/web_ui.py at lines 760-767:

The WebSocket chat endpoint currently calls `chat()` which blocks until the entire response is
ready, then sends it as a single token message. This defeats the purpose of WebSocket streaming.

Fix: Replace the blocking `chat()` call with a streaming version.

1. In core/inference/ollama_safe.py, if not already present, add a `chat_stream()` function that
   yields tokens as they arrive from Ollama:
   ```python
   def chat_stream(model: str, messages: list, timeout: float = 120.0):
       """Yields response tokens one by one from Ollama."""
       import ollama
       stream = ollama.chat(model=model, messages=messages, stream=True, options={"num_predict": 2048})
       for chunk in stream:
           token = chunk.get("message", {}).get("content", "")
           if token:
               yield token
   ```

2. In the websocket route (web_ui.py line 740), replace the blocking call:
   ```python
   response = chat(model=..., messages=..., timeout=120.0)
   await websocket.send_json({"type": "token", "text": response})
   await websocket.send_json({"type": "done", "full": response})
   ```
   With streaming:
   ```python
   full = ""
   for token in chat_stream(model=CONFIG["models"]["focus"], messages=messages):
       full += token
       await websocket.send_json({"type": "token", "text": token})
   await websocket.send_json({"type": "done", "full": full})
   ```

3. Verify the frontend in CommandInput.tsx already handles individual tokens via onTokenReceived
   (it does — lines 20-24). No frontend changes needed.

This gives real character-by-character streaming in the Holographic HUD chat, matching the terminal
TUI experience in chat.py.
```

---

## Execution Order

```
Phase 1 — Kill Fake Data    (P1.1, P1.2)
    ↓
Phase 2 — Error Handling    (P2.1, P2.2, P2.3)
    ↓
Phase 3 — Bug Fixes         (P3.1, P3.2, P3.3)
    ↓
Phase 4 — UX Improvements   (P4.1, P4.2, P4.3)
    ↓
Phase 5 — Build Pipeline    (P5.1, P5.2)
    ↓
Phase 6 — Remaining Issues  (R1, R2, R3, R4, R5)
```

Each prompt is ~5-30 minutes of work for Claude Code. Total ~4-5 hours.
