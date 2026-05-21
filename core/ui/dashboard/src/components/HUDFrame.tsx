import { useEffect, useState } from 'react'
import { useVectorStore } from '../store/vectorStore'

const CYAN = 'rgba(0,212,255,'

export default function HUDFrame() {
  const [time, setTime] = useState('')
  const status = useVectorStore((s) => s.status)
  const connected = useVectorStore((s) => s.connected)
  const voiceState = useVectorStore((s) => s.voiceState)

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setTime(now.toTimeString().slice(0, 8))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  const dots = [
    { label: 'LOOP',   active: status?.loop_running ?? false },
    { label: 'OLLAMA', active: !!(status?.models && Object.keys(status.models).length > 0) },
    { label: 'MEM',    active: !!(status?.memory && Object.keys(status.memory).length > 0) },
    { label: 'GATE',   active: connected },
    { label: 'VCTR',   active: connected },
  ]

  const isListening = voiceState === 'listening'
  const bracketBorderColor = isListening ? '#00CFFF' : `${CYAN}0.2)`
  const bracketScale = isListening ? 'scale(1.18)' : 'scale(1)'
  const bracketTransition = 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)'

  return (
    <>
      {/* Fullscreen Input Boundary Glow Overlay */}
      <div className={`listening-boundary-glow ${isListening ? 'active' : ''}`} />

      {/* Top center bracket ⊓ */}
      <div style={{
        position: 'fixed', top: 0, left: '50%', transform: 'translateX(-50%)',
        zIndex: 200, pointerEvents: 'none',
      }}>
        <svg width={120} height={20}>
          <line x1={10} y1={2} x2={110} y2={2} stroke={`${CYAN}0.4)`} strokeWidth={1} />
          <line x1={10} y1={2} x2={10} y2={20} stroke={`${CYAN}0.4)`} strokeWidth={1} />
          <line x1={110} y1={2} x2={110} y2={20} stroke={`${CYAN}0.4)`} strokeWidth={1} />
        </svg>
      </div>

      {/* Top-left corner bracket */}
      <div style={{
        position: 'fixed', top: 8, left: 8, width: 24, height: 24,
        borderTop: `1.5px solid ${bracketBorderColor}`, borderLeft: `1.5px solid ${bracketBorderColor}`,
        boxShadow: isListening ? `inset 2px 2px 8px rgba(0, 207, 255, 0.25)` : 'none',
        transform: bracketScale,
        transition: bracketTransition,
        zIndex: 200, pointerEvents: 'none',
      }} />

      {/* Top-right corner bracket */}
      <div style={{
        position: 'fixed', top: 8, right: 8, width: 24, height: 24,
        borderTop: `1.5px solid ${bracketBorderColor}`, borderRight: `1.5px solid ${bracketBorderColor}`,
        boxShadow: isListening ? `inset -2px 2px 8px rgba(0, 207, 255, 0.25)` : 'none',
        transform: bracketScale,
        transition: bracketTransition,
        zIndex: 200, pointerEvents: 'none',
      }} />

      {/* Bottom-left corner bracket */}
      <div style={{
        position: 'fixed', bottom: 60, left: 8, width: 24, height: 24,
        borderBottom: `1.5px solid ${bracketBorderColor}`, borderLeft: `1.5px solid ${bracketBorderColor}`,
        boxShadow: isListening ? `inset 2px -2px 8px rgba(0, 207, 255, 0.25)` : 'none',
        transform: bracketScale,
        transition: bracketTransition,
        zIndex: 200, pointerEvents: 'none',
      }} />

      {/* Bottom-right corner bracket */}
      <div style={{
        position: 'fixed', bottom: 60, right: 8, width: 24, height: 24,
        borderBottom: `1.5px solid ${bracketBorderColor}`, borderRight: `1.5px solid ${bracketBorderColor}`,
        boxShadow: isListening ? `inset -2px -2px 8px rgba(0, 207, 255, 0.25)` : 'none',
        transform: bracketScale,
        transition: bracketTransition,
        zIndex: 200, pointerEvents: 'none',
      }} />

      {/* Bottom mode dots */}
      <div style={{
        position: 'fixed', bottom: 64, left: '50%', transform: 'translateX(-50%)',
        display: 'flex', alignItems: 'center', gap: 8,
        zIndex: 200, pointerEvents: 'none',
      }}>
        {dots.map(({ label, active }) => (
          <div key={label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
            <div style={{
              width: 5, height: 5, borderRadius: '50%',
              background: active ? '#00CFFF' : `${CYAN}0.15)`,
              boxShadow: active ? '0 0 6px #00CFFF' : 'none',
              transition: 'all 0.3s ease',
            }} />
            <span style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 6,
              color: `${CYAN}0.35)`,
              letterSpacing: '0.08em',
            }}>
              {label}
            </span>
          </div>
        ))}
      </div>

      {/* Bottom-right V.E.C.T.O.R timestamp */}
      <div style={{
        position: 'fixed', bottom: 8, right: 16,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 7.5, color: `${CYAN}0.22)`,
        letterSpacing: '0.1em',
        zIndex: 200, pointerEvents: 'none',
      }}>
        V.E.C.T.O.R • {time}
      </div>

      {/* Bottom-left AUTONOMOUS label */}
      <div style={{
        position: 'fixed', bottom: 8, left: 16,
        fontFamily: "'Orbitron', sans-serif",
        fontSize: 7, color: `${CYAN}0.15)`,
        letterSpacing: '0.3em',
        zIndex: 200, pointerEvents: 'none',
      }}>
        AUTONOMOUS
      </div>
    </>
  )
}
