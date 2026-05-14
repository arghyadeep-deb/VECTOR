# VECTOR Holographic HUD Dashboard — Single-File Spec

## 1. Purpose
Replace the existing multi-page dashboard with a single, immersive **JARVIS-style HUD** served as one standalone HTML file. Zero build step, zero framework — portable, instantly previewable.

## 2. Architecture
- **Single HTML file** — all CSS inline in `<style>`, all JS inline in `<script>`
- **Google Fonts** via CDN (JetBrains Mono)
- **Canvas 2D** for orb particle field (not Three.js — keeps file size ~zero)
- **CSS keyframe animations** for rings, pulses, scanlines, shimmer
- **setInterval/requestAnimationFrame** for live clock, event feed simulation, bar animations
- **No external JS dependencies** — no React, no build tools

## 3. Layout (7 zones, single screen)

```
┌──────────────────────────────────────────────────────────────────┐
│ V.E.C.T.O.R. ▲  ● ONLINE  │  UPTIME 4h  │ AGENTS 24 │ V1.3 │ 14:32:59 │  ← TOP STATUS BAR
├───────────────────┬──────────────────────────────────┬───────────┤
│                   │                                  │           │
│  EVENT FEED       │     ORB VISUALIZATION            │ DISTRICTS │
│  [14:32:59] [CHAT]│     (central glowing core        │ ● coding  │
│  [14:32:58] [GOVE]│      + 3 orbital rings           │ ● finance │
│  [14:32:57] [SYS] │      + particle field)           │ ● govern  │
│                   │                                  │ ● health  │
│  ───────────────  │                                  │ ● memory  │
│  TELEMETRY        │  ┌───────────────────────────┐   │ ● projcts │
│  CPU ████░        │  │ ⚡ COMMAND ►────────── ▶ │   │ ● reflctn │
│  MEM ███░░        │  └───────────────────────────┘   │ ● resrch  │
│  AGENTS: 18       │  [CPU ██] [RAM ██] [DSK ██]     │ ● securty │
│  MODE: FOCUS      │  ~~~~~~~~ sine wave ~~~~~~~~     │ ● time_cl │
│                   │                                  │           │
├───────────────────┴──────────────────────────────────┴───────────┤
│ [AI NEWS] [HN TOP] [REFRESH] [COUNCIL] [GOALS] [MORTALITY]  VECTOR READY ≈│  ← BOTTOM NAV
└──────────────────────────────────────────────────────────────────┘
```

## 4. Visual Design

### Colors
| Token | Hex | Usage |
|-------|-----|-------|
| `--bg` | `#050d1a` | Deep navy black background |
| `--cyan` | `#00d4ff` | Primary glow, active elements |
| `--blue` | `#0066ff` | Secondary electric blue |
| `--white-glow` | `rgba(255,255,255,0.1)` | Subtle accents |
| `--amber` | `#ffaa00` | Warnings, thinking state |
| `--danger` | `#ff3333` | Critical alerts |
| `--panel` | `rgba(5,15,30,0.7)` | Glass panel bg |
| `--border` | `rgba(0,212,255,0.15)` | Panel borders |

### Typography
- `'Share Tech Mono', monospace` — all text, all-caps labels with letter-spacing
- Headings use same font, slightly larger, bolder

### Effects
- **Scanline overlay**: repeating 2px horizontal lines at `rgba(0,0,0,0.15)` over entire screen
- **Glass morphism**: `backdrop-filter: blur(12px)` on all panels, semi-transparent backgrounds
- **Corner brackets**: `::before`/`::after` clip-path decorations on every panel
- **Shimmer fill**: animated gradient sweep on progress bars
- **Glow edges**: `box-shadow: 0 0 15px rgba(0,212,255,0.3)` on panels

## 5. Components

### 5.1 Top Status Bar
- Left: VECTOR logo text + pulsing white triangle icon
- Badge: green dot + "ONLINE" text
- Stats: UPTIME (simulated), AGENTS count, VERSION
- Right: Live HH:MM:SS clock updated every second

### 5.2 Left Sidebar — Telemetry
- Circular SVG gauges for MEM LOAD and CPU (animated arc)
- Text counters: AGENTS ALIVE, MEMORY (ev), SYSTEM HP
- Mode pills: FOCUS, CODER, REASONING, MULTILINGUAL — glowing colored tags
- MODELS section with status indicators
- CORE STATUS mini-panel with simulated uptime

### 5.3 Center Top — Event Feed
- Scrolling log container with fade-in entries
- Timestamps in HH:MM:SS format
- Color-coded tags: [CHAT]=cyan, [GOVE]=amber, [SYS]=white, [ERROR]=red
- Left border glow per row matching tag color
- Auto-scroll to bottom, pause on hover
- TICKER label with blinking dot

### 5.4 Center Main — Orb Visualization (Canvas)
- Central glowing white-blue orb with radial gradient
- 3 orbital rings at tilted axes (rotateX/Y/Z combos), different speeds
  - Ring 1: 8s rotation
  - Ring 2: 13s rotation (different axis)
  - Ring 3: 20s rotation (opposite tilt)
- Rings rendered as ellipses with cyan glow
- 100+ particle star-dust field drifting slowly
- Orb breathing: scale pulse 1.0 → 1.03
- Color states: idle=cyan/white, thinking=amber pulse, alert=red pulse

### 5.5 Center Bottom — System Monitor + Command
- Mini bar chart: CPU/RAM/DSK/GPU animated bars with shimmer
- Sine wave oscilloscope line (animated)
- Command input with ⚡ icon, placeholder text
- EXEC button with cyan glow

### 5.6 Right Sidebar — Districts
- Title: DISTRICTS
- Bullet list of 10 districts with clickable glowing dots
- Active district highlighted
- SYSTEM METRICS progress bars: CPU, RAM, DSK, GPU, NET

### 5.7 Bottom Nav Bar
- 6 pill buttons: AI NEWS, HN TOP, REFRESH, COUNCIL, GOALS, MORTALITY
- Cyan border on hover/active
- Status text "VECTOR READY" with animated waveform

## 6. Animations
- **Orb rings**: CSS `@keyframes` rotate3d at 8s/13s/20s
- **Orb breath**: scale 1.0 ↔ 1.03, 4s ease-in-out
- **Pulse dots**: opacity 0.3 ↔ 1.0, 2s
- **Scanlines**: static CSS repeating gradient
- **Bar shimmer**: gradient sweep 3s infinite
- **Sine wave**: Canvas 2D with phase shift per frame
- **Event entries**: fadeIn + slideUp on DOM insert
- **Glow hover**: transition 0.3s on all interactive elements
- **Particle field**: requestAnimationFrame, slow random drift

## 7. State & Data Simulation
- All data is simulated client-side (no backend required)
- Event feed generates random entries on interval
- CPU/MEM/DISK/GPU values oscillate randomly
- Clock, uptime, agent count update via setInterval
- Command input is cosmetic placeholder

## 8. Output
- Single file: `core/ui/dashboard/index.html`
