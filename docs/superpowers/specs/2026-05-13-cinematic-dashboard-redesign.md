# Cinematic Dashboard Redesign — VECTOR AGI Command Center

## Scope
Full redesign of the VECTOR dashboard (`core/ui/dashboard/`) into a cinematic JARVIS-like AGI operating system interface. Covers all components: TelemetryPanel, DistrictsPanel, centerpiece core, command input, event feed, and HUD elements.

## Layout

```
┌─────────────────────────────────────────────────────┐
│  TOP BAR: "VECTOR" | status | uptime | clock        │
├────────┬─────────────────────────────┬───────────────┤
│        │                             │               │
│ TELE-  │    CENTERPIECE              │  DISTRICTS    │
│ METRY  │    • AGI core orb           │  • coding     │
│ PANEL  │    • orbital rings          │  • finance    │
│        │    • neural pathways        │  • governance │
│ • CPU  │    • particle field         │  • health     │
│ • GPU  │    • comm traces            │  • mem_curator│
│ • RAM  │    • holographic layers     │  • projects   │
│ • VRAM │                             │  • reflection │
│ • mem  │                             │  • research   │
│ • HP   │                             │  • security   │
│ • conf │                             │  • time_cal   │
│ • depth│                             │               │
│ • radar│                             │               │
│ • up   │                             │               │
│ • refl │                             │               │
├────────┴─────────────────────────────┴───────────────┤
│  EVENT FEED (scrolling logs) │  COMMAND TERMINAL      │
│  [DEC][GOV][WARN] colored     │  "Type command..."    │
│  tags + timestamps            │  EXEC btn + waveform  │
└─────────────────────────────────────────────────────┘
```

## Component Details

### TelemetryPanel (left)
- Width: ~220px, fixed left
- Glass-panel background with cyan border glow
- Sections (stacked vertically):
  1. **CPU/GPU/RAM/VRAM** — 4 circular SVG ring gauges (46px), glow on arc
  2. **Memory pressure** — horizontal bar
  3. **Hallucination risk** — horizontal bar  
  4. **Confidence** — horizontal bar
  5. **Reasoning depth** — numeric counter
  6. **Agent health** — alive count, avg HP, at-risk count
  7. **System HP** — large scrambler number
  8. **Heading radar** — compass canvas (retained from CornerHUD)
  9. **Uptime** — formatted duration
  10. **Reflect cycles** — counter
- All labels: Orbitron 7-8px, uppercase
- Values: JetBrains Mono 8-10px, cyan
- Pulse dot online indicator

### DistrictsPanel (right)
- Width: ~200px, fixed right
- Glass-panel with border-left glow
- Header: "DISTRICTS" + count
- Each district entry:
  - Cyan pulse dot (3px, animated v-pulse)
  - District name (Orbitron 8px)
  - Thin 1px separator between entries
  - Hover: text glow + brighten
- Ordered list: coding, finance, governance, health, memory_curator, projects, reflection, research, security, time_calendar
- Footer showing total alive agents

### Centerpiece (ArcReactor + CentralHologram + NeuralPathways + CommunicationTraces)
- Keep existing components, enhance:
  - Brighter white core nucleus
  - More orbital trails (dashoffset animation)
  - Faster rotation during processing
  - Neural lines glow brighter on activity
  - Star field drifts continuously

### CommandInput (bottom center)
- Keep current streaming typewriter response
- Keep task timeline bar
- Keep waveform pulse indicator
- Keep EXEC button

### Event Feed (bottom left)
- CompactEventFeed: keep as-is (scrolling colored tags)

### Background
- `#030a14` (deep blue-black)
- Fine grid overlay via CSS on root
- Faint scanline effect

## Visual Style
- Colors: `#00d4ff` (cyan), `#0066ff` (electric blue), `#030a14` (bg), `#0a1628` (panel bg)
- Typography: Orbitron (labels/headers), JetBrains Mono (values/data)
- Glow: `box-shadow` with cyan, `drop-shadow` on SVG arcs
- Panels: `rgba(5,13,26,0.88)` with `backdrop-filter: blur(12px)`
- Borders: `rgba(0,212,255,0.08)` subtle cyan
- Active indicators: `v-pulse` animation

## Files to Modify
- `src/components/TelemetryPanel.tsx` — full redesign
- `src/components/DistrictsPanel.tsx` — full redesign
- `src/styles.css` — add scanlines, grid overlay
- `src/App.tsx` — layout adjustments if needed
- `src/components/CornerHUD.tsx` — integrate heading radar into TelemetryPanel
- Other components: minimal adjustments

## Files to Create
- None (edit in-place)

## Files to Delete
- None (already cleaned up: LowerHUD, SystemHeat, DonutRing, ArcGauge deleted)
