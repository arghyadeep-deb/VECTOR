# Center Cognition Core — Design

**Files to edit:** ArcReactor.tsx, CentralHologram.tsx, styles.css, zIndex.ts

## Visual Architecture (bottom to top)

### Layer 1 — Deep space field (background)
- Hundreds of tiny slowly-drifting star particles on a full-viewport canvas
- Replace the static CSS grid dot pattern with animated drifting stars
- File: Decorations.tsx or new BackgroundCanvas.tsx

### Layer 2 — Orbital rings (SVG + CSS 3D)
- 4-5 elliptical orbital trajectories at different angles/tilts
- Rings pulse brighter during processing (via AmbientTheme mood)
- Replace current DecorativeRing + CentralHologram rings
- File: CentralHologram.tsx → rewrite completely

### Layer 3 — Cognition orb (center focal point)
- Large glowing sphere with layered radial gradients
- Inner core pulsing with breathing animation
- Outer corona with subtle rotation
- Glow intensity driven by processing state (IDLE=soft cyan, PROCESSING=bright teal, ERROR=red pulse)
- File: ArcReactor.tsx → strip to core orb, move radar/particles elsewhere

### Layer 4 — Neural pathways / reasoning lines
- SVG lines radiating from center orb outward, branching like neuron paths
- Lines animate during processing (grow, pulse)
- Static when idle (just visible traces)
- 8-12 pathways total
- File: new NeuralPathways.tsx or add to ArcReactor

### Layer 5 — Agent communication traces
- Thin curved arcs between center orb and left/right sidebar regions
- Represent agent ↔ core communication
- Soft glow, slow orbit animation
- File: new CommunicationTraces.tsx or add to ArcReactor

### Layer 6 — Ambient glow overlay (already exists)
- Current AmbientTheme.tsx works well
- Connect it to core orb glow intensity for adaptive brightness

## Interaction States
- **IDLE:** Soft cyan breathing orb, slow ring rotation, dim pathways
- **PROCESSING:** Bright teal orb, rings accelerate, pathways pulse, particles speed up
- **ERROR/CRITICAL:** Red shift on orb, subtle glitch on rings
- **COUNCIL:** Purple tint on orb glow

## Data Integration
- Orb brightness/color driven by `AmbientTheme` mood (already set via CSS vars)
- Processing intensity from `goals.immediate_actions.length`
- Alert level from recent event types

**Rough layout:**
```
                  ┌─────────────────────────────────────┐
                  │     Star field (full bg canvas)     │
                  │  ┌───────────────────────────────┐  │
                  │  │  Orbital rings (angled ellipses)│  │
                  │  │  ┌─────────────────────────┐  │  │
                  │  │  │  Neural pathways (SVG)  │  │  │
                  │  │  │   ┌─────────────────┐   │  │  │
                  │  │  │   │   Cognition orb   │   │  │  │
                  │  │  │   │  (layered glow)   │   │  │  │
                  │  │  │   └─────────────────┘   │  │  │
                  │  │  └─────────────────────────┘  │  │
                  │  └───────────────────────────────┘  │
                  │     Agent comm traces (side arcs)    │
                  └─────────────────────────────────────┘
```

This design uses ~6 layers stacked with increasing z-index. Each layer is a separate component. This is cleaner than the current 224-line ArcReactor monolith.
