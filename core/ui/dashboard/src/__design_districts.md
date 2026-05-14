# Right Districts Panel — Design

**Files to edit:** DistrictsPanel.tsx, styles.css

## Current → Target
Current: simple list with colored dots, width 185px
Target: modular expandable cards, width 200px

## Layout
```
┌──────────────────────┐
│ DISTRICTS        [12] │  ← header with count
├──────────────────────┤
│ ● Coding         ▓▓░░ │  ← activity bar (live pulse)
│   Last: 3m ago        │
├──────────────────────┤
│ ● Research       ▓░░░ │
│   Last: 12m ago       │
├──────────────────────┤
│ ● Finance        ▓▓▓░ │  ← fuller bar = more active
│   Last: 30s ago       │
├──────────────────────┤
│ ... more districts    │
└──────────────────────┘
```

- **Width:** 185 → 200px (slightly wider)
- **Each district:** Name + thin activity bar + "Last active" timestamp
- **Activity bar:** fluctuates based on agent HP sum in that district (more HP = fuller bar)
- **Color dot:** cyan if alive agents, grey if none, flashing if critical HP
- **No expandable cards** (YAGNI for now — keeps it clean)
- **Hover effect:** subtle brightness increase, no click action (preserves existing click→openPanel)
