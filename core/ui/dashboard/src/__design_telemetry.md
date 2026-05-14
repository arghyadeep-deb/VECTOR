# Left Telemetry Panel — Design

**Files to edit:** TelemetryPanel.tsx, SystemHeat.tsx, CornerHUD.tsx, LowerHUD.tsx, CoreStatusPanel.tsx

## Consolidation strategy
Merge scattered telemetry data into ONE cohesive panel:

### New TelemetryPanel (left: 16, top: 56, width: 200)
```
┌──────────────────────┐
│ TELEMETRY      ONLINE │  ← header
├──────────────────────┤
│ ┌──────┐ ┌──────┐   │
│ │ CPU  │ │ GPU  │   │  ← arc gauges (moved from SystemHeat)
│ │  42% │ │  67% │   │
│ └──────┘ └──────┘   │
│ ┌──────┐ ┌──────┐   │
│ │ RAM  │ │ VRAM │   │  ← new VRAM gauge
│ │ 6.2G │ │ 4.1G │   │
│ └──────┘ └──────┘   │
├──────────────────────┤
│ Mem Pressure    ▓▓░░ │  ← bar
│ Hallucination   ░░░░ │  ← low risk bar
│ Confidence      ▓▓▓░ │  ← alignment bar
│ Reasoning Depth   12 │  ← counter
├──────────────────────┤
│ AGENT HEALTH        │
│ ● Alive: 14/18      │
│ ● Avg HP: 523       │
│ ● At Risk: 2        │
└──────────────────────┘
```

### Removed/repositioned
- **SystemHeat.tsx** → DELETE (merged into TelemetryPanel as CPU/GPU gauges)
- **CornerHUD compass** → KEEP at same position (aesthetic, no data replacement)
- **CornerHUD MetricBars** → DELETE (redundant — CPU/RAM/DSK/GPU/NET already in TelemetryPanel)
- **LowerHUD.tsx** → DELETE (EKG + MiniRadar replaced by TelemetryPanel's live log)
- **CoreStatusPanel.tsx** → KEEP (draggable, unique data)
