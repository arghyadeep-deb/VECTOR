# HUD Dashboard Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade VECTOR HUD dashboard to visually match MCU JARVIS by connecting Three.js scene, data-binding it, adding real mic input, persistent chat history, and a 3D globe.

**Architecture:** The React HUD dashboard (`core/ui/dashboard/src/`) is a Vite+React SPA with Zustand store. All 5 items are frontend-only changes to existing files or new components. The backend `POST /voice` endpoint already exists for mic input.

**Tech Stack:** React 19, Three.js 0.184, @react-three/fiber 9.6, Zustand, MediaRecorder API, localStorage

---

### Task 1: Connect Three.js Scene to App.tsx

**Files:**
- Modify: `core/ui/dashboard/src/App.tsx` — import and render VectorScene
- Modify: `core/ui/dashboard/src/three/VectorScene.tsx` — remove background fill, make transparent

- [ ] **Step 1: Make VectorScene transparent**

The Canvas currently has `background: '#020B18'` — change it to transparent so SVG overlays (ArcReactor, CentralHologram) show through.

Edit `VectorScene.tsx` line 125: remove `background: '#020B18'` from Canvas style

- [ ] **Step 2: Add VectorScene to App.tsx**

Import VectorScene and render it as the deepest layer (z-index 0) above BackgroundCanvas:

```tsx
import VectorScene from './three/VectorScene'
// ...in render:
<VectorScene />
<BackgroundCanvas />
```

- [ ] **Step 3: Build and verify**

Run: `cd core/ui/dashboard && npm run build`

### Task 2: Wire Three.js Scene to Live Data

**Files:**
- Modify: `core/ui/dashboard/src/three/VectorScene.tsx` — accept store data, react to CPU%, mood, agent HP, events

- [ ] **Step 1: Make SceneContent read from Zustand store**

Import `useVectorStore` and destructure `systemMetrics`, `status`, `agents`, `events`. Use data to:
- CPU% → HolographicRing rotation speed (0.2-1.0x)
- Alert from events → CoreSphere emissive color (#00CFFF → #FF3D3D)
- Agent count → ParticleField count (200 + agents * 5)
- Average HP → wireframe opacity (0.05-0.25)

- [ ] **Step 2: Build and verify**

Run: `cd core/ui/dashboard && npm run build`

### Task 3: Real Mic Input

**Files:**
- Create: `core/ui/dashboard/src/components/VoiceInput.tsx`
- Modify: `core/ui/dashboard/src/components/CommandInput.tsx` — add mic button
- Modify: `core/ui/dashboard/src/lib/api.ts` — add voice API call

- [ ] **Step 1: Add voice API call to api.ts**

```tsx
voice: (blob: Blob) => {
  const form = new FormData()
  form.append('audio', blob, 'voice.webm')
  return fetch(`${BASE}/voice`, { method: 'POST', body: form }).then(r => r.json())
}
```

- [ ] **Step 2: Create VoiceInput component**

MediaRecorder wrapper: start/stop recording, POST blob to `/voice`, return transcript + response text.

- [ ] **Step 3: Add mic button to CommandInput**

A mic icon button next to the EXEC button. On click, start recording (red pulse animation), on second click stop and send. Response text fills the command input.

- [ ] **Step 4: Build and verify**

Run: `cd core/ui/dashboard && npm run build`

### Task 4: Persistent Chat History

**Files:**
- Modify: `core/ui/dashboard/src/components/CommandInput.tsx` — save to localStorage, add history toggle

- [ ] **Step 1: Add localStorage save/load**

Save `{cmd, resp, ts}` entries on each command completion. Load on mount. Max 50 entries.

- [ ] **Step 2: Add history toggle button**

A clock icon button that shows recent history as a dropdown list. Click an entry to re-populate the command input.

- [ ] **Step 3: Build and verify**

Run: `cd core/ui/dashboard && npm run build`

### Task 5: 3D Globe Overlay

**Files:**
- Create: `core/ui/dashboard/src/three/VectorGlobe.tsx`
- Modify: `core/ui/dashboard/src/three/VectorScene.tsx` — add globe toggle

- [ ] **Step 1: Create VectorGlobe component**

Three.js sphere with Earth texture (generated via canvas — blue sphere with random green/brown dots), atmosphere glow, rotation, point markers.

- [ ] **Step 2: Wire into VectorScene**

Add globe as optional child, toggleable via store flag. Button in QuickActions to toggle.

- [ ] **Step 3: Build and verify**

Run: `cd core/ui/dashboard && npm run build`
