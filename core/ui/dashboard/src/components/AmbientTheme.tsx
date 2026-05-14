import { useEffect, useRef } from 'react'
import { useVectorStore } from '../store/vectorStore'

const MOODS = {
  IDLE:        { accent: '#00d4ff', glow: 'rgba(0,212,255,0.08)', border: 'rgba(0,212,255,0.25)', grid: 'rgba(0,51,102,0.06)' },
  PROCESSING:  { accent: '#00FFD4', glow: 'rgba(0,255,212,0.15)', border: 'rgba(0,255,212,0.30)', grid: 'rgba(0,80,70,0.08)' },
  ERROR:       { accent: '#FF3D3D', glow: 'rgba(255,61,61,0.18)', border: 'rgba(255,61,61,0.35)', grid: 'rgba(80,10,10,0.10)' },
  COUNCIL:     { accent: '#BF5FFF', glow: 'rgba(191,95,255,0.10)', border: 'rgba(191,95,255,0.25)', grid: 'rgba(60,10,80,0.08)' },
  CRITICAL:    { accent: '#FF0000', glow: 'rgba(255,0,0,0.20)', border: 'rgba(255,0,0,0.40)', grid: 'rgba(80,0,0,0.12)' },
} as const

type Mood = keyof typeof MOODS

function computeMood(
  events: { event_type: string }[],
  goals: { immediate_actions: Record<string, unknown>[] } | null,
  loopRunning: boolean,
): Mood {
  if (!loopRunning) return 'ERROR'

  const topEvent = events[0]
  if (topEvent) {
    const t = topEvent.event_type.toLowerCase()
    if (t.includes('error') || t.includes('warn')) return 'ERROR'
    if (t.includes('critical') || t.includes('die') || t.includes('kill')) return 'CRITICAL'
    if (t.includes('gov') || t.includes('council')) return 'COUNCIL'
  }

  const hasActiveWork = (goals?.immediate_actions?.length ?? 0) > 0
  if (hasActiveWork) return 'PROCESSING'

  return 'IDLE'
}

export default function AmbientTheme() {
  const events = useVectorStore((s) => s.events)
  const goals = useVectorStore((s) => s.goals)
  const status = useVectorStore((s) => s.status)
  const loopRunning = status?.loop_running ?? true
  const overlayRef = useRef<HTMLDivElement>(null)
  const settledRef = useRef(false)

  useEffect(() => {
    if (status) settledRef.current = true
    if (!settledRef.current) return

    const mood = computeMood(events, goals, loopRunning)
    const isIdle = mood === 'IDLE'

    if (overlayRef.current) {
      overlayRef.current.style.transition = isIdle ? 'background 0s ease' : 'background 0.8s ease'
    }

    const m = MOODS[mood]
    const root = document.documentElement
    root.style.setProperty('--theme-accent', m.accent)
    root.style.setProperty('--theme-glow', m.glow)
    root.style.setProperty('--theme-border', m.border)
    root.style.setProperty('--theme-grid', m.grid)
    if (overlayRef.current) {
      overlayRef.current.style.background = `radial-gradient(ellipse at 50% 50%, transparent 50%, ${m.accent}22 100%)`
    }
  }, [events, goals, loopRunning, status])

  return (
    <div
      ref={overlayRef}
      style={{
        position: 'fixed', inset: 0, zIndex: 99998, pointerEvents: 'none',
        background: 'radial-gradient(ellipse at 50% 50%, transparent 50%, rgba(0,212,255,0.08) 100%)',
        transition: 'background 0.8s ease',
      }}
    />
  )
}