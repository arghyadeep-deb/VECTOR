import { useEffect, useRef, useState } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { api } from '../lib/api'

// ── Scrolling system log ────────────────────────────────────────────────────
function DiagnosticsPanel() {
  const [lines, setLines] = useState<string[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const seed = [
      'VECTOR CORE: NOMINAL',
      'DECISION ENGINE: ACTIVE',
      'PERMISSION GATEWAY: STANDBY',
      'CONTEXT ENGINE: SYNCHRONIZED',
      'EPISODIC MEMORY: 12,720 EVENTS',
      'POLICY MEMORY: 449 PATTERNS',
      'AUTONOMOUS LOOP: RUNNING',
      'NUDGE ENGINE: 30s INTERVAL',
      'OLLAMA: CONNECTED',
      'SYSTEM LOAD: NOMINAL',
    ]
    setLines(seed)
  }, [])

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const s = await api.status()
        const agent_count = s.agents?.count ?? '—'
        const uptime = s.uptime_seconds ?? 0
        const h = Math.floor(uptime / 3600)
        const m = Math.floor((uptime % 3600) / 60)
        const newLine = `UPTIME: ${h}h ${m}m | AGENTS: ${agent_count} | LOOP: ${s.loop_running ? 'ACTIVE' : 'STANDBY'}`
        setLines(prev => [...prev.slice(-60), newLine])
      } catch {
        setLines(prev => [...prev.slice(-60), `PING: ${new Date().toLocaleTimeString()}`])
      }
    }, 4000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  return (
    <div style={{
      height: '100%', overflow: 'hidden',
      fontFamily: "'JetBrains Mono', monospace", fontSize: 9,
      color: 'rgba(0,207,255,0.7)', lineHeight: 1.6,
      display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
    }}>
      <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#00CFFF', letterSpacing: '0.2em', marginBottom: 6 }}>
        SYSTEM DIAGNOSTICS
      </div>
      <div style={{ overflowY: 'auto', flex: 1 }}>
        {lines.map((l, i) => (
          <div key={i} style={{ color: i === lines.length - 1 ? '#00FFFF' : 'rgba(0,207,255,0.55)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            <span style={{ color: 'rgba(0,207,255,0.3)', marginRight: 6 }}>›</span>{l}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Agent node cards ────────────────────────────────────────────────────────
function AgentNodes() {
  const agents = useVectorStore((s) => s.agents)
  const top5 = [...agents].sort((a, b) => b.health_points - a.health_points).slice(0, 5)
  const critical = [...agents].filter(a => a.health_points < 200).slice(0, 3)

  const hpColor = (hp: number) => hp >= 700 ? '#00FF88' : hp >= 400 ? '#FFAA00' : '#FF4444'

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#00CFFF', letterSpacing: '0.2em', marginBottom: 4 }}>
        NODE STATUS
      </div>
      {top5.map((a, i) => (
        <div key={a.id} style={{
          background: 'rgba(0,207,255,0.04)',
          border: '1px solid rgba(0,207,255,0.12)',
          padding: '5px 8px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#00CFFF', letterSpacing: '0.1em' }}>
              NODE-{String(i + 1).padStart(2, '0')}
            </span>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: hpColor(a.health_points) }}>
              {a.health_points} HP
            </span>
          </div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 7, color: 'rgba(0,207,255,0.5)', marginBottom: 3 }}>
            {a.name?.toUpperCase()} · {a.district?.toUpperCase()}
          </div>
          {/* HP bar */}
          <div style={{ height: 2, background: 'rgba(0,207,255,0.1)', borderRadius: 1 }}>
            <div style={{ width: `${(a.health_points / 1000) * 100}%`, height: '100%', background: hpColor(a.health_points), borderRadius: 1, transition: 'width 1s ease' }} />
          </div>
        </div>
      ))}
      {critical.length > 0 && (
        <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#FF4444', letterSpacing: '0.1em', marginTop: 4 }}>
          ⚠ {critical.length} CRITICAL
        </div>
      )}
    </div>
  )
}

// ── Rotating gear hologram (CSS, no three.js dependency) ────────────────────
function GearHologram() {
  const status = useVectorStore((s) => s.status)
  const agents = useVectorStore((s) => s.agents)

  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      position: 'relative',
    }}>
      {/* Outer rotating ring */}
      <div style={{
        position: 'absolute',
        width: 280, height: 280,
        border: '1px solid rgba(0,207,255,0.15)',
        borderRadius: '50%',
        animation: 'gearSpin 20s linear infinite',
      }} />
      <div style={{
        position: 'absolute',
        width: 240, height: 240,
        border: '1px solid rgba(0,207,255,0.1)',
        borderRadius: '50%',
        animation: 'gearSpin 15s linear infinite reverse',
      }} />
      <div style={{
        position: 'absolute',
        width: 200, height: 200,
        border: '2px solid rgba(0,207,255,0.25)',
        borderRadius: '50%',
        animation: 'gearSpin 10s linear infinite',
      }} />

      {/* Gear teeth effect using dashed border */}
      <div style={{
        position: 'absolute',
        width: 200, height: 200,
        border: '8px dashed rgba(0,207,255,0.12)',
        borderRadius: '50%',
        animation: 'gearSpin 8s linear infinite reverse',
      }} />

      {/* Inner core glow */}
      <div style={{
        position: 'absolute',
        width: 120, height: 120,
        background: 'radial-gradient(circle, rgba(0,207,255,0.15) 0%, rgba(0,207,255,0.05) 50%, transparent 70%)',
        borderRadius: '50%',
        animation: 'gearPulse 3s ease-in-out infinite',
      }} />

      {/* Tick marks on outer ring */}
      {Array.from({ length: 24 }).map((_, i) => {
        const angle = (i * 15 * Math.PI) / 180
        const r = 148
        const x = 150 + r * Math.cos(angle - Math.PI / 2)
        const y = 150 + r * Math.sin(angle - Math.PI / 2)
        return (
          <div key={i} style={{
            position: 'absolute',
            left: x - 1, top: y - 1,
            width: i % 6 === 0 ? 3 : 1.5,
            height: i % 6 === 0 ? 3 : 1.5,
            background: i % 6 === 0 ? '#00CFFF' : 'rgba(0,207,255,0.4)',
            borderRadius: '50%',
          }} />
        )
      })}

      {/* Center label */}
      <div style={{ textAlign: 'center', position: 'relative', zIndex: 2 }}>
        <div style={{
          fontFamily: "'Orbitron', sans-serif",
          fontSize: 14, fontWeight: 700,
          color: '#ffffff',
          letterSpacing: '0.25em',
          textShadow: '0 0 20px rgba(0,207,255,0.9)',
        }}>
          VECTOR
        </div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 9,
          color: 'rgba(0,207,255,0.6)', letterSpacing: '0.12em', marginTop: 4,
        }}>
          {agents.length} AGENTS ACTIVE
        </div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 8,
          color: status?.loop_running ? 'rgba(0,255,136,0.7)' : 'rgba(255,68,68,0.7)',
          letterSpacing: '0.12em', marginTop: 2,
        }}>
          {status?.loop_running ? 'LOOP: NOMINAL' : 'LOOP: STANDBY'}
        </div>
      </div>

      <style>{`
        @keyframes gearSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes gearPulse { 0%,100% { opacity: 0.6; transform: scale(1); } 50% { opacity: 1; transform: scale(1.08); } }
      `}</style>
    </div>
  )
}

// ── Main FORTRESS MODE ──────────────────────────────────────────────────────
export default function FortressMode() {
  const setMode = useVectorStore((s) => s.setMode)
  const status = useVectorStore((s) => s.status)
  const agents = useVectorStore((s) => s.agents)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)))
  }, [])

  const exit = () => {
    setVisible(false)
    setTimeout(() => setMode('JARVIS_MODE'), 500)
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: '#000',
      opacity: visible ? 1 : 0,
      transition: 'opacity 0.5s ease',
      display: 'flex', flexDirection: 'column',
      fontFamily: "'Orbitron', sans-serif",
    }}>
      {/* Background network nodes */}
      <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', opacity: 0.08 }}>
        {Array.from({ length: 20 }).map((_, i) => {
          const x1 = Math.sin(i * 1.3) * 50 + 50
          const y1 = Math.cos(i * 0.9) * 50 + 50
          const x2 = Math.sin((i + 3) * 0.7) * 50 + 50
          const y2 = Math.cos((i + 5) * 1.1) * 50 + 50
          return <line key={i} x1={`${x1}%`} y1={`${y1}%`} x2={`${x2}%`} y2={`${y2}%`} stroke="#00CFFF" strokeWidth="0.5" />
        })}
        {Array.from({ length: 12 }).map((_, i) => {
          const x = Math.sin(i * 1.7) * 45 + 50
          const y = Math.cos(i * 1.3) * 45 + 50
          return <circle key={i} cx={`${x}%`} cy={`${y}%`} r="3" fill="#00CFFF" opacity="0.6" />
        })}
      </svg>

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 20px',
        borderBottom: '1px solid rgba(0,207,255,0.15)',
        background: 'rgba(0,207,255,0.03)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 11, color: '#00CFFF', letterSpacing: '0.3em' }}>VECTOR</span>
          <span style={{ fontSize: 8, color: 'rgba(0,207,255,0.4)', letterSpacing: '0.15em' }}>SCALE: INF</span>
          <span style={{ width: 1, height: 14, background: 'rgba(0,207,255,0.2)' }} />
          <span style={{ fontSize: 8, color: 'rgba(0,207,255,0.4)', letterSpacing: '0.12em' }}>DISTRICTS: 47</span>
          <span style={{ fontSize: 8, color: 'rgba(0,207,255,0.4)', letterSpacing: '0.12em' }}>AGENTS: {agents.length}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 8, color: status?.loop_running ? '#00FF88' : '#FF4444', letterSpacing: '0.12em' }}>
            ● {status?.loop_running ? 'OPERATIONAL' : 'STANDBY'}
          </span>
          <button onClick={exit} style={{
            background: 'none', border: '1px solid rgba(0,207,255,0.25)',
            color: 'rgba(0,207,255,0.6)', fontFamily: "'Orbitron', sans-serif",
            fontSize: 8, padding: '2px 10px', cursor: 'pointer', letterSpacing: '0.12em',
          }}>
            STAND DOWN
          </button>
        </div>
      </div>

      {/* Main 3-column layout */}
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '220px 1fr 260px', gap: 1, overflow: 'hidden', padding: 1 }}>
        {/* Left: Agent nodes */}
        <div style={{
          background: 'rgba(0,5,12,0.95)',
          borderRight: '1px solid rgba(0,207,255,0.08)',
          padding: 14, overflow: 'hidden',
        }}>
          <AgentNodes />
        </div>

        {/* Center: Gear hologram */}
        <div style={{
          background: 'rgba(0,3,8,0.97)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          position: 'relative', overflow: 'hidden',
        }}>
          <GearHologram />
        </div>

        {/* Right: Diagnostics */}
        <div style={{
          background: 'rgba(0,5,12,0.95)',
          borderLeft: '1px solid rgba(0,207,255,0.08)',
          padding: 14, overflow: 'hidden',
        }}>
          <DiagnosticsPanel />
        </div>
      </div>

      {/* Footer */}
      <div style={{
        padding: '6px 20px',
        borderTop: '1px solid rgba(0,207,255,0.12)',
        background: 'rgba(0,207,255,0.02)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 8, color: 'rgba(0,207,255,0.4)', letterSpacing: '0.18em' }}>
          VECTOR GLOBAL NETWORK INTEGRITY
        </span>
        <span style={{ fontSize: 7, color: 'rgba(0,207,255,0.25)', letterSpacing: '0.12em', fontFamily: "'JetBrains Mono', monospace" }}>
          UPTIME: {status ? `${Math.floor((status.uptime_seconds ?? 0) / 3600)}h ${Math.floor(((status.uptime_seconds ?? 0) % 3600) / 60)}m` : '—'} · SYSTEM NOMINAL
        </span>
      </div>
    </div>
  )
}
