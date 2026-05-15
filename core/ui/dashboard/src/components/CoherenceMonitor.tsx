import { useState, useEffect } from 'react'

interface AgentCoherence {
  id: string
  name: string
  coherence: number  // 0-100
  hp: number         // 0-1000
  privilege: 'full' | 'restricted' | 'read_only' | 'suspended'
  active: boolean
}

const PRIVILEGE_COLOR: Record<string, string> = {
  full: '#4CAF50',
  restricted: '#FFB300',
  read_only: '#FF7043',
  suspended: '#EF5350',
}

const MOCK_AGENTS: AgentCoherence[] = [
  { id: 'a1', name: 'vector-coder', coherence: 84, hp: 720, privilege: 'full', active: true },
  { id: 'a2', name: 'vector-security', coherence: 91, hp: 860, privilege: 'full', active: true },
  { id: 'a3', name: 'vector-researcher', coherence: 63, hp: 530, privilege: 'restricted', active: true },
  { id: 'a4', name: 'vector-comms', coherence: 45, hp: 380, privilege: 'read_only', active: false },
]

function CoherenceGauge({ value, size = 40 }: { value: number; size?: number }) {
  const r = (size - 6) / 2
  const circ = 2 * Math.PI * r
  const fill = circ * (1 - value / 100)
  const color = value >= 70 ? '#4FC3F7' : value >= 50 ? '#FFB300' : '#EF5350'
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={4} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={color} strokeWidth={4}
        strokeDasharray={circ} strokeDashoffset={fill}
        strokeLinecap="round"
        style={{ transition: 'stroke-dashoffset 0.6s ease' }}
      />
      <text
        x={size / 2} y={size / 2 + 4}
        textAnchor="middle" fill={color}
        style={{ fontSize: 9, fontFamily: 'monospace', transform: 'rotate(90deg)', transformOrigin: `${size / 2}px ${size / 2}px` }}
      >
        {value}
      </text>
    </svg>
  )
}

function HPBar({ hp }: { hp: number }) {
  const pct = Math.min(100, hp / 10)
  const color = hp >= 700 ? '#4FC3F7' : hp >= 400 ? '#FFB300' : '#EF5350'
  return (
    <div style={{ flex: 1, height: 3, background: 'rgba(255,255,255,0.06)', borderRadius: 2 }}>
      <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.4s' }} />
    </div>
  )
}

export default function CoherenceMonitor() {
  const [agents, setAgents] = useState<AgentCoherence[]>(MOCK_AGENTS)
  const [lastUpdate, setLastUpdate] = useState('')
  const [live, setLive] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch('/api/agents/coherence', { cache: 'no-store' })
        if (!r.ok) throw new Error()
        const d = await r.json()
        setAgents(d.agents ?? MOCK_AGENTS)
        setLive(true)
      } catch {
        setLive(false)
      }
      setLastUpdate(new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    }
    load()
    const id = setInterval(load, 15_000)
    return () => clearInterval(id)
  }, [])

  const avgCoherence = Math.round(agents.reduce((s, a) => s + a.coherence, 0) / Math.max(1, agents.length))

  return (
    <div style={{
      background: 'rgba(0,8,20,0.88)',
      border: '1px solid rgba(79,195,247,0.25)',
      borderRadius: 6,
      padding: '8px 10px',
      fontFamily: 'monospace',
      fontSize: 11,
      color: '#B0BEC5',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ color: '#4FC3F7', fontWeight: 700, fontSize: 10, letterSpacing: 1.5 }}>COHERENCE</span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ color: avgCoherence >= 70 ? '#4FC3F7' : '#FFB300', fontSize: 10 }}>avg {avgCoherence}%</span>
          <span style={{ color: live ? '#4CAF50' : '#37474F', fontSize: 9 }}>{live ? 'LIVE' : 'MOCK'}</span>
        </div>
      </div>

      {/* Agent rows */}
      {agents.map(agent => (
        <div key={agent.id} style={{
          display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5,
          opacity: agent.active ? 1 : 0.45,
        }}>
          <CoherenceGauge value={agent.coherence} size={36} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
              <span style={{ color: '#CFD8DC', fontSize: 9, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 90 }}>
                {agent.name.replace('vector-', '')}
              </span>
              <span style={{
                color: PRIVILEGE_COLOR[agent.privilege] ?? '#546E7A',
                fontSize: 8, letterSpacing: 0.5,
                textTransform: 'uppercase',
              }}>
                {agent.privilege.replace('_', '-')}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <HPBar hp={agent.hp} />
              <span style={{ color: '#37474F', fontSize: 8, flexShrink: 0 }}>{agent.hp}HP</span>
            </div>
          </div>
        </div>
      ))}

      <div style={{ marginTop: 2, color: '#37474F', fontSize: 9, display: 'flex', justifyContent: 'space-between' }}>
        <span>{agents.filter(a => a.active).length}/{agents.length} active</span>
        <span style={{ color: '#546E7A' }}>{lastUpdate}</span>
      </div>
    </div>
  )
}
