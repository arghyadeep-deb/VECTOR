import { useState, useEffect, useRef } from 'react'
import { api } from '../lib/api'

const CYAN = '#00CFFF'
const MONO = "'JetBrains Mono', monospace"
const ORBITRON = "'Orbitron', sans-serif"

// ── Right panel: scrolling live diagnostics ─────────────────────────────────

function DiagnosticsHUD() {
  const [lines, setLines] = useState<string[]>([
    'VECTOR CORE: NOMINAL',
    'DECISION ENGINE: ACTIVE',
    'PERMISSION GATEWAY: STANDBY',
    'CONTEXT ENGINE: SYNCHRONIZED',
    'EPISODIC MEMORY: INITIALIZING',
    'POLICY MEMORY: LOADED',
    'AUTONOMOUS LOOP: RUNNING',
    'OLLAMA: CONNECTED',
    'SYSTEM LOAD: NOMINAL',
    'SECURITY SCANNER: PASSIVE',
    'INFERENCE ENGINE: READY',
    'MEMORY SYNC: ACTIVE',
  ])
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const s = await api.status()
        const count = s.agents?.count ?? '—'
        const uptime = s.uptime_seconds ?? 0
        const h = Math.floor(uptime / 3600)
        const m = Math.floor((uptime % 3600) / 60)
        const memEvt = s.memory?.episodic_memory ?? '—'
        const newLines = [
          `UPTIME: ${h}h ${m}m`,
          `AGENTS: ${count} ACTIVE`,
          `MEMORY: ${memEvt} EVENTS`,
          `LOOP: ${s.loop_running ? 'ACTIVE' : 'STANDBY'}`,
          `TICK: ${new Date().toLocaleTimeString()}`,
        ]
        setLines(prev => [...prev.slice(-35), ...newLines])
      } catch {
        setLines(prev => [...prev.slice(-39), `PING: ${new Date().toLocaleTimeString()}`])
      }
    }, 4000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{
        fontFamily: ORBITRON, fontSize: 8, color: CYAN,
        letterSpacing: '0.2em', marginBottom: 8, opacity: 0.7,
      }}>
        SYSTEM DIAGNOSTICS
      </div>
      <div style={{ flex: 1, overflowY: 'auto', scrollbarWidth: 'none' }}>
        {lines.map((l, i) => (
          <div key={i} style={{
            fontFamily: MONO, fontSize: 8.5, lineHeight: 1.7,
            color: i === lines.length - 1 ? CYAN : 'rgba(0,207,255,0.45)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            <span style={{ color: 'rgba(0,207,255,0.25)', marginRight: 5 }}>›</span>
            {l}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Left panel: static system status ────────────────────────────────────────

function StatusHUD() {
  const [status, setStatus] = useState({
    loop: false, agents: 0, memory: 0, uptime: 0, ollama: false,
  })

  useEffect(() => {
    const fetch = async () => {
      try {
        const s = await api.status()
        setStatus({
          loop: s.loop_running ?? false,
          agents: s.agents?.count ?? 0,
          memory: s.memory?.episodic_memory ?? 0,
          uptime: s.uptime_seconds ?? 0,
          ollama: !!(s.models),
        })
      } catch {}
    }
    fetch()
    const id = setInterval(fetch, 10000)
    return () => clearInterval(id)
  }, [])

  const h = Math.floor(status.uptime / 3600)
  const m = Math.floor((status.uptime % 3600) / 60)

  const rows: [string, string, boolean?][] = [
    ['LOOP',    status.loop ? 'ACTIVE' : 'STANDBY', status.loop],
    ['AGENTS',  String(status.agents)],
    ['MEMORY',  `${status.memory.toLocaleString()} EVT`],
    ['UPTIME',  `${h}h ${m}m`],
    ['OLLAMA',  status.ollama ? 'CONNECTED' : 'OFFLINE', status.ollama],
    ['GATEWAY', 'STANDBY'],
    ['INTEL',   'PASSIVE'],
    ['ENCRYPT', 'AES-256'],
  ]

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{
        fontFamily: ORBITRON, fontSize: 8, color: CYAN,
        letterSpacing: '0.2em', marginBottom: 8, opacity: 0.7,
      }}>
        SYSTEM STATUS
      </div>
      <div style={{
        borderTop: '1px solid rgba(0,207,255,0.15)',
        paddingTop: 8,
        flex: 1,
      }}>
        {rows.map(([key, val, ok]) => (
          <div key={key} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: 6,
          }}>
            <span style={{ fontFamily: MONO, fontSize: 8.5, color: 'rgba(0,207,255,0.4)', letterSpacing: '0.1em' }}>
              {key}
            </span>
            <span style={{
              fontFamily: MONO, fontSize: 8.5,
              color: ok === false ? '#FF4466' : ok === true ? '#00FF88' : 'rgba(0,207,255,0.7)',
              letterSpacing: '0.08em',
            }}>
              {val}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Export ────────────────────────────────────────────────────────────────────

interface Props { side: 'left' | 'right' }

export default function VectorHUD({ side }: Props) {
  const isLeft = side === 'left'
  const width = isLeft ? 190 : 215

  return (
    <div style={{
      position: 'fixed',
      top: '50%',
      transform: 'translateY(-50%)',
      [isLeft ? 'left' : 'right']: 14,
      width,
      maxHeight: 'calc(100vh - 120px)',
      padding: '12px 10px',
      background: 'rgba(0,8,20,0.55)',
      borderLeft: isLeft ? `1px solid rgba(0,207,255,0.12)` : 'none',
      borderRight: !isLeft ? `1px solid rgba(0,207,255,0.12)` : 'none',
      borderTop: '1px solid rgba(0,207,255,0.06)',
      borderBottom: '1px solid rgba(0,207,255,0.06)',
      zIndex: 20,
      overflowY: 'hidden',
      backdropFilter: 'blur(2px)',
    }}>
      {isLeft ? <StatusHUD /> : <DiagnosticsHUD />}
    </div>
  )
}
