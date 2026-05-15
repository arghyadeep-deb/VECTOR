# VECTOR Holographic HUD Dashboard — Design Spec

## 1. Purpose
Replace the existing Next.js multi-page dashboard with a single, immersive **pilot-AR-helmet-style HUD** served by FastAPI. The 3D holographic scene acts as the background, with floating glass-morphism panels overlaid with system telemetry, live event feed, command input, and district overview.

## 2. Architecture

### Frontend
- **Vite + React 18 + TypeScript**
- **@react-three/fiber + @react-three/drei** for the 3D holographic scene
- **Zustand** for state management (migrated from old dashboard)
- **Zero routing** — single-page, all panels overlay the 3D canvas
- **Build output**: `core/ui/dashboard/dist/` served as static files by FastAPI

### Backend
- **FastAPI** serves the built dashboard at `GET /`
- API endpoints remain at `/api/*` (already exist)
- WebSocket at `/ws` for live events

### File Structure (new)
```
core/ui/dashboard/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── styles.css
    ├── components/
    │   ├── HUD.tsx              ← Main HUD layout (assembles all panels)
    │   ├── TopBar.tsx           ← Logo, status badges, clock, data stream text
    │   ├── TelemetryPanel.tsx   ← System stats (left column)
    │   ├── EventFeed.tsx        ← Live memory feed (center)
    │   ├── CommandInput.tsx     ← Holographic command input
    │   ├── DistrictsPanel.tsx   ← District list (right column)
    │   └── QuickActions.tsx     ← Bottom action buttons
    ├── three/
    │   └── VectorScene.tsx      ← 3D holographic scene (core, rings, nodes, particles, radar sweep)
    ├── store/
    │   └── vectorStore.ts       ← Zustand store
    └── lib/
        └── api.ts              ← API client + WebSocket
```

## 3. Visual Design

### Layout (single screen, no scrolling)
```
┌──────────────────────────────────────────────────────────────┐
│ V.E.C.T.O.R  ● ONLINE   │ UPTIME 4h 12m  │ AGENTS 24 │ 14:32│  ← TopBar
├──────┬───────────────────────────────────────────┬───────────┤
│      │                                           │           │
│ SYS  │   3D Holographic Scene (full background)   │ DISTRICTS │
│ TEMP │                                           │           │
│ CPU  │  ┌──────────────────────────────────┐     │ ● govern  │
│ MEM  │  │  LIVE FEED                       │     │ ● coding  │
│ FAT  │  │  [14:30] Council decision stored  │     │ ● secur   │
│      │  │  [14:28] Agent GitBot HP +30      │     │ ● memory  │
│ HP   │  │  [14:25] Morning brief generated  │     │ ● ...     │
│      │  └──────────────────────────────────┘     │           │
│      │                                           │           │
│      │  ┌──────────────────────────────────┐     │           │
│      │  │ ⚡ COMMAND                        │     │           │
│      │  │ ┌─────────────────────────┐ ▶ │     │           │
│      │  │ │ Type a command for VECTOR│   │     │           │
│      │  │ └─────────────────────────┘   │     │           │
│      │  └──────────────────────────────────┘     │           │
├──────┴───────────────────────────────────────────┴───────────┤
│  QUICK: [AI News] [HN Top] [Council] [Goals] [Refresh]       │  ← QuickActions
└──────────────────────────────────────────────────────────────┘
```

### Color Palette
| Token | Hex | Usage |
|-------|-----|-------|
| `--bg` | `#050a0a` | Deep background |
| `--cyan` | `#00ffff` | Primary glow, active elements |
| `--cyan-dim` | `#00aaaa` | Secondary text, inactive borders |
| `--amber` | `#ffbb00` | Warnings, medium priority |
| `--red` | `#ff3355` | Alerts, critical |
| `--blue` | `#4488ff` | Info accents |
| `--panel` | `rgba(5,15,25,0.75)` | Glass panel background |
| `--border` | `rgba(0,255,255,0.15)` | Panel borders |
| `--text` | `#c8e6e5` | Primary text |
| `--dim` | `#5a8a8a` | Secondary/label text |

### Typography
- **Data/monospace**: `"JetBrains Mono", monospace` — all telemetry, feeds, labels
- **Headings**: `"Space Grotesk", sans-serif` — VECTOR logo, section headers
- Sizes range from 9px (labels) to 28px (logo)

## 4. Components

### 4.1 3D Holographic Scene (`VectorScene.tsx`)
- **Core sphere**: Metallic/emissive cyan sphere with breathing pulse animation
- **Orbital rings**: 4-6 rotating rings at varying radii/tilts/speeds (cyan, amber, blue, purple)
- **Data nodes**: Floating octahedrons orbiting at ring intersections, pulsing with glow
- **Particle field**: 800+ particles forming a starfield, slowly rotating
- **Radar sweep**: A radial line sweeping clockwise across the scene with a gradient tail
- **Connection lines**: Thin lines between nearby nodes
- **Camera**: Auto-rotates slowly, user can drag to orbit (OrbitControls)

### 4.2 TopBar
- Left: VECTOR logo with animated pulsing status dot
- Center-right: Status badges (ONLINE/OFFLINE, UPTIME, AGENT COUNT)
- Far right: Live clock (24h format, seconds ticking)
- Subtle scrolling hexadecimal/data stream text as a background effect

### 4.3 TelemetryPanel (left, ~200px wide)
- CPU Usage (progress bar)
- Memory Usage (progress bar)  
- Fatigue Score (numerical with color coding)
- System HP (large number + progress bar)
- Active goals count
- All labels in monospace, values cyan

### 4.4 EventFeed (center, flexible)
- Scrollable list of recent episodic memory events
- Each entry: timestamp + event type badge + truncated content
- Auto-scrolls to bottom on new events
- Polls every 5s (or WebSocket push)

### 4.5 CommandInput (below EventFeed)
- Single-line input with holographic styling (cyan underline focus, transparent bg)
- Send button with ▶ icon
- Sends to `/ui/chat` or `/ws`
- Response appears as a feed entry

### 4.6 DistrictsPanel (right, ~200px wide)
- List of all 25 districts with green/cyan dots
- Shows agent count per district
- Hover to see active/inactive status

### 4.7 QuickActions (bottom bar)
- Row of 5-6 buttons: AI News, HN Top, Convene Council, Refresh Goals, Recent Memory
- Styled as cyan-bordered chips with hover glow

## 5. Animations
- **Panel entrance**: fadeIn + subtle translateY (0.4s ease)
- **Pulse**: status dots and active elements (2s cycle)
- **Radar sweep**: 4s rotation
- **Data stream**: scrolling hex text (20s scroll)
- **Hover glow**: panels get increased border opacity + shadow
- **Loading**: blinking text for placeholder states

## 6. Backend Changes
- `core/main.py`: serve `core/ui/dashboard/dist/index.html` at `GET /` and all sub-routes (SPA fallback)
- Static files served from `core/ui/dashboard/dist/`
- No new API routes needed — reuse existing `/status`, `/ui/*` endpoints

## 7. Cleanup
- **DELETE** entire `dashboard/` directory (old Next.js project)
- **REMOVE** any references to `dashboard/` in scripts, workflows, or configs
- **KEEP** `core/ui/web_ui.py` and `core/ui/chat.py` unchanged

## 8. Build & Dev
```bash
# Dev (hot reload)
cd core/ui/dashboard && npm run dev  # starts on :5173
# FastAPI runs on :8000, dashboard proxies API calls

# Production
cd core/ui/dashboard && npm run build  # outputs to dist/
# FastAPI serves from dist/
```
