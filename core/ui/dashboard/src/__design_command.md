# Bottom Command Interface — Design

**Files to edit:** CommandInput.tsx, QuickActions.tsx, VoiceWaveform.tsx

## Layout (bottom bar, full width)

```
┌────────────────────────────────────────────────────────┐
│  ⚡ [type a command for VECTOR...]        [EXEC]       │  ← command row (height: 40px)
│  ┌──────────────── response area ──────────────────┐  │
│  │  VECTOR: Processing request...                  │  │  ← streaming area (max-height: 200px)
│  │  ⟳ Analyzing cognitive pathways...              │  │
│  │  ✓ Task complete. Confidence: 94%               │  │
│  └─────────────────────────────────────────────────┘  │
│  ┌─── next actions ───────────────────────────────┐  │
│  │  [Analyze] [Research] [Write] [Plan] [Monitor] │  │  ← suggested next actions
│  └────────────────────────────────────────────────┘  │
│  ┌─── task timeline ───────────────────────────────┐  │
│  │  ■■■■■■■□□□□□ 65%  ●──●──●──○  eta: 12s       │  │
│  └────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────┤
│  [AI NEWS] [HN TOP] [REFRESH] [COUNCIL] [GOALS]       │  ← QuickActions bar (height: 32px)
└────────────────────────────────────────────────────────┘
```

## Changes

### CommandInput.tsx
- **Visual refresh:** Dark glass input, cyan focus glow, larger font
- **Response area:** Streaming text with typewriter reveal, VECTOR prefix in cyan
- **Suggested next-actions row:** Below response during processing (Analyze, Research, etc.)
- **Task timeline bar:** Small progress bar below response showing completion %

### QuickActions.tsx
- **Tighter:** Reduce height from 36px → 32px, compact pill buttons
- **Homogeneous styling:** All buttons same style (currently mortality is highlighted)
- **Remove voice waveform:** VoiceWaveform.tsx becomes part of command input instead of floating below

### VoiceWaveform.tsx
- **Reposition:** Move inside CommandInput, show only during streaming responses
- **Same animation:** 40 vertical bars, but only visible when executing

## Data Integration
- Task timeline % from `goals.immediate_actions.length` (more actions = more progress)
- Suggested actions from `goals.immediate_actions` titles
- Streaming state from `websocket.ts` (already connected)
